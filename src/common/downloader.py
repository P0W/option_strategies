"""
This script downloads the historical data for the current expiry contracts of all the indices
"""
import datetime
import logging
import os
import pathlib
import sys

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from src.clients.client_5paisa import Client as Client5Paisa

import strikes_manager


def write_to_blob(dataframe, blob_name, use_connection_string=False):
    """Write the dataframe to a blob in Azure Storage"""
    account_url, container_name = (
        "https://stockstrategies.blob.core.windows.net/",
        "strikes-data",
    )
    if use_connection_string:
        # Create a blob service client using the connection string
        blob_service_client = BlobServiceClient.from_connection_string(
            conn_str=""
        )
    else:
        # Create a default credential
        credential = DefaultAzureCredential()

        # Create a blob service client
        blob_service_client = BlobServiceClient(
            account_url=account_url, credential=credential
        )

    # Get a reference to the container
    container_client = blob_service_client.get_container_client(container_name)
    ## if not exists, create the container
    if not container_client.exists():
        logging.info("Creating container %s", container_name)
        container_client.create_container()

    # Get a reference to the blob
    blob_client = container_client.get_blob_client(blob_name)
    if not blob_client.exists():
        logging.info("Creating blob %s", blob_name)
        # Convert the DataFrame to CSV and get the CSV data as a string
        csv_data = dataframe.to_csv(index=False)
        blob_client.upload_blob(csv_data)


def main():
    """The main function"""
    today = datetime.datetime.now()
    today = today.strftime("%Y-%m-%d")
    Client5Paisa.configure_logger(logging.INFO, "downloader")
    client = Client5Paisa("../../creds.json")
    client.login()
    strike_mgr = strikes_manager.StrikesManager(
        client=client, config={"indices_info": "../../indices_info.json"}
    )

    for index, exchange in [
        # ("NIFTY", "N"),
        ("BANKNIFTY", "N"),
        # ("FINNIFTY", "N"),
        # ("SENSEX", "B"),
        # ("BANKEX", "B"),
        # ("MIDCPNIFTY", "N"),
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
            write_to_blob(dataframe, f"{today}/{index}/{file_name}.csv", True)
            logging.info("Downloaded data for %s", file_name)
        ## remove the folder recursively
        pathlib.Path(f"data/{today}/{index}").rmdir()


if __name__ == "__main__":
    main()
    sys.exit(0)
