# Author: Prashant Srivastava
import datetime
import logging
import pathlib
import sys
from typing import List, Dict
from abc import ABC
from abc import abstractmethod


# pylint: disable=too-many-public-methods
class IClientManager(ABC):
    @staticmethod
    def configure_logger(log_level, prefix_log_file: str = "daily_short"):
        # Setup logging
        # create a directory logs if it does not exist
        pathlib.Path.mkdir(pathlib.Path("logs"), exist_ok=True)
        # Create a filename suffixed with current date DDMMYY format with
        # current date inside logs directory
        log_file = pathlib.Path("logs") / (
            f"{prefix_log_file}_{datetime.datetime.now().strftime('%Y%m%d')}.log"
        )
        # pylint: disable=line-too-long
        logging.basicConfig(
            format="%(asctime)s.%(msecs)d %(filename)s:%(lineno)d:%(funcName)s() %(levelname)s %(message)s",
            datefmt="%A,%d/%m/%Y|%H:%M:%S",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_file),
            ],
            level=log_level,
        )

    @abstractmethod
    def login(self):
        raise NotImplementedError

    @abstractmethod
    def get_option_chain(self, exch: str, symbol: str, expire: int):
        raise NotImplementedError

    @abstractmethod
    def get_expiry(self, exch: str, symbol: str):
        raise NotImplementedError

    @abstractmethod
    def place_order(self, **order):
        raise NotImplementedError

    @abstractmethod
    def fetch_order_status(self, req_list: List):
        raise NotImplementedError

    @abstractmethod
    def modify_order(self, **order):
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, **order):
        raise NotImplementedError

    @abstractmethod
    def get_tradebook(self):
        raise NotImplementedError

    @abstractmethod
    def order_book(self):
        raise NotImplementedError

    @abstractmethod
    def positions(self):
        raise NotImplementedError

    @abstractmethod
    def cancel_bulk_order(self, exch_order_ids: List):
        raise NotImplementedError

    # pylint: disable=invalid-name
    @abstractmethod
    def Request_Feed(self, method: str, operation: str, req_list: List):
        raise NotImplementedError

    @abstractmethod
    def connect(self, wspayload: Dict):
        raise NotImplementedError

    @abstractmethod
    def error_data(self, err: any):
        raise NotImplementedError

    @abstractmethod
    def close_data(self):
        raise NotImplementedError

    @abstractmethod
    def receive_data(self, msg: any):
        raise NotImplementedError

    @abstractmethod
    def send_data(self, wspayload: any):
        raise NotImplementedError

    @abstractmethod
    def get_pnl_summary(self, tag: str = None):
        raise NotImplementedError

    @abstractmethod
    def get_todays_tags(self):
        raise NotImplementedError

    @abstractmethod
    def fetch_market_depth(self, req_list: List):
        raise NotImplementedError

    @abstractmethod
    # pylint: disable=too-many-arguments
    def historical_data(
        self,
        exch: str,
        exchange_segment: str,
        scrip_code: int,
        time_val: str,
        from_val: str,
        to_val: str,
    ):
        raise NotImplementedError
