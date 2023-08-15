## Author : Prashant Srivastava

import logging
import time
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    def __init__(self, name: str, scrip_codes: list):
        self.scrip_codes = scrip_codes
        self.name = name
        self.logger = logging.getLogger(__name__)
        self.executed_orders = None
        self.tag = "%s%d" % (self.name.lower(), int(time.time()))

    @abstractmethod
    def entry(self, ohlcvt: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exit(self, ohlcvt: dict) -> bool:
        raise NotImplementedError

    def get_pnl(self):
        ## sum all the pnl of each leg
        total_pnl = None
        if self.executed_orders:
            total_pnl = 0.0
            for code in self.executed_orders.keys():
                total_pnl += self.executed_orders[code]["pnl"]
        return total_pnl

    def update_leg(self, code, leg_pnl):
        if not self.executed_orders:
            self.executed_orders = {}
        self.executed_orders[code]["pnl"] = leg_pnl

    def is_in_position(self):
        return True if self.executed_orders else False

    def get_executed_order(self, code) -> (float, int):  # Avg, Qty
        return (self.executed_orders[code]["rate"], self.executed_orders[code]["qty"])

    def get_all_executed_orders(self):
        return self.executed_orders

    @abstractmethod
    def run(self, ohlcvt: dict, user_data: dict = None):
        if self.is_in_position():
            ltp = ohlcvt["c"]
            code = ohlcvt["code"]
            self.executed_orders[code]["ltp"] = ltp

    @abstractmethod
    def order_placed(self, order: dict, subsList: dict, user_data: dict):
        ## This will be called for "Fully Executed"" only
        ## check if order["ScripCode"] is in self.scrip_codes
        ## if yes, add to self.executed_orders
        if order["ScripCode"] in self.scrip_codes:
            if not self.executed_orders:
                self.executed_orders = {}
            self.executed_orders[order["ScripCode"]] = {
                "rate": order["Price"],
                "qty": order["Qty"],
                "ltp": order["Price"],
                "pnl": 0.0,
            }

    @abstractmethod
    def stop(self):
        raise NotImplementedError

    @abstractmethod
    def start(self):
        raise NotImplementedError
