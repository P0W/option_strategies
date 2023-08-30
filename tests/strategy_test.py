## Author : Prashant Srivastava
# pylint: disable=redefined-outer-name
import argparse
import json
import sys
import time


from src.strategy import base_strategy
from src.common import live_feed_manager
from src.common import order_manager
from src.common import strikes_manager

# from clients.client_dummy import Client as Client5Paisa
from src.clients.client_5paisa import Client as Client5Paisa


## The Strangle Strategy. Refer entry and exit methods for the strategy
class StrangleStrategy(base_strategy.BaseStrategy):
    ## NIFTY_INDEX is the scrip code for NIFTY index
    NIFTY_INDEX = 999920000
    BANKNIFTY_INDEX = 999920005
    INDIA_VIX = 999920019

    ## Constructor
    def __init__(
        self,
        strikes: dict,
        feed_manager: live_feed_manager.LiveFeedManager,
        order_manager: order_manager.OrderManager,
        strikes_manager: strikes_manager.StrikesManager,
    ):
        super().__init__(
            "Strangle",
            [StrangleStrategy.NIFTY_INDEX, strikes["ce_code"], strikes["pe_code"]],
        )
        self.strikes_manager = strikes_manager
        self.order_manager = order_manager
        self.feed_manager = feed_manager

        ## This should be managed by base, by currently putting it here

        self.strikes = strikes
        self.set_mtm_target(self.order_manager.config["target_profit"])
        self.set_mtm_stop_loss(self.order_manager.config["target_loss"])
        self.qty = self.order_manager.config["QTY"]
        self.wait_time = self.order_manager.config["wait_time"]

        ## Display all the config
        self.logger.info("target_profit: %f", self.get_mtm_target())
        self.logger.info("target_loss: %f", self.get_mtm_stop_loss())
        self.logger.info("qty: %d", self.qty)
        self.logger.info("strikes: %s", json.dumps(self.strikes, indent=2))
        self.logger.info("wait_time: %f", self.wait_time)

        ## Ask user if this looks good
        self.logger.info("Press y to continue")
        if input() != "y":
            sys.exit(-1)

        self.displayed_time = time.time()

        self.user_data = {
            "nifty_index": {"low": -1.0, "high": -1.0},
            "start_time": self.displayed_time,
        }
        self.ltp = {}

        self.logger.info("Strangle Strategy Initiated")

    def get_leg_pnl(self, _code: int, avg: float, qty: int, ltp: float):
        return (avg - ltp) * qty

    ## @override
    ## Entry Condtion: Wait for 15 minutes after the start of the strategy
    ## Check if the close of nifty index is between the high and low of the nifty index
    ## If yes, unsubscribe from the nifty index feed and take the trade
    def entry(self, ohlcvt: dict) -> bool:
        if self.is_in_position():  ## Already in a trade
            return False
        if StrangleStrategy.NIFTY_INDEX == ohlcvt["code"]:
            if self.user_data["nifty_index"]["low"] == -1.0:
                self.user_data["nifty_index"]["low"] = ohlcvt["l"]
            if self.user_data["nifty_index"]["high"] == -1.0:
                self.user_data["nifty_index"]["high"] = ohlcvt["h"]
            if (
                time.time() - self.user_data["start_time"] > self.wait_time
            ):  ## Wait for 15 seconds
                self.user_data["start_time"] = time.time()
                ## check "close" of nifty index is between high and
                ## low before the start of the strategy
                if (
                    ohlcvt["c"] < self.user_data["nifty_index"]["high"]
                    and ohlcvt["c"] > self.user_data["nifty_index"]["low"]
                ):
                    ## Unsubscribe from the nifty index feed
                    self.feed_manager.unsubscribe(
                        scrip_codes=[StrangleStrategy.NIFTY_INDEX]
                    )
                    ## Reove the nifty index from the scrip codes
                    self.unmonitor(StrangleStrategy.NIFTY_INDEX)
                    ## we are ready to take the trade
                    self.logger.info("Ready to take the trade at %f", ohlcvt["c"])
                    ## Log some stats
                    self.logger.debug(
                        "Entry Time stamp: %2.f", self.user_data["start_time"]
                    )
                    self.logger.debug("Candle Time stamp: %2.f", ohlcvt["t"])
                    self.logger.debug(
                        "Candle timestamp difference: %2.f",
                        self.user_data["start_time"] - ohlcvt["t"],
                    )
                    return True
                ## 15 seconds have passed, but the close is not between high and low
                self.logger.debug(
                    "%.2f seconds Elapsed. Nifty at %f not between [%f, %f]",
                    self.wait_time,
                    ohlcvt["c"],
                    self.user_data["nifty_index"]["low"],
                    self.user_data["nifty_index"]["high"],
                )
            else:
                self.logger.info(
                    "Nifty at %f waiting for entry condition [%f, %f]",
                    ohlcvt["c"],
                    self.user_data["nifty_index"]["low"],
                    self.user_data["nifty_index"]["high"],
                )
        return False

    ## @override
    ## Strategy brief: If we are in a trade, update the leg pnl
    ## If we are not in a trade, check if we need to take the trade
    ## If yes, take the trade
    ## If we are in a trade, check if we need to exit
    ## If yes, exit the trade
    def run(self, ohlcvt: dict, user_data: dict = None):
        super().run(ohlcvt)
        code = ohlcvt["code"]
        ltp = ohlcvt["c"]
        self.ltp[code] = ltp
        all_executed_orders = self.get_all_executed_orders()
        if self.is_in_position():
            if self.get_strategy_state() == base_strategy.StrategyState.EXECUTED:
                ## Check if we need to exit
                if self.exit(ohlcvt):
                    self.set_strategy_state(base_strategy.StrategyState.SQUAREDOFF)
                    self.logger.info("Squaring off the trade")
                    ## Square off both legs. Square off needs the ltp of the scrip
                    self.order_manager.squareoff(
                        tag=self.tag,
                        strikes={
                            code: all_executed_orders[code]["ltp"]
                            for code in all_executed_orders
                        },
                    )
                    self.logger.info("Cancelling off the sl order")
                    self.order_manager.squareoff_sl_order(tag=self.tag)
                    ## Unsubscribe from the strikes
                    self.feed_manager.unsubscribe(scrip_codes=self.scrip_codes)
                    self.feed_manager.stop()
                else:
                    ## Log pnl updates every 15 seconds
                    if ohlcvt["t"] - self.displayed_time > 15:
                        self.displayed_time = ohlcvt["t"]
                        self.logger.debug("Current Pnl %.2f", self.get_pnl())
            else:
                self.logger.info(
                    "Waiting for order to be executed %s", self.get_strategy_state()
                )
        elif self.entry(ohlcvt):
            self.set_strategy_state(base_strategy.StrategyState.PLACED)
            ## Take strangle
            self.order_manager.place_short(self.strikes, self.tag)
            self.order_manager.place_short_stop_loss_v2(self.tag)

    ## @override
    ## Stop the feed manager. This is not required as the feed manager will
    ## stop automatically after 15 seconds if no scrip is subscribed
    def stop(self):
        self.set_strategy_state(base_strategy.StrategyState.STOPPED)
        self.feed_manager.stop()
        return super().stop()

    ## @override
    ## If one of the leg is exited (due to stop loss), update the stop loss order
    ## Move the stop loss order to entry price of the other leg
    def order_placed(self, order: dict, subsList: dict, user_data: dict):
        super().order_placed(order, subsList, user_data)
        ## user_data["order_update"] is a list of scrip codes removed from subscription
        unsubscribe_list = user_data["order_update"]
        if len(unsubscribe_list) == 1:
            all_executed_orders = self.get_all_executed_orders()
            ## Get the scrip code that was removed from subscription
            scrip_code = unsubscribe_list[0]
            ## Get the other scrip code from all_executed_orders
            other_scrip_code = [
                code for code in all_executed_orders if code != scrip_code
            ][0]
            ## update the stop loss order - Move SL to entry price
            self.logger.info(
                "Modifying stop loss order for %s, %f",
                other_scrip_code,
                all_executed_orders[other_scrip_code]["rate"],
            )
            self.order_manager.modify_stop_loss_order(
                tag=self.tag,
                scrip_code=other_scrip_code,
                price=all_executed_orders[other_scrip_code]["rate"],
            )

    def start(self):
        self.feed_manager.monitor(
            scrip_codes=[
                StrangleStrategy.NIFTY_INDEX,
                self.strikes["ce_code"],
                self.strikes["pe_code"],
            ],
            on_scrip_data=self.run,
            on_order_update=self.order_placed,
        )


