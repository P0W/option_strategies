# Author : Prashant Srivastava

# pylint: disable=unsubscriptable-object

import datetime
import json
import logging
import math
import re
from typing import Any, Dict

import pandas as pd

from src.clients.iclientmanager import IClientManager


class StrikesManager:
    TODAY_TIMESTAMP = int(datetime.datetime.today().timestamp())

    def __init__(self, client: IClientManager, config: Dict = None) -> None:
        self.client = client
        self.logger = logging.getLogger(__name__)
        self.config = config
        indices_info_path = "indices_info.json"
        if "indices_info" in config:
            indices_info_path = config["indices_info"]
        ## load data from indices_info.json
        with open(indices_info_path, "r", encoding="utf-8") as json_file:
            self.indices_info = json.load(json_file)

    def get_exchange(self, index: str) -> str:
        return self.indices_info[index]["exchange"]

    def get_lot_size(self, index: str) -> int:
        return self.indices_info[index]["lot_size"]

    def get_tick_size(self, index: str) -> float:
        return self.indices_info[index]["tick_size"]

    def get_current_expiry(self, index: str) -> int:
        self.logger.debug("Pulling the current expiry timestamp")
        all_nifty_expiry = self.client.get_expiry(
            exch=self.get_exchange(index), symbol=index
        )["Expiry"]
        date_pattern = re.compile("/Date\\((\\d+).+?\\)/")
        min_diff = math.inf
        this_expiry = StrikesManager.TODAY_TIMESTAMP
        for expiry in all_nifty_expiry:
            search_text = date_pattern.search(expiry["ExpiryDate"])
            if search_text:
                timestamp = int(search_text.group(1))
                diff = timestamp - StrikesManager.TODAY_TIMESTAMP
                if min_diff > diff:
                    min_diff = diff
                    this_expiry = timestamp
        return this_expiry

    def straddle_strikes(self, index: str) -> Dict[str, Any]:
        this_expiry = self.get_current_expiry(index)
        contracts = self.client.get_option_chain(
            exch=self.get_exchange(index), symbol=index, expire=this_expiry
        )["Options"]
        ce_strikes = {}
        pe_strikes = {}
        for contract in contracts:
            ltp = contract["LastRate"]
            code = contract["ScripCode"]
            name = contract["Name"]
            ctype = contract["CPType"]
            strike = contract["StrikeRate"]
            if ltp > 0:
                if ctype == "CE":
                    ce_strikes[strike] = {"ltp": ltp, "code": code, "name": name}
                else:
                    pe_strikes[strike] = {"ltp": ltp, "code": code, "name": name}

        min_diff = math.inf
        atm = 0
        for key, value in ce_strikes.items():
            if key in pe_strikes:
                diff = abs(value["ltp"] - pe_strikes[key]["ltp"])
                if min_diff > diff:
                    min_diff = diff
                    atm = key

        self.logger.debug("Minimum CE/PE Difference = %f", min_diff)
        premium = (ce_strikes[atm]["ltp"] + pe_strikes[atm]["ltp"]) * self.get_lot_size(
            index
        )
        self.logger.debug("Straddle Premium = %f", premium)
        return {
            "ce_code": ce_strikes[atm]["code"],
            "ce_ltp": ce_strikes[atm]["ltp"],
            "ce_name": ce_strikes[atm]["name"],
            "pe_code": pe_strikes[atm]["code"],
            "pe_ltp": pe_strikes[atm]["ltp"],
            "pe_name": pe_strikes[atm]["name"],
        }

    def strangle_strikes(
        self, closest_price_thresh: float, index: str
    ) -> Dict[str, Any]:
        this_expiry = self.get_current_expiry(index)
        if "CLOSEST_PREMINUM" in self.config:
            closest_price_thresh = float(self.config["CLOSEST_PREMINUM"])
            self.logger.debug(
                "Finding closest strikes to premium %f from expiry timestamp %d",
                closest_price_thresh,
                this_expiry,
            )
        contracts = self.client.get_option_chain(
            exch=self.get_exchange(index), symbol=index, expire=this_expiry
        )["Options"]
        min_pe_diff = min_ce_diff = math.inf
        ce_code = -1
        pe_code = -1
        ce_ltp = 0.0
        pe_ltp = 0.0
        ce_name = ""
        pe_name = ""
        for contract in contracts:
            ltp = contract["LastRate"]
            code = contract["ScripCode"]
            name = contract["Name"]
            ctype = contract["CPType"]

            if ltp < closest_price_thresh:
                continue
            diff = ltp - closest_price_thresh
            if ctype == "CE" and min_ce_diff > diff:
                min_ce_diff = diff
                ce_code = code
                ce_ltp = ltp
                ce_name = name
            if ctype == "PE" and min_pe_diff > diff:
                min_pe_diff = diff
                pe_code = code
                pe_ltp = ltp
                pe_name = name

        self.logger.debug("Minimum CE Difference = %f", min_ce_diff)
        self.logger.debug("Minimum PE Difference = %f", min_pe_diff)
        premium = (ce_ltp + pe_ltp) * self.get_lot_size(index)
        self.logger.debug("Strangle Premium = %f", premium)
        return {
            "ce_code": ce_code,
            "ce_ltp": ce_ltp,
            "ce_name": ce_name,
            "pe_code": pe_code,
            "pe_ltp": pe_ltp,
            "pe_name": pe_name,
        }

    def get_indices(self):
        req_items = {999920000: "NIFTY", 999920005: "BANKNIFTY", 999920019: "INDIAVIX"}
        request_prices = list(
            map(
                lambda item: {
                    "Exchange": "N",
                    "ExchangeType": "D",
                    "ScripCode": item,
                },
                req_items.keys(),
            )
        )
        depth = self.client.fetch_market_depth(request_prices)["Data"]
        ltp_dict = {
            req_items[dep["ScripCode"]]: dep["LastTradedPrice"] for dep in depth
        }
        return ltp_dict
