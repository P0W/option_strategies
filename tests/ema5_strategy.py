import concurrent.futures
import datetime
import logging
import os
import pathlib

import backtrader as bt
import pandas as pd
import requests

from src.clients.client_5paisa import Client as Client5Paisa


class EMA5Strategy(bt.Strategy):
    params = (
        ("period", 5),
        ("stop_loss", 1),
        ("target", 2),
    )

    def __init__(self, qty=1):
        super().__init__()
        self.ema = bt.indicators.ExponentialMovingAverage(
            self.data.close, period=self.params.period
        )
        self.order = None
        self.price = None
        self.comm = None
        self.qty = qty

    def next(self):
        if self.order:
            return  # if an order is pending, do nothing

        if not self.position:  # not in the market
            if (
                self.data.low[-1] > self.data.high[-2]
                and self.data.close[0] < self.data.low[-1]
                and self.data.low[-1] > self.ema[-1]
                and self.data.low[0] > self.ema[0]
            ):
                self.order = self.sell(size=self.qty)
                self.price = self.data.close[0]
                self.stop_price = max(self.data.high[-1], self.data.high[-2])
                self.target_price = self.price - self.params.target * (
                    self.price - self.stop_price
                )
        else:  # in the market
            if (
                self.data.close[0] >= self.target_price
                or self.data.close[0] <= self.stop_price
            ):
                self.order = self.close(size=self.qty)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY EXECUTED, {order.executed.price}")
            elif order.issell():
                self.log(f"SELL EXECUTED, {order.executed.price}")

        self.order = None

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")


class Expectancy(bt.Analyzer):
    def __init__(self):
        self.wins = 0
        self.losses = 0
        self.total_gain = 0
        self.total_loss = 0

    def notify_trade(self, trade):
        if trade.isclosed:
            if trade.pnl > 0:
                self.wins += 1
                self.total_gain += trade.pnl
            else:
                self.losses += 1
                self.total_loss += trade.pnl

    def get_analysis(self):
        try:
            expectancy = (
                (self.total_gain / self.wins) / (self.total_loss / self.losses)
                if self.losses > 0
                else float("inf")
            )
            return {"expectancy": expectancy}
        except:
            return {"expectancy": 0}


## Run strategy
def run_strategy(
    client: Client5Paisa,
    scrip_code: int,
    lot_size=1,
    exch_type: str = "D",
    name: str = None,
):
    today = datetime.datetime.now()
    today = today.strftime("%Y-%m-%d")
    no_of_years = 1
    past_date = datetime.datetime.now() - datetime.timedelta(days=90)
    df = client.historical_data("N", exch_type, scrip_code, "5m", past_date, today)
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    # df['Datetime'] = pd.to_datetime(df['Datetime'])
    df.set_index("Datetime", inplace=True)
    df.rename(columns={"Datetime": "datetime"}, inplace=True)
    ## get current price
    current_price = df["Close"].iloc[-1]
    # Convert the DataFrame to a Backtrader data feed
    data = bt.feeds.PandasData(dataname=df)

    # Create a Cerebro entity
    cerebro = bt.Cerebro()

    # Add analyzers
    cerebro.addanalyzer(Expectancy, _name="expectancy")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # Add the data feed to Cerebro
    cerebro.adddata(data)

    # Add the strategy to Cerebro
    # ema5 = EMA5Strategy(qty=lot_size)
    investment = 100000
    if lot_size == 1:
        lot_size = investment // current_price
        logging.info(f"Lot size for {name} is {lot_size}")
    cerebro.addstrategy(EMA5Strategy, qty=lot_size)

    ## set the initial capital
    cerebro.broker.setcash(investment)
    ## set brokerage
    cerebro.broker.setcommission(commission=0.0001)

    # Run the strategy
    results = cerebro.run()

    # Get analysis results
    expectancy = results[0].analyzers.expectancy.get_analysis()["expectancy"]
    sqn = results[0].analyzers.sqn.get_analysis()["sqn"]
    trades = results[0].analyzers.trades.get_analysis()
    ## win loss ratio
    try:
        win_loss_ratio = trades.won.total / trades.lost.total
        ## profit factor
        profit_factor = -trades.pnl.net.total / trades.pnl.net.total
    except:
        win_loss_ratio = -1
        profit_factor = -1
    try:
        ## total trades
        total_trades = trades.total.total
        ## total profit
        total_profit = trades.pnl.net.total
        ## average profit
        average_profit = trades.pnl.net.average
        ## average trade
        average_trade = trades.pnl.net.average
        ## largest win
        largest_win = trades.won.pnl.max
        ## largest loss
        largest_loss = trades.lost.pnl.max
        ## average win
        average_win = trades.won.pnl.average
        ## average loss
        average_loss = trades.lost.pnl.average
        ## max consecutive wins
        max_consecutive_wins = trades.streak.won.longest
        ## max consecutive losses
        max_consecutive_losses = trades.streak.lost.longest
        drawdown_len = results[0].analyzers.drawdown.get_analysis()["len"]
        drawdown_drawdown = results[0].analyzers.drawdown.get_analysis()["drawdown"]
        drawdown_moneydown = results[0].analyzers.drawdown.get_analysis()["moneydown"]
    except:
        logging.error("Error in calculating the metrics %s", name)
        total_trades = 0
        total_profit = 0
        average_profit = 0
        average_trade = 0
        largest_win = 0
        largest_loss = 0
        average_win = 0
        average_loss = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        drawdown_len = 0
        drawdown_drawdown = 0
        drawdown_moneydown = 0

    # Create a DataFrame
    df = pd.DataFrame(
        [
            [
                scrip_code,
                name,
                lot_size,
                expectancy,
                sqn,
                win_loss_ratio,
                profit_factor,
                total_trades,
                total_profit,
                average_profit,
                average_trade,
                largest_win,
                largest_loss,
                average_win,
                average_loss,
                max_consecutive_wins,
                max_consecutive_losses,
                drawdown_len,
                drawdown_drawdown,
                drawdown_moneydown,
            ]
        ],
        columns=[
            "Scrip Code",
            "Name",
            "Lot Size",
            "Expectancy",
            "SQN",
            "Win Loss Ratio",
            "Profit Factor",
            "Total Trades",
            "Total Profit",
            "Average Profit",
            "Average Trade",
            "Largest Win",
            "Largest Loss",
            "Average Win",
            "Average Loss",
            "Max Consecutive Wins",
            "Max Consecutive Losses",
            "Max Drawdown Length",
            "Max Drawdown Drawdown",
            "Max Drawdown Moneydown",
        ],
    )

    # if total profit is greater than 0 plot
    if total_profit >= 5000:
        ## plot the chart as candlestick
        ##cerebro.plot(style="candlestick")

        # Write the DataFrame to a json file
        df.to_json(f"results/{name}.json", orient="records", indent=2)
    return total_profit


