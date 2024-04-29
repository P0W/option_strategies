"""
This script downloads the historical data for the current expiry contracts of all the indices
"""
import datetime
import logging
import pathlib
import sys

import pandas as pd
from src.clients.client_5paisa import Client as Client5Paisa

import strikes_manager


def main():
    """The main function"""
    today = datetime.datetime.now()
    today = today.strftime("%Y-%m-%d")
    Client5Paisa.configure_logger(logging.DEBUG, "downloader")
    client = Client5Paisa("../../creds.json")
    client.login()
    strike_mgr = strikes_manager.StrikesManager(
        client=client, config={"indices_info": "../../indices_info.json"}
    )

    for index, exchange in [
        ("NIFTY", "N"),
        ("BANKNIFTY", "N"),
        ("FINNIFTY", "N"),
        ("SENSEX", "B"),
        ("BANKEX", "B"),
        ("MIDCPNIFTY", "N"),
    ]:
        this_expiry = strike_mgr.get_current_expiry(index)
        contracts = client.get_option_chain(
            exch=exchange, symbol=index, expire=this_expiry
        )["Options"]
        past_date = datetime.datetime.now() - datetime.timedelta(days=1)
        ## create a date folder, if not exists
        pathlib.Path(f"data/{today}/{index}").mkdir(parents=True, exist_ok=True)
        for contract in contracts:
            dataframe = client.historical_data(
                exch=exchange,
                exchange_segment="D",
                scrip_code=contract["ScripCode"],
                time_val="1m",
                from_val=past_date,
                to_val=today,
            )
            ## if the dataframe is empty, continue
            if dataframe.empty:
                continue
            dataframe["Datetime"] = pd.to_datetime(dataframe["Datetime"])
            ## save as csv to data/contracts['Name'].csv
            file_name = contract["Name"].replace(" ", "_")
            dataframe.to_csv(f"data/{today}/{index}/{file_name}.csv", index=False)


if __name__ == "__main__":
    main()
    sys.exit(0)
