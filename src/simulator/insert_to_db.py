import datetime
import json
import logging
import time

import pandas as pd
import timeseriesdb

from src.clients.client_5paisa import Client
from src.common.strikes_manager import StrikesManager

Client.configure_logger(logging.INFO)
client = Client()
client.login()
logger = logging.getLogger(__name__)
strike_mgr = StrikesManager(client, {})


# pylint: disable=duplicate-code
def get_strikes_of_interest(index_info: dict):
    this_expiry = strike_mgr.get_current_expiry(index_info["index"])
    contracts = client.get_option_chain(
        exch="N", symbol=index_info["index"], expire=this_expiry
    )["Options"]
    ce_strikes = {}
    pe_strikes = {}
    codes_of_interest = []
    for contract in contracts:
        ltp = contract["LastRate"]
        code = contract["ScripCode"]
        name = contract["Name"]
        ctype = contract["CPType"]
        strike = contract["StrikeRate"]
        if (
            index_info["low"] <= ltp <= index_info["high"]
        ):  ## 5.0 is the minimum premium for a strike
            if ctype == "CE":
                ce_strikes[strike] = {"ltp": ltp, "code": code, "name": name}
                codes_of_interest.append(ce_strikes[strike])
            else:
                pe_strikes[strike] = {"ltp": ltp, "code": code, "name": name}
                codes_of_interest.append(pe_strikes[strike])

    logger.info(json.dumps(ce_strikes, indent=2, sort_keys=True))
    logger.info(json.dumps(pe_strikes, indent=2, sort_keys=True))
    return codes_of_interest


def insert_to_timescaledb(timescaledb: timeseriesdb.TimescaleDB, index_info: dict):
    codes_of_interest = get_strikes_of_interest(index_info)
    for scrip_details in codes_of_interest:
        seven_days_before = (
            datetime.datetime.now() - datetime.timedelta(weeks=2)
        ).strftime("%Y-%m-%d")
        end_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        data_frame = client.historical_data(
            "N", "D", scrip_details["code"], "1m", seven_days_before, end_date
        )
        # Convert the "Datetime" column to datetime objects
        data_frame["Datetime"] = pd.to_datetime(data_frame["Datetime"])

        # Convert Datetime column to UTC
        data_frame["Datetime"] = data_frame["Datetime"].dt.tz_localize(
            datetime.timezone.utc
        )
        logger.info("Inserting data into timescaledb %s", scrip_details["name"])
        start_time = time.time()
        timescaledb.insert_option_data_from_dataframe(data_frame, scrip_details["name"])
        end_time = time.time()
        logger.info("Time taken to insert data: %.2f", end_time - start_time)


if __name__ == "__main__":
    db_config = {
        "dbname": "option_db",
        "user": "admin",
        "password": "admin",
        "host": "localhost",
        "port": "5432",
    }
    timescale_db = timeseriesdb.TimescaleDB(db_config)
    # timescale_db.drop_database() # Uncomment this to drop the database
    timescale_db.create_database()
    timescale_db.create_tables()
    timescale_db.connect(db_config["dbname"])

    for indices in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
        index_config = {"index": indices.upper(), "high": 25, "low": 5}
        insert_to_timescaledb(timescale_db, index_config)
