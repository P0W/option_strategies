## Author : Prashant Srivastava
## Last Modified Date  : Dec 25th, 2022

from py5paisa import FivePaisaClient
from py5paisa.const import TODAY_TIMESTAMP
from py5paisa import strategy
import re
import math
import datetime
import time
import logging
import json
import argparse
import threading
from typing import Any


## Setup logging
logging.basicConfig(
    filename="daily_logs.txt",
    filemode="a",
    format="%(asctime)s.%(msecs)d %(funcName)20s() %(levelname)s %(message)s",
    datefmt="%A,%d/%m/%Y|%H:%M:%S",
    level=logging.DEBUG,
)

## Some handy day separater tag as title
logging.info(
    "STARTING ALGO TRADING WEEKLY OTPTIONS DATED: |%s|" % datetime.datetime.now()
)

logger = logging.getLogger(__name__)

## Globals - Refactor someday
QTY = 100
SL_FACTOR = 1.55  # 55 %
CLOSEST_PREMINUM = 7.0
INDEX_OPTION = "NIFTY"
EXPIRY_DAY = 0
client = None


def login(cred_file: str):
    global client
    with open(cred_file) as cred_fh:
        cred = json.load(cred_fh)

    client = FivePaisaClient(
        email=cred["email"], passwd=cred["passwd"], dob=cred["dob"], cred=cred
    )
    client.login()


def get_current_expiry(index: str) -> int:
    logger.info("Pulling the current expiry timestamp")
    all_nifty_expiry = client.get_expiry(exch="N", symbol=index)["Expiry"]
    date_pattern = re.compile("/Date\((\d+).+?\)/")
    min_diff = math.inf
    this_expiry = TODAY_TIMESTAMP
    for expiry in all_nifty_expiry:
        st = date_pattern.search(expiry["ExpiryDate"])
        if st:
            timestamp = int(st.group(1))
            diff = timestamp - TODAY_TIMESTAMP
            if min_diff > diff:
                min_diff = diff
                this_expiry = timestamp
    return this_expiry


def straddle_strikes(index: str) -> dict[str, Any]:
    this_expiry = get_current_expiry(index)
    contracts = client.get_option_chain(exch="N", symbol=index, expire=this_expiry)[
        "Options"
    ]
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

    logger.info("Minimum CE/PE Difference = %f" % min_diff)
    return {
        "ce_code": ce_strikes[atm]["code"],
        "ce_ltp": ce_strikes[atm]["ltp"],
        "ce_name": ce_strikes[atm]["name"],
        "pe_code": pe_strikes[atm]["code"],
        "pe_ltp": pe_strikes[atm]["ltp"],
        "pe_name": pe_strikes[atm]["name"],
    }


def strangle_strikes(closest_price_thresh: float, index: str) -> dict[str, Any]:
    this_expiry = get_current_expiry(index)
    logger.info(
        "Finding closest strikes to premium %f from expiry timestamp %d"
        % (CLOSEST_PREMINUM, this_expiry)
    )
    contracts = client.get_option_chain(exch="N", symbol=index, expire=this_expiry)[
        "Options"
    ]
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

    logger.info("Minimum CE Difference = %f" % min_ce_diff)
    logger.info("Minimum PE Difference = %f" % min_pe_diff)
    return {
        "ce_code": ce_code,
        "ce_ltp": ce_ltp,
        "ce_name": ce_name,
        "pe_code": pe_code,
        "pe_ltp": pe_ltp,
        "pe_name": pe_name,
    }


def place_short(strikes: dict, tag: str) -> None:
    for item in ["ce", "pe"]:
        price = 0.0  # strikes["%s_ltp" % item] # Market Order if price =0.0
        textinfo = """client.place_order(OrderType='S', 
                                        Exchange='N', 
                                        ExchangeType='D', 
                                        ScripCode=%d,
                                        Qty=QTY,
                                        Price=%f, IsIntraday=True,
                                        RemoteOrderID=%s)""" % (
            strikes["%s_code" % item],
            price,
            tag,
        )
        logger.info(textinfo)
        order_status = client.place_order(
            OrderType="S",
            Exchange="N",
            ExchangeType="D",
            ScripCode=strikes["%s_code" % item],
            Qty=QTY,
            Price=price,
            IsIntraday=True,
            RemoteOrderID=tag,
        )
        if order_status["Message"] == "Success":
            logger.info("%s_done" % item)