def read_scrip_master(exch_type: str = "D"):
    todays_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    download_path = f"downloads/scripmaster_{todays_date}.csv"
    ## check if the file exists
    scrip_file = pathlib.Path(download_path)
    if not scrip_file.exists():
        logging.info("Downloading the scrip master file")
        full_path = r"https://images.5paisa.com/website/scripmaster-csv-format.csv"
        ## use the requests library to download the csv file
        req = requests.get(full_path)
        url_content = req.content

        csv_file = open(download_path, "wb")
        csv_file.write(url_content)
        csv_file.close()
    else:
        logging.info("Scrip master file already exists")
    ## read the file from the downloads folder as a dataframe
    scrip_df = pd.read_csv(download_path)
    scrip_df = scrip_df[
        (scrip_df["Exch"] == "N")
        & (scrip_df["ExchType"] == exch_type)
        & (scrip_df["AllowedToTrade"] == "Y")
        & (scrip_df["CO BO Allowed"] == "Y")
        & (scrip_df["TickSize"] == 0.05)
    ]
    ## Print the size of the dataframe
    logging.info(f"Size of the dataframe is {scrip_df.shape}")
    scrip_df = scrip_df[["Scripcode", "Name", "Expiry", "FullName", "LotSize"]]
    return scrip_df


def worker(code:int, size:int, full_name:str):
    profit = run_strategy(
        client, scrip_code=code, lot_size=size, name=full_name, exch_type=exch_type
    )
    logging.info("Profit for %s (lotsize =%d) is %f", full_name, size, profit)


if __name__ == "__main__":
    Client5Paisa.configure_logger(logging.DEBUG, "ema5_strategy")
    exch_type = "D"
    scrip_df = read_scrip_master(exch_type)
    pid = os.getpid()
    logging.info("PID of the script is %d", pid)

    if exch_type == "D":
        ## Pick LotSize >= 1000 and less than 5000
        scrip_df = scrip_df[
            (scrip_df["LotSize"] >= 1000) & (scrip_df["LotSize"] <= 10000)
        ]

    ## get all the scrip codes
    scrip_codes = scrip_df["Scripcode"].tolist()
    lot_sizes = scrip_df["LotSize"].tolist()
    full_names = scrip_df["FullName"].tolist()

    client = Client5Paisa()
    client.login()
    user_data = {"scrips": {}}
    total_profit = 0
    investment = 100000

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(worker, scrip_codes, lot_sizes, full_names)
