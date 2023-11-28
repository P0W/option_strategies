## Strategy Brief:
## Place straddles
## Place stop loss as OTM strangles for breakeven strikes
## Desired stop loss is 35% of the OTM strikes ltp
## This eliminates the risk of swings, which hits stop loss on straddle legs and then reverses
import datetime
import json
import math
import re
from typing import Any, Dict
from src.common.strikes_manager import StrikesManager
from src.clients.client_5paisa import Client as Client5Paisa
from src.common.order_manager import OrderManager

import logging
import argparse


Client5Paisa.configure_logger(logging.INFO, "straddle")

## set up arg for accepting index
parser = argparse.ArgumentParser()
parser.add_argument(
    "--index", help="Index to trade (NIFTY/FINNIFTY/BANKNIFTY)", required=True, type=str
)
## add qty
parser.add_argument("--qty", help="Quantity to trade", required=True, type=int)
## add stop loss
parser.add_argument("--sl", help="Stop loss", required=True, type=float)

args = parser.parse_args()


class StraddleIronCondor:
    def __init__(self, client: Client5Paisa, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.strikes_manager = StrikesManager(self.client, self.config)
        self.logger.info("Initialized straddle")

    def get_current_expiry(self, index: str) -> int:
        self.logger.debug("Pulling the current expiry timestamp")
        all_nifty_expiry = self.client.get_expiry(
            exch=self.strikes_manager.get_exchange(index), symbol=index
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

    def search_strike(
        self, index: str, strike: float, option_type: str
    ) -> Dict[str, Any]:
        """
        Search for the strike and get the code and ltp
        """
        this_expiry = self.get_current_expiry(index)
        contracts = self.client.get_option_chain(
            exch=self.strikes_manager.get_exchange(index),
            symbol=index,
            expire=this_expiry,
        )["Options"]
        for contract in contracts:
            ltp = contract["LastRate"]
            code = contract["ScripCode"]
            name = contract["Name"]
            ctype = contract["CPType"]
            opt_strike = contract["StrikeRate"]
            if opt_strike == strike and ctype == option_type:
                return {"ltp": ltp, "code": code, "name": name}
        return {}

    def get_strikes(self, index: str, round_to: int = 100) -> Dict[str, Any]:
        straddleStrikes = self.strikes_manager.straddle_strikes(index)
        premium = straddleStrikes["ce_ltp"] + straddleStrikes["pe_ltp"]
        ## Fomr ce_name and pe_name of the form "BANKNIFTY DD MMM YYYY CE/PE Strike" get strike
        ce_strike = straddleStrikes["ce_name"].split(" ")[-1]
        pe_strike = straddleStrikes["pe_name"].split(" ")[-1]
        ## Substract premium from strike to get breakeven
        self.logger.info("Straddle Premium %.2f", premium)
        self.logger.info("Straddle Strikes %s %s", ce_strike, pe_strike)
        ce_breakeven = float(ce_strike) + premium
        pe_breakeven = float(pe_strike) - premium
        self.logger.info("Straddle Breakeven %.2f %.2f", ce_breakeven, pe_breakeven)
        ## Find the nearest strike to the breakeven round it off to the nearest round_to
        ce_breakeven = round(ce_breakeven / round_to) * round_to
        pe_breakeven = round(pe_breakeven / round_to) * round_to
        self.logger.info("Straddle Breakeven %.2f %.2f", ce_breakeven, pe_breakeven)
        ## Search for the strike and get the code
        ce_breakeven = self.search_strike(index, ce_breakeven, "CE")
        pe_breakeven = self.search_strike(index, pe_breakeven, "PE")
        return {
            "straddle": straddleStrikes,
            "sl": {
                "ce_code": ce_breakeven["code"],
                "pe_code": pe_breakeven["code"],
                "ce_name": ce_breakeven["name"],
                "pe_name": pe_breakeven["name"],
                "ce_ltp": ce_breakeven["ltp"],
                "pe_ltp": pe_breakeven["ltp"],
            },
        }

    def get_strikes_v2(self, index: str) -> Dict[str, Any]:
        straddleStrikes = self.strikes_manager.straddle_strikes(index)
        ## Get 35% of the ce_ltp and pe_ltp
        ce_sl = straddleStrikes["ce_ltp"] * 0.35 / 1.3
        pe_sl = straddleStrikes["pe_ltp"] * 0.35 / 1.3
        ## Find min of ce_sl and pe_sl
        sl = min(ce_sl, pe_sl)
        logging.info("Minimum SL %.2f", sl)
        ## get strangle strikes
        strangleStrikes_sl = self.strikes_manager.strangle_strikes(sl, index)
        return {"straddle": straddleStrikes, "strangle_sl": strangleStrikes_sl}


if __name__ == "__main__":
    client = Client5Paisa()
    client.login()
    index = args.index
    config = {"QTY": int(args.qty), "SL_FACTOR": float(args.sl)}
    straddleIronCondor = StraddleIronCondor(client, config)
    order_manager = OrderManager(client, config=config)
    if args.index == "NIFTY":
        round_to = 50
    elif args.index == "BANKNIFTY":
        round_to = 100
    elif args.index == "FINNIFTY":
        round_to = 50
    strikes = straddleIronCondor.get_strikes(index, round_to)
    now = int(datetime.datetime.now().timestamp())
    tag = f"p0wsic{now}"
    sl_tag = f"slp0wsic{now}"
    qty = config["QTY"]

    logging.info("Straddle strikes are %s", json.dumps(strikes, indent=2))

    order_manager.place_short(strikes["straddle"], tag)

    for optType in ["ce", "pe"]:
        scrip_code = strikes["sl"][f"{optType}_code"]
        trigger_price = order_manager.square_off_price(
            strikes["sl"][f"{optType}_ltp"] * config["SL_FACTOR"]
        )
        sl_price = trigger_price + 0.5
        order_status = client.place_order(
            OrderType="B",
            Exchange="N",
            ExchangeType="D",
            ScripCode=scrip_code,
            Qty=qty,
            Price=sl_price,
            StopLossPrice=trigger_price,
            IsIntraday=True,
            RemoteOrderID=sl_tag,
        )
