## Author : Prashant Srivastava
## Last Modified Date  : Dec 26th, 2022

import requests
import logging
import json
import sys
from py5paisa import *
from strikes_manager import StrikesManager
import pandas as pd
import datetime


def get_india_vix() -> float:
    baseurl = "https://www.nseindia.com/"
    url = "https://www.nseindia.com/api/allIndices"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) "
        "Chrome/80.0.3987.149 Safari/537.36",
        "accept-language": "en,gu;q=0.9,hi;q=0.8",
        "accept-encoding": "gzip, deflate, br",
    }
    try:
        session = requests.Session()
        request = session.get(baseurl, headers=headers, timeout=5)
        cookies = dict(request.cookies)
        response = session.get(url, headers=headers, timeout=5, cookies=cookies)
        if response.status_code == 200:
            indices_data = response.json()

            india_vix = list(
                filter(lambda x: "VIX" in x["indexSymbol"], indices_data["data"])
            )

            return india_vix[0]["last"]
    except:
        logging.getLogger(__name__).info("Error fecthing INDIA VIX")
    return -1.0


def login(cred_file: str):
    with open(cred_file) as cred_fh:
        cred = json.load(cred_fh)

    client = FivePaisaClient(
        email=cred["email"], passwd=cred["passwd"], dob=cred["dob"], cred=cred
    )
    client.login()

    return client


def test():
    client = login("creds.json")
    sm = StrikesManager(client, {})

    straddle_strikes = sm.strangle_strikes(5.0, "NIFTY")
    print(straddle_strikes)
    df_ce = client.historical_data(
        "N", "D", straddle_strikes["ce_code"], "5m", "2023-06-27", "2023-06-28"
    )
    df_pe = client.historical_data(
        "N", "D", straddle_strikes["pe_code"], "5m", "2023-06-27", "2023-06-28"
    )

    ## drop null or nan values
    df_ce = df_ce.dropna()
    df_pe = df_pe.dropna()

    ## get the Close price and Datetime from both the dataframes and make a new dataframe
    df_ce = df_ce[["Close", "Datetime"]]
    df_pe = df_pe[["Close", "Datetime"]]
    df_ce.columns = ["ce_close", "Datetime"]
    df_pe.columns = ["pe_close", "Datetime"]
    df_ce_pe = pd.merge(df_ce, df_pe, on="Datetime")
    df_ce_pe["ce_pe_close"] = df_ce_pe["ce_close"] + df_ce_pe["pe_close"]
    df_ce_pe["ce_pe_close"] = df_ce_pe["ce_pe_close"].round(2)
    df_ce_pe["Datetime"] = pd.to_datetime(df_ce_pe["Datetime"])
    df_ce_pe["Datetime"] = df_ce_pe["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df_ce_pe["Datetime"] = pd.to_datetime(df_ce_pe["Datetime"])
    df_ce_pe = df_ce_pe.set_index("Datetime")
    df_ce_pe = df_ce_pe.sort_index()
    df_ce_pe = df_ce_pe.reset_index()

    print(df_ce_pe)

    ## plot the graph
    import matplotlib.pyplot as plt

    ## show a continuous line graph for the close price
    plt.plot(
        df_ce_pe["Datetime"],
        df_ce_pe["ce_pe_close"],
        color="blue",
        linestyle="solid",
        linewidth=3,
    )
    ## plot ce and pe close price
    plt.plot(
        df_ce_pe["Datetime"],
        df_ce_pe["ce_close"],
        color="red",
        linestyle="solid",
        linewidth=1,
    )
    plt.plot(
        df_ce_pe["Datetime"],
        df_ce_pe["pe_close"],
        color="green",
        linestyle="solid",
        linewidth=1,
    )
    plt.show()

    sys.exit()


if __name__ == "__main__":
    # print(get_india_vix())
    client = login("creds.json")
    test()
    print(client.positions())
    # client.bo_order(OrderType='S',
    #                 Exchange='N',
    #                 ExchangeType='D',
    #                 ScripCode= 44260, #44222,
    #                 Qty=50,
    #                 LimitPrice=8.05,
    #                 TargetPrice=4.5,
    #                 StopLossPrice=9.5,
    #                 LimitPriceForSL=9.8,
    #                 TrailingSL=0.5,
    #                 TriggerPrice=9.0)

    # TARGET_PRICE is 70% less than the strike price
    # STOP_LOSS_PRICE is 1000% above than the strike price
    strike_price = 8.5
    TARGET_THERSHOLD = 70
    STOP_LOSS_THERSHOLD = 100
    scrip_code = 44260
    TRAILING_STOP_LOSS = 0.5
    QTY = 50
    tag = "test"

    targetPrice = strike_price * (1 - TARGET_THERSHOLD / 100)
    stopLossPrice = strike_price * (1 + STOP_LOSS_THERSHOLD / 100)

    # Stop loss trigger price is 0.5 less than stop loss price
    stopLossTriggerPrice = stopLossPrice - 0.5

    # Limit price
    limitPrice = strike_price

    # Log all prices above
    print("Scrip Code: %s", scrip_code)
    print("Strike Price: %s", strike_price)
    print("Target Price: %s", targetPrice)
    print("Stop Loss Price: %s", stopLossPrice)
    print("Stop Loss Trigger Price: %s", stopLossTriggerPrice)
    print("Limit Price: %s", limitPrice)

    client.bo_order(
        OrderType="S",
        Exchange="N",
        ExchangeType="D",
        ScripCode=scrip_code,
        Qty=QTY,
        LimitPrice=limitPrice,
        TargetPrice=targetPrice,
        StopLossPrice=stopLossTriggerPrice,
        LimitPriceForSL=stopLossPrice,
        TrailingSL=TRAILING_STOP_LOSS,
        RemoteOrderID=tag,
    )
