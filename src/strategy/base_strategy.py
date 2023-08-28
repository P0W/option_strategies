# Author : Prashant Srivastava
import json
import logging
import time
from abc import ABC
from abc import abstractmethod


class BaseStrategy(ABC):
    def __init__(self, name: str, scrip_codes: list):
        self.scrip_codes = scrip_codes
        self.name = name
        self.logger = logging.getLogger(__name__)
        self.executed_orders = None
        self.tag = f"{self.name.lower()}{int(time.time())}"

    @abstractmethod
    def entry(self, ohlcvt: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exit(self, ohlcvt: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_leg_pnl(self, code: int, avg: float, qty: int, ltp: float):
        raise NotImplementedError

    def get_pnl(self):
        # sum all the pnl of each leg
        total_pnl = None
        if self.executed_orders:
            total_pnl = 0.0
            for _, info in self.executed_orders.items():
                total_pnl += info["pnl"]
        return total_pnl

    def is_in_position(self):
        return self.executed_orders is not None

    def get_executed_order(self, code) -> (float, int):  # Avg, Qty
        if code not in self.executed_orders:
            return (None, None)
        return (self.executed_orders[code]["rate"], self.executed_orders[code]["qty"])

    def get_all_executed_orders(self):
        return self.executed_orders

    @abstractmethod
    def run(self, ohlcvt: dict, user_data: dict = None):
        # Following is done to update the ltp of the scrip in the
        # executed_orders only
        if self.is_in_position():
            ltp = ohlcvt["c"]
            code = ohlcvt["code"]
            if code in self.executed_orders:
                self.executed_orders[code]["ltp"] = ltp
                self.executed_orders[code]["pnl"] = self.get_leg_pnl(
                    code,
                    self.executed_orders[code]["rate"],
                    self.executed_orders[code]["qty"],
                    self.executed_orders[code]["ltp"],
                )

    def add_executed_orders(self, executed_orders: dict):
        if not self.executed_orders:
            self.executed_orders = {}
        self.executed_orders[executed_orders["ScripCode"]] = executed_orders

    @abstractmethod
    def order_placed(self, order: dict, _subs_list: dict, user_data: dict):
        # If this is a fresh order and is fully executed
        # Fresh order : order which is not square off order or stop loss order
        fresh_orders = (
            not (
                order["RemoteOrderId"].startswith("sl")
                or order["RemoteOrderId"].startswith("sq")
            )
            and order["Status"] == "Fully Executed"
        )
        if fresh_orders and order["ScripCode"] in self.scrip_codes:
            if not self.executed_orders:
                self.executed_orders = {}
            if order["ScripCode"] not in self.executed_orders:
                self.executed_orders[order["ScripCode"]] = {
                    "rate": order["Price"],
                    "qty": order["Qty"],
                    "ltp": order["Price"],
                    "pnl": 0.0,
                }
                self.logger.info(
                    "New updated executed_orders %s",
                    json.dumps(self.executed_orders, indent=2),
                )
            else:
                self.logger.warning(
                    "Received a very late/duplicate order update from broker? %s",
                    json.dumps(self.executed_orders, indent=2),
                )

    @abstractmethod
    def stop(self):
        raise NotImplementedError

    @abstractmethod
    def start(self):
        raise NotImplementedError
