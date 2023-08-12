## Author : Prashant Srivastava

import datetime
import json
import logging
import sys
import pathlib
from py5paisa import FivePaisaClient
import pyotp


def login(cred_file: str = "creds.json"):
    with open(cred_file) as cred_fh:
        cred = json.load(cred_fh)

    client = FivePaisaClient(cred)
    totp = pyotp.TOTP(cred["totp_secret"])
    client.get_totp_session(cred["clientcode"], totp.now(), cred["pin"])
    return client


def login_from_json(cred: dict):
    client = FivePaisaClient(
        email=cred["email"], passwd=cred["passwd"], dob=cred["dob"], cred=cred
    )
    client.login()
    return client


def configure_logger(log_level):
    ## Setup logging
    ## create a directory logs if it does not exist
    pathlib.Path.mkdir(pathlib.Path("logs"), exist_ok=True)
    ## Create a filename suffixed with current date DDMMYY format with current date inside logs directory
    log_file = pathlib.Path("logs") / (
        "daily_short_%s.log" % datetime.datetime.now().strftime("%Y%m%d")
    )
    logging.basicConfig(
        format="%(asctime)s.%(msecs)d %(funcName)20s() %(levelname)s %(message)s",
        datefmt="%A,%d/%m/%Y|%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
        level=log_level,
    )
