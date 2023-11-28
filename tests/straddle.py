## Strategy Brief:
## Monitor the straddle premium difference for given threshold
## If the premium difference is less than threshold for given duration,
## then place straddle order
## If the premium difference is greater than threshold, then keep monitoring
## until is comes below threshold else exit if straddle strikes change
import datetime
import json
import time
from typing import Dict
from src.common.strikes_manager import StrikesManager
from src.clients.client_5paisa import Client as Client5Paisa
from src.common.live_feed_manager import LiveFeedManager
from src.common.order_manager import OrderManager

import logging
import argparse
import os
import threading

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
## diff threshold
parser.add_argument(
    "--diff", help="Difference threshold", required=False, default=-1.0, type=float
)
## add wait time
parser.add_argument(
    "--wait", help="Wait time in seconds", required=False, default=60, type=int
)
args = parser.parse_args()


def callback(ohlcvt: dict, user_data: Dict = None):
    if "strikes" not in user_data:
        user_data["strikes"] = {}
    strikes_data = user_data["strikes"]
    strikes_data[ohlcvt["code"]] = ohlcvt
    ## if two keys are present, then calculate the straddle price
    if len(strikes_data) == 2:
        ## diff the two close prices in user_data
        s1, s2 = strikes_data.keys()
        price_diff = abs(strikes_data[s1]["c"] - strikes_data[s2]["c"])
        premium = strikes_data[s1]["c"] + strikes_data[s2]["c"]
        max_time = max(strikes_data[s1]["t"], strikes_data[s2]["t"])
        ## convert utc to ist in HH:MM:SS format
        if max_time > 0:
            max_time = time.strftime("%H:%M:%S", time.localtime(max_time))
            user_data["max_time"] = max_time
            user_data["price_diff"] = price_diff
            user_data["premium"] = premium
            logging.info(
                f"Straddle Premium %.2f Difference %.2f at %s",
                premium,
                price_diff,
                max_time,
            )
        else:
            logging.error("Invalid timestamp %d", max_time)


def fetch_straddle_strike(
    index: str,
    live_feed_manager: LiveFeedManager,
    strikes_manager: StrikesManager,
    evt: threading.Event,
    user_data: Dict = None,
):
    logging.debug("Starting straddle strike fetcher")
    straddleStrikes = strikes_manager.straddle_strikes(index)
    live_feed_manager.monitor(
        [straddleStrikes["ce_code"], straddleStrikes["pe_code"]],
        on_scrip_data=callback,
        user_data=user_data,
    )
    curr_time = None
    while live_feed_manager.is_active():
        time.sleep(1)
        newStrikes = strikes_manager.straddle_strikes(index)
        if (
            newStrikes["ce_code"] != straddleStrikes["ce_code"]
            or newStrikes["pe_code"] != straddleStrikes["pe_code"]
        ):
            straddleStrikes = newStrikes
            live_feed_manager.unsubscribe(
                [straddleStrikes["ce_code"], straddleStrikes["pe_code"]]
            )
            logging.info(
                f"New strikes are {straddleStrikes}, original monitoring no longer valid"
            )
            live_feed_manager.stop()
            break
        elif "price_diff" in user_data:
            ## 5% of premium is the threshold
            if user_data["diff_threshold"] < 0:
                threshold = user_data["premium"] * 0.05
            else:
                threshold = user_data["diff_threshold"]
            if user_data["price_diff"] <= threshold:
                if not curr_time:  ## For the first time
                    curr_time = datetime.datetime.now()
                    logging.info(
                        "Straddle premium difference is less than %f, waiting for %d seconds",
                        threshold,
                        user_data["wait"],
                    )
                elif datetime.datetime.now() - curr_time > datetime.timedelta(
                    seconds=user_data["wait"]
                ):
                    logging.info(
                        "Straddle premium difference is less than %f for %d seconds",
                        threshold,
                        user_data["wait"],
                    )
                    evt.set()
                    live_feed_manager.stop()
                    break
            else:
                ## Reset the curr_time
                curr_time = None
    if not curr_time:
        ## Release other thread, if curr_time is None,
        # then straddle premium difference is greater than 15
        evt.set()


def place_straddle(evt: threading.Event, user_data: Dict = None):
    logging.info(
        "Waiting for straddle premium difference to be less than %s for %d seconds",
        user_data["diff_threshold"],
        user_data["wait"],
    )
    evt.wait()
    if user_data["diff_threshold"] < 0:
        threshold = user_data["premium"] * 0.05
    else:
        threshold = user_data["diff_threshold"]
    if "strikes" not in user_data or user_data["price_diff"] > threshold:
        logging.error("Cannot place straddle order %s", json.dumps(user_data, indent=2))
        return
    logging.info(
        "Straddle premium difference is less than %f for %d seconds, placing straddle order",
        threshold,
        user_data["wait"],
    )
    strikes_data = user_data["strikes"]
    s1, s2 = strikes_data.keys()
    straddles = {
        "ce_code": s1,
        "ce_ltp": strikes_data[s1]["c"],
        "ce_name": s1,
        "pe_code": s2,
        "pe_ltp": strikes_data[s2]["c"],
        "pe_name": s2,
    }
    ## place straddle order
    now = int(datetime.datetime.now().timestamp())
    tag = f"p0wss{now}"
    logging.info("Placing straddle order with tag %s", tag)
    logging.info("Straddle strikes are %s", json.dumps(straddles, indent=2))

    order_mgr = OrderManager(
        client=client,
        config=config,
    )
    order_mgr.place_short(straddles, tag)
    order_mgr.place_short_stop_loss_v2(tag)


if __name__ == "__main__":
    client = Client5Paisa()
    client.login()
    index = args.index
    config = {"QTY": int(args.qty), "SL_FACTOR": float(args.sl)}
    if args.diff < 0:
        logging.info("Using dynamic threshold of 5% of straddle premium")
    user_data = {"diff_threshold": float(args.diff), "wait": int(args.wait)}
    strikes_manager = StrikesManager(client)

    ## Create a event to notify when staddle premium difference is less than 15
    signal_short = threading.Event()

    ## Create a thread to fetch new straddle strike every 5 minutes
    ## get pid of the running script
    pid = os.getpid()
    logging.info("PID of the script is %d", pid)
    ## Create a live feed manager
    live_feed_manager = LiveFeedManager(client)
    monitor_thread = threading.Thread(
        target=fetch_straddle_strike,
        args=(
            index,
            live_feed_manager,
            strikes_manager,
            signal_short,
            user_data,
        ),
    )
    order_thread = threading.Thread(
        target=place_straddle,
        args=(
            signal_short,
            user_data,
        ),
    )

    order_thread.start()
    monitor_thread.start()

    ## Wait for the thread to finish
    monitor_thread.join()
    order_thread.join()