def place_short_stop_loss(tag: str) -> None:
    logger.info("Fetching order status for %s" % tag)
    id = []
    while len(id) != 2:
        r = client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
            "OrdStatusResLst"
        ]
        for order in r:
            eoid = order["ExchOrderID"]
            logger.info("ExchOrderID: %d" % eoid)
            if eoid != "":
                id.append(eoid)
        logger.info("Waiting for order execution")
        time.sleep(5)

    logger.info("Fetching TradeBookDetail for %s" % tag)
    trdbook = client.get_tradebook()["TradeBookDetail"]
    max_premium = 0.0
    for eoid in id:
        for trade in trdbook:
            if eoid == int(trade["ExchOrderID"]):
                scrip = trade["ScripCode"]
                logger.info(
                    "Matched for ExchOrderID: %d for Scrip: %d. Placing Stop Loss at %f times"
                    % (eoid, scrip, SL_FACTOR)
                )
                qty = trade["Qty"]
                avgprice = trade["Rate"]
                max_premium += avgprice * qty
                sl = int(avgprice * SL_FACTOR)
                higher_price = sl + 0.5
                logger.info(
                    "Placing order ScripCode=%d QTY=%d Trigger Price = %f Stop Loss Price = %f"
                    % (scrip, qty, sl, higher_price)
                )
                logger.info("USING STOPLOSS TAG:%s" % ("sl" + tag))
                order_status = client.place_order(
                    OrderType="B",
                    Exchange="N",
                    ExchangeType="D",
                    ScripCode=scrip,
                    Qty=qty,
                    Price=higher_price,
                    StopLossPrice=sl,
                    IsIntraday=True,
                    RemoteOrderID="sl" + tag,
                )
                if order_status["Message"] == "Success":
                    logger.info("Placed for %d" % scrip)
    logger.info("Collecting Maximum Premium of :%f INR" % max_premium)


def debug_status(tag: str) -> None:
    r = client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
        "OrdStatusResLst"
    ]
    print(json.dumps(r, indent=2))
    trdbook = client.get_tradebook()["TradeBookDetail"]
    print(json.dumps(trdbook, indent=2))


def pnl() -> float:
    positions = client.positions()
    # print(json.dumps(positions, indent=2))
    mtom = 0.0
    for item in positions:
        mtom += item["MTOM"]
    return mtom


def squareoff(tag: str) -> None:
    id = []
    r = client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
        "OrdStatusResLst"
    ]
    for order in r:
        eoid = order["ExchOrderID"]
        if eoid != "":
            id.append(eoid)
    trdbook = client.get_tradebook()["TradeBookDetail"]
    for eoid in id:
        for trade in trdbook:
            if eoid == int(trade["ExchOrderID"]):
                buysell_type = "B"
                intra = trade["DelvIntra"]
                scrip = trade["ScripCode"]
                qty = trade["Qty"]
                segment = trade["ExchType"]
                order_status = client.place_order(
                    OrderType=buysell_type,
                    Exchange="N",
                    ExchangeType=segment,
                    ScripCode=scrip,
                    Qty=qty,
                    Price=0,
                    IsIntraday=True,
                    remote_order_id=tag,
                )
            else:
                continue


def day_over() -> bool:
    ## Look for 15:20 on non expiry,
    ## leave to epire worthless on expiry day
    current_time = datetime.datetime.now()

    if (
        current_time.weekday != EXPIRY_DAY
        and current_time.hour >= 15
        and current_time.minute >= 20
    ):
        return True
    return False


def monitor(target: float, tag: str, log_only: bool = True) -> None:
    def poll():
        while not day_over():
            mtom = pnl()
            if not log_only and mtom >= target:
                ## TARGET ACCHEIVED
                ## Sqaure off both legs
                squareoff(tag=tag)
            logger.info("MTM = %.2f" % mtom)
            time.sleep(5)
        logger.info("Not Monitoring Day Over!")

    th = threading.Thread(target=poll, args=())
    th.start()
    th.join()
    return


