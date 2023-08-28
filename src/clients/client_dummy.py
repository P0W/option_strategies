import json
import logging
import time

import websocket
from pymongo import MongoClient

from . import iclientmanager


# pylint: disable=too-many-public-methods
class Client(iclientmanager.IClientManager):
    def __init__(self, _file_name: str = "creds.json"):
        self.host = "localhost"
        self.port = 8765
        self.logger = logging.getLogger(__name__)

        # Connection parameters
        username = "root"
        password = "admin"
        host = "localhost"
        port = 27017
        auth_source = "admin"  # The authentication database

        # Create the connection URL with authentication
        connection_url = f"mongodb://{username}:{password}@{host}:{port}/{auth_source}"
        self.mongo_client = MongoClient(connection_url)
        # Create a database
        self.database = self.mongo_client["test-database"]
        # Create a collection
        self.collection = self.database["orders"]
        self.web_url = None
        self.web_sock = None

    # pylint: disable=invalid-name
    def Request_Feed(self, _method: str, operation: str, req_list: list):
        payload = {"Method": "mf", "Operation": operation, "MarketFeedData": req_list}
        return payload

    def connect(self, wspayload: dict):
        self.logger.info("Connecting to %s:%d", self.host, self.port)
        try:
            self.web_url = f"ws://{self.host}:{self.port}/"

            def on_open(web_sock):
                self.logger.info("Streaming Started from %s", self.web_url)
                try:
                    web_sock.send(json.dumps(wspayload))
                except Exception as exp:
                    self.logger.error(exp)

            self.web_sock = websocket.WebSocketApp(self.web_url)
            self.web_sock.on_open = on_open
        except Exception as e:
            self.logger.error(e)

    def send_data(self, wspayload: any):
        try:
            self.web_sock.send(json.dumps(wspayload))
        except Exception as exp:
            self.logger.error(exp)

    def receive_data(self, msg: any):
        try:
            self.web_sock.on_message = msg
            self.web_sock.run_forever()
        except Exception as exp:
            self.logger.error(exp)

    def close_data(self):
        try:
            self.web_sock.close()
        except Exception as exp:
            self.logger.error(exp)

    def error_data(self, err: any):
        try:
            self.web_sock.on_error = err
        except Exception as exp:
            self.logger.error(exp)

    def place_order(self, **order):
        # Send the order placed message after 1 second
        time.sleep(1)
        # Add the order to the database
        self.collection.insert_one(
            {
                # random ExchOrderID 16 char only digits
                "ExchOrderID": str(int(time.time()))[-16:],
                "Status": "Fully Executed",
                "ScripCode": order["ScripCode"],
                "RemoteOrderId": order["RemoteOrderId"],
                "Qty": order["Qty"],
                "Rate": order["Price"],
                "Price": order["Price"],
                "BuySell": order["OrderType"],
                # "ExchType": order["Exchange"],
                "DelvIntra": order["IsIntraday"],
                "ExchType": order["ExchangeType"],
                "ScripName": "Dummy",
            }
        )
        # Do not immediately send the order placed message when its sl order
        if not order["RemoteOrderId"].startswith("sl"):
            self.send_data(
                {
                    "placed": order["ScripCode"],
                    "Price": order["Price"],
                    "Qty": order["Qty"],
                    "RemoteOrderId": order["RemoteOrderId"],
                }
            )
        return {"Message": "Success"}

    def fetch_order_status(self, req_list: list):
        response = {"OrdStatusResLst": []}
        # find the order in the database with each items in req_list matching
        # the "RemoteOrderID" field
        for req in req_list:
            order = self.collection.find_one({"RemoteOrderId": req["RemoteOrderId"]})
            if order:
                # change ExchOrderID to int(ExchOrderID)
                order["ExchOrderID"] = int(order["ExchOrderID"])
                order["PendingQty"] = 0  # Nothing pending all executed
                response["OrdStatusResLst"].append(order)
        return response

    def modify_order(self, **order):
        self.logger.info("modify_order %s", order)

    def cancel_order(self, **order):
        self.logger.info("cancel_order %s", order)

    def get_tradebook(self):
        response = {"TradeBookDetail": []}
        # find all orders in the database with status "Fully Executed"
        for order in self.collection.find({"Status": "Fully Executed"}):
            response["TradeBookDetail"].append(order)
        return response

    def order_book(self):
        response = self.get_tradebook()["TradeBookDetail"]
        # add "OrderStatus" same as "Status"
        for order in response:
            order["OrderStatus"] = order["Status"]
        return response

    def positions(self):
        self.logger.info("positions")

    def cancel_bulk_order(self, exch_order_ids: list):
        # update the database with status "Cancelled" for each ExchOrderID in
        # ExchOrderIDs
        for exch_order_id in exch_order_ids:
            self.collection.update_one(
                {"ExchOrderID": exch_order_id}, {"$set": {"Status": "Cancelled"}}
            )

    def get_option_chain(self, exch: str, symbol: str, expire: int):
        return {
            "Options": [
                {
                    "LastRate": 8.5,
                    "ScripCode": 201945003,
                    "Name": "NIFTY23AUG19600CE",
                    "CPType": "CE",
                },
                {
                    "LastRate": 8.1,
                    "ScripCode": 301945003,
                    "Name": "NIFTY23AUG19100PE",
                    "CPType": "PE",
                },
            ]
        }

    def get_expiry(self, exch: str, symbol: str):
        return {"Expiry": []}

    def login(self):
        return self

    ## @override
    def get_pnl_summary(self, _tag: str = None):
        return {}

    ## @override
    def get_todays_tags(self):
        return {}

    ## @override
    def fetch_market_depth(self, _req_list: list):
        return {}

    ## @override
    # pylint: disable=too-many-arguments
    def historical_data(
        self,
        _exch: str,
        _exchange_segment: str,
        _scrip_code: int,
        _time_val: str,
        _from_val: str,
        _to_val: str,
    ):
        return {}