argparser = argparse.ArgumentParser()
argparser.add_argument("--closest_premium", type=float, required=True)
argparser.add_argument("--sl_factor", type=float, required=True)
argparser.add_argument("--qty", type=int, required=True)
argparser.add_argument("--index_option", type=str, default="NIFTY")
argparser.add_argument("--exchange_type", type=str, default="D")
argparser.add_argument("--target_profit", type=float, required=True)
argparser.add_argument("--target_loss", type=float, required=True)
argparser.add_argument("--wait_time", type=float, default=15.0)


if __name__ == "__main__":
    args = argparser.parse_args()
    # if help is used, exit
    try:
        if args.help:
            sys.exit(-1)
    except Exception:
        pass

    ## Setup logging
    Client5Paisa.configure_logger("DEBUG")
    ## Setup client
    client = Client5Paisa("creds.json")
    client.login()

    ## Set up Config
    config = {
        "CLOSEST_PREMINUM": args.closest_premium,
        "SL_FACTOR": args.sl_factor,
        "QTY": args.qty,
        "INDEX_OPTION": args.index_option,
        "exchangeType": args.exchange_type,
        "target_profit": args.target_profit,
        "target_loss": args.target_loss,
        "wait_time": args.wait_time,
    }
    ## Get config from argparse
    ## Create live feed and start the strategy monitor
    live_feed = live_feed_manager.LiveFeedManager(client, config)
    ## Create order manager
    om = order_manager.OrderManager(client, config)
    ## Create strikes manager
    sm = strikes_manager.StrikesManager(client, config)
    try:
        strikes = sm.strangle_strikes(
            closest_price_thresh=config["CLOSEST_PREMINUM"],
            index=config["INDEX_OPTION"],
        )
        strategy = StrangleStrategy(
            strikes=strikes,
            feed_manager=live_feed,
            order_manager=om,
            strikes_manager=sm,
        )
        strategy.start()
    except Exception as e:
        print(e)
        strategy.stop()
    sys.exit(0)
