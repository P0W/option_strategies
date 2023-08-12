## Author : Prashant Srivastava

import os
import sys
import time

current_directory = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory
parent_directory = os.path.dirname(current_directory)
# Add the parent directory to sys.path temporarily
sys.path.append(parent_directory)

import base_strategy
import live_feed_manager
import order_manager
import strikes_manager
import client_manager


## The Strangle Strategy. Refer entry and exit methods for the strategy
class StrangleStrategy(base_strategy.BaseStrategy):
    ## NIFTY_INDEX is the scrip code for NIFTY index
    NIFTY_INDEX = 999920000

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

        self.target_profit = 1500.0
        self.sl_target = -1000.0
        self.strikes = strikes

        self.user_data = {
            "nifty_index": {"low": -1.0, "high": -1.0},
            "start_time": time.time(),
        }

        self.logger.info("Strangle Strategy Initiated")

    ## @override
    ## Exit Condtion: Check if the pnl is greater than target profit or less than stop loss
    ## If yes, exit the trade
    def exit(self, ohlcvt: dict) -> bool:
        if self.is_in_position():
            pnl = self.get_pnl()
            if pnl and pnl >= self.target_profit or pnl <= self.sl_target:
                return True
        return False

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
                time.time() - self.user_data["start_time"] > 15 * 60
            ):  ## Wait for 15 minutes
                ## check "close" of nifty index is between high and low before the start of the strategy
                if (
                    ohlcvt["c"] < self.user_data["nifty_index"]["high"]
                    and ohlcvt["c"] > self.user_data["nifty_index"]["low"]
                ):
                    ## Update the start time
                    self.user_data["start_time"] = time.time()
                    ## Unsubscribe from the nifty index feed
                    self.feed_manager.unsubscribe(
                        scrip_codes=[StrangleStrategy.NIFTY_INDEX]
                    )
                    ## we are ready to take the trade
                    self.logger.info("Ready to take the trade")
                    return True
        return False

    ## @override
    ## Strategy brief: If we are in a trade, update the leg pnl
    ## If we are not in a trade, check if we need to take the trade
    ## If yes, take the trade
    ## If we are in a trade, check if we need to exit
    ## If yes, exit the trade
    def run(self, ohlcvt: dict, user_data: dict = None):
        code = ohlcvt["code"]
        ltp = ohlcvt["c"]
        if self.is_in_position():
            ## Update the leg pnl
            avg, qty = self.get_executed_order(code)
            leg_pnl = (avg - ltp) * qty
            self.update_leg(code, leg_pnl)

            ## Check if we need to exit
            if self.exit(ohlcvt):
                ## Square off both legs. Square off needs the ltp of the scrip
                all_executed_orders = self.get_all_executed_orders()
                self.order_manager.squareoff(
                    tag=self.tag,
                    strikes={
                        code: all_executed_orders[code]["ltp"]
                        for code in all_executed_orders
                    },
                )
                self.order_manager.squareoffSL(tag=self.tag)
                ## Unsubscribe from the strikes
                self.feed_manager.unsubscribe(scrip_codes=self.scrip_codes)
        elif self.entry(ohlcvt):
            ## Take strangle
            self.order_manager.place_short(self.strikes, self.tag)
            self.order_manager.place_short_stop_loss(self.tag)

        return super().run(ohlcvt)

    ## @override
    ## Stop the feed manager. This is not required as the feed manager will
    ## stop automatically after 15 seconds if no scrip is subscribed
    def stop(self):
        self.feed_manager.stop()
        return super().stop()

    ## @override
    ## If one of the leg is exited (due to stop loss), update the stop loss order
    ## Move the stop loss order to entry price of the other leg
    def order_placed(self, order: dict, subsList: dict, user_data: dict):
        super().order_placed(order, subsList, user_data)
        ## user_data["order_update"] is a list of scrip codes removed from subscription
        unsubscribeList = user_data["order_update"]
        if len(unsubscribeList) == 1:
            all_executed_orders = self.get_all_executed_orders()
            ## Get the scrip code that was removed from subscription
            scrip_code = unsubscribeList[0]
            ## Get the other scrip code from all_executed_orders
            other_scrip_code = [
                code for code in all_executed_orders if code != scrip_code
            ][0]
            ## update the stop loss order - Move SL to entry price
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


if __name__ == "__main__":
    ## Setup logging
    client_manager.configure_logger("DEBUG")
    ## Setup client
    client = client_manager.login("..\creds.json")
    ## Create live feed and start the strategy monitor
    live_feed = live_feed_manager.LiveFeedManager(client, {})
    ## Create order manager
    om = order_manager.OrderManager(client, {})
    ## Create strikes manager
    sm = strikes_manager.StrikesManager(client, {})
    strikes = sm.strangle_strikes(closest_price_thresh=9.0, index="NIFTY")
    strategy = StrangleStrategy(
        strikes=strikes, feed_manager=live_feed, order_manager=om, strikes_manager=sm
    )
    strategy.start()
