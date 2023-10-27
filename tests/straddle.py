import time
from src.common.strikes_manager import StrikesManager
from src.clients.client_5paisa import Client as Client5Paisa
from src.common.live_feed_manager import LiveFeedManager

import logging
import argparse
import os
import threading

Client5Paisa.configure_logger(logging.INFO)

## set up arg for accepting index
parser = argparse.ArgumentParser()
parser.add_argument("--index", help="Index to trade", default="NIFTY")
args = parser.parse_args()


def callback(ohlcvt: dict, user_data: dict = None):
    user_data[ohlcvt["code"]] = ohlcvt
    ## if two keys are present, then calculate the straddle price
    if len(user_data) == 2:
        ## diff the two close prices in user_data
        price_diff = abs(
            user_data[straddleStrikes["ce_code"]]["c"]
            - user_data[straddleStrikes["pe_code"]]["c"]
        )
        premium = (
            user_data[straddleStrikes["ce_code"]]["c"]
            + user_data[straddleStrikes["pe_code"]]["c"]
        )
        max_time = max(
            user_data[straddleStrikes["ce_code"]]["t"],
            user_data[straddleStrikes["pe_code"]]["t"],
        )
        ## convert utc to ist in HH:MM:SS format
        max_time = time.strftime("%H:%M:%S", time.localtime(max_time))
        logging.info(
            f"Straddle Premium %.2f Difference %.2f at %s",
            premium,
            price_diff,
            max_time,
        )


def fetch_straddle_strike(
    index: str, live_feed_manager: LiveFeedManager, strikes_manager: StrikesManager
):
    logging.debug("Starting straddle strike fetcher")
    straddleStrikes = strikes_manager.straddle_strikes(index)
    live_feed_manager.monitor(
        [straddleStrikes["ce_code"], straddleStrikes["pe_code"]],
        on_scrip_data=callback,
        user_data={},
    )
    while live_feed_manager.is_active():
        time.sleep(10)
        newStrikes = strikes_manager.straddle_strikes(index=index)
        if (
            newStrikes["ce_code"] != straddleStrikes["ce_code"]
            or newStrikes["pe_code"] != straddleStrikes["pe_code"]
        ):
            straddleStrikes = newStrikes
            live_feed_manager.unsubscribe(
                [straddleStrikes["ce_code"], straddleStrikes["pe_code"]]
            )
            logging.debug(
                f"New strikes are {straddleStrikes}, original monitoring no longer valid"
            )
            live_feed_manager.stop()
            break


if __name__ == "__main__":
    client = Client5Paisa()
    client.login()
    index = args.index
    config = {}
    strikes_manager = StrikesManager(client, config)
    current_expiry = strikes_manager.get_current_expiry(index)

    ## Create a thread to fetch new straddle strike every 5 minutes
    straddleStrikes = strikes_manager.straddle_strikes(index)
    ## get pid of the running script
    pid = os.getpid()
    logging.debug("PID of the script is %d", pid)
    ## Create a live feed manager
    live_feed_manager = LiveFeedManager(client, config)
    threading.Thread(
        target=fetch_straddle_strike,
        args=(
            index,
            live_feed_manager,
            strikes_manager,
        ),
    ).start()

    logging.debug(f"Current expiry for {index} is {straddleStrikes}")
