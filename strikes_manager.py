## Author : Prashant Srivastava
## Last Modified Date  : Dec 25th, 2022

import datetime
import math
import logging
import re
from typing import Any


class StrikesManager:
    TODAY_TIMESTAMP = int(datetime.datetime.today().timestamp())

    def __init__(self, client, config: dict) -> None:
        self.client = client
        self.logger = logging.getLogger(__name__)
        self.config = config

    def get_current_expiry(self, index: str) -> int:
        self.logger.info("Pulling the current expiry timestamp")
        all_nifty_expiry = self.client.get_expiry(exch="N", symbol=index)["Expiry"]
        date_pattern = re.compile("/Date\((\d+).+?\)/")
        min_diff = math.inf
        this_expiry = StrikesManager.TODAY_TIMESTAMP
        for expiry in all_nifty_expiry:
            st = date_pattern.search(expiry["ExpiryDate"])
            if st:
                timestamp = int(st.group(1))
                diff = timestamp - StrikesManager.TODAY_TIMESTAMP
                if min_diff > diff:
                    min_diff = diff
                    this_expiry = timestamp
        return this_expiry

    def straddle_strikes(self, index: str) -> dict[str, Any]:
        this_expiry = self.get_current_expiry(index)
        contracts = self.client.get_option_chain(
            exch="N", symbol=index, expire=this_expiry
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
        for k, v in ce_strikes.items():
            if k in pe_strikes:
                diff = abs(v["ltp"] - pe_strikes[k]["ltp"])
                if min_diff > diff:
                    min_diff = diff
                    atm = k

        self.logger.info("Minimum CE/PE Difference = %f" % min_diff)
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
    ) -> dict[str, Any]:
        this_expiry = self.get_current_expiry(index)
        self.logger.info(
            "Finding closest strikes to premium %f from expiry timestamp %d"
            % (self.config["CLOSEST_PREMINUM"], this_expiry)
        )
        contracts = self.client.get_option_chain(
            exch="N", symbol=index, expire=this_expiry
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

        self.logger.info("Minimum CE Difference = %f" % min_ce_diff)
        self.logger.info("Minimum PE Difference = %f" % min_pe_diff)
        return {
            "ce_code": ce_code,
            "ce_ltp": ce_ltp,
            "ce_name": ce_name,
            "pe_code": pe_code,
            "pe_ltp": pe_ltp,
            "pe_name": pe_name,
        }