def main(args) -> None:
    global CLOSEST_PREMINUM, SL_FACTOR, QTY, INDEX_OPTION, EXPIRY_DAY
    now = int(datetime.datetime.now().timestamp())
    tag = "p0wss%d" % now
    CLOSEST_PREMINUM = args.closest_premium
    SL_FACTOR = args.stop_loss_factor
    QTY = args.quantity
    INDEX_OPTION = args.index
    monitor_tag = None

    login(cred_file=args.creds)

    if args.tag != "":
        debug_status(tag=args.tag)
        return
    elif args.pnl:
        mtom = pnl()
        logger.info("MTM = %.2f" % mtom)
        return

    logger.info("USING INDEX :%s" % INDEX_OPTION)
    logger.info("USING CLOSEST PREMINUM :%f" % CLOSEST_PREMINUM)
    logger.info("USING SL FACTOR:%f" % SL_FACTOR)
    logger.info("USING QTY:%d" % QTY)
    logger.info("USING CURRENT TIMESTAMP TAG:%s" % tag)
    strangles = strangle_strikes(
        closest_price_thresh=CLOSEST_PREMINUM, index=INDEX_OPTION
    )
    straddles = straddle_strikes(index=INDEX_OPTION)

    symbol_pattern = "%s\s(\d+)\s" % INDEX_OPTION
    logger.info("Symbol Pattern %s" % symbol_pattern)
    st = re.search(symbol_pattern, straddles["ce_name"])
    if st:
        EXPIRY_DAY = int(st.group(1))
    logger.info("Expiry day:%d" % EXPIRY_DAY)

    logger.info("Obtained Strangle Strikes:%s" % json.dumps(strangles, indent=2))
    logger.info("Obtained Straddle Strikes:%s" % json.dumps(straddles, indent=2))

    if not args.show_strikes_only and args.tag == "":
        if args.strangle:
            place_short(strangles, tag)
            place_short_stop_loss(tag)
            monitor_tag = tag
        if args.straddle:
            place_short(straddles, tag)
            place_short_stop_loss(tag)
            monitor_tag = tag
    if args.monitor_target > 0.0:
        if args.tag != "":
            monitor_tag = args.tag
        if not monitor_tag:
            monitor(target=args.mmonitor_target, tag=monitor_tag, log_only=False)
        else:
            logger.info("No recent order, please provide a tag")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--creds",
        required=False,
        default="creds.json",
        type=str,
        help="Credentials file for login to 5paisa account",
    )
    parser.add_argument(
        "-s",
        "--show-strikes-only",
        action="store_true",
        help="Show strikes only, do not place order",
    )
    parser.add_argument(
        "--monitor-target",
        required=False,
        type=float,
        default=-1.0,
        help="Keep polling for given target amount",
    )
    parser.add_argument(
        "-cp",
        "--closest_premium",
        default=7.0,
        type=float,
        required=False,
        help="Search the strangle strikes for provided closest premium",
    )
    parser.add_argument(
        "-sl",
        "--stop_loss_factor",
        default=1.55,
        type=float,
        required=False,
        help="Percent above the placed price for stop loss",
    )
    parser.add_argument(
        "-q",
        "--quantity",
        default=100,
        type=int,
        required=False,
        help="Quantity to short for Nifty (Lot size =50), for 1 lot say 50",
    )
    parser.add_argument(
        "--index",
        default="NIFTY",
        type=str,
        required=False,
        help="Index to trade (NIFTY/BANKNIFTY)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="",
        required=False,
        help="Tag to print status of last order for given tag, if combined with --monitor_target it polls the position for given tag",
    )
    parser.add_argument("--pnl", action="store_true", help="Show current PNL")
    parser.add_argument("--strangle", action="store_true", help="Place Strangle")
    parser.add_argument("--straddle", action="store_true", help="Place Straddle")
    args = parser.parse_args()
    logger.info("Command Line Arguments : %s" % json.dumps(vars(args), indent=2))
    main(args)
