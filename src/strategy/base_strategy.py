# Author : Prashant Srivastava
from enum import Enum
import json
import logging
import math
import time
from typing import Dict, List
from abc import ABC
from abc import abstractmethod


class StrategyState(Enum):
    WAITING = 0
    PLACED = 1
    EXECUTED = 2
    SQUAREDOFF = 3
    STOPPED = 4


class BaseStrategy(ABC):
    def __init__(self, name: str, scrip_codes: List):
        self.scrip_codes = scrip_codes
        self.name = name
        self.logger = logging.getLogger(__name__)
        self.executed_orders = None
        self.tag = f"{self.name.lower()}{int(time.time())}"
        self.target_mtm_profit = math.inf
        self.target_mtm_loss = -math.inf
        self.startegy_state = StrategyState.WAITING

    def set_mtm_target(self, profit: float):
        self.target_mtm_profit = profit

    def set_mtm_stop_loss(self, loss: float):
        self.target_mtm_loss = loss

    def get_mtm_target(self):
        return self.target_mtm_profit

    def get_mtm_stop_loss(self):
        return self.target_mtm_loss

    def set_strategy_state(self, state: StrategyState):
        self.logger.info("Strategy state changed to %s", state)
        self.startegy_state = state

    def get_strategy_state(self):
        return self.startegy_state

    def unmonitor(self, scrip_code: int):
        ## remove scrip code from self.scrip_codes if it exists
        if scrip_code in self.scrip_codes:
            self.scrip_codes.remove(scrip_code)
            self.logger.debug("Removed scrip code %d from strategy", scrip_code)

    def exit(self, _ohlcvt: Dict) -> bool:
        shall_exit = False
        if self.is_in_position():
            pnl = self.get_pnl()
            if pnl:
                if pnl > self.get_mtm_target():
                    self.logger.info("Target Profit Hit at %f", pnl)
                    shall_exit = True
                elif pnl <= self.get_mtm_stop_loss():
                    self.logger.info("Target Stop Loss Hit at %f", pnl)
                    shall_exit = True
                if shall_exit:
                    self.logger.info(
                        "Executed Orders: %s",
                        json.dumps(self.get_all_executed_orders(), indent=2),
                    )
        return shall_exit

    def get_pnl(self):
        # sum all the pnl of each leg
        total_pnl = None
        if self.executed_orders:
            total_pnl = 0.0
            for _, info in self.executed_orders.items():
                total_pnl += info["pnl"]
        return total_pnl

    def is_in_position(self):
        return self.get_strategy_state() in [
            StrategyState.EXECUTED,
            StrategyState.PLACED,
        ]

    def get_executed_order(self, code) -> (float, int):  # Avg, Qty
        if code not in self.executed_orders:
            return (None, None)
        return (self.executed_orders[code]["rate"], self.executed_orders[code]["qty"])

    def get_all_executed_orders(self):
        return self.executed_orders

    def run(self, ohlcvt: Dict, _user_data: Dict = None):
        # Following is done to update the ltp of the scrip in the
        # executed_orders only
        if self.get_strategy_state() == StrategyState.EXECUTED:
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

    def order_placed(self, order: Dict, _subs_list: Dict, _user_data: Dict):
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
                ## If all the self.executed_orders.keys() are in self.scrip_codes
                ## then set strategy state to executed
                if all(code in self.scrip_codes for code in self.executed_orders):
                    self.logger.debug(
                        "All orders executed, setting strategy state to executed"
                    )
                    self.set_strategy_state(StrategyState.EXECUTED)
                else:
                    self.logger.debug("Not all orders executed")
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

    @abstractmethod
    def entry(self, ohlcvt: Dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_leg_pnl(self, code: int, avg: float, qty: int, ltp: float):
        raise NotImplementedError
