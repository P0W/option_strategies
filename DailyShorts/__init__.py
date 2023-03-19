## Author : Prashant Srivastava
## Last Modified Date  : March 19th, 2023

import datetime
import logging

import azure.functions as func

import argparse
import daily_short

daily_short.configure_logger("DEBUG")

args = argparse.Namespace(
    quantity=400,
    closest_premium=7.0,
    stop_loss_factor=1.55,
    index="NIFTY",
    log_level="DEBUG",
    creds="creds.json",
    show_strikes_only=False,
    monitor_target=False,
    tag="",
    pnl=False,
    straddle=False,
    strangle=True,
)


def main(mytimer: func.TimerRequest) -> None:
    utc_timestamp = (
        datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
    )

    if mytimer.past_due:
        logging.info("Missed placing strategy at 9:31 am today")

    logging.info("Running strategy at %s", utc_timestamp)
    daily_short.main(args)
