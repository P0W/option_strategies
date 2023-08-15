import json
import logging
import time
from . import iclientmanager
import websocket
from pymongo import MongoClient


class Client(iclientmanager.IClientManager):
    def __init__(self):
        self.host = "localhost"
        self.port = 8765
        self.logger = logging.getLogger(__name__)

        # Connection parameters
        username = 'root'
        password = 'admin'
        host = 'localhost'
        port = 27017
        auth_source = 'admin'  # The authentication database

        # Create the connection URL with authentication
        connection_url = f"mongodb://{username}:{password}@{host}:{port}/{auth_source}"
        self.mongo_client = MongoClient(connection_url)
        ## Create a database
        self.db = self.mongo_client["test-database"]
        ## Create a collection
        self.collection = self.db["orders"]
        self.web_url = None

    def Request_Feed(self, Method: str, Operation: str, req_list: list):
        payload = {"Method": "mf", "Operation": Operation, "MarketFeedData": req_list}
        return payload

    def connect(self, wspayload: dict):
        self.logger.info("Connecting to %s:%d" % (self.host, self.port))
        try:
            self.web_url = f"ws://{self.host}:{self.port}/"

            def on_open(ws):
                self.logger.info("Streaming Started from %s" % self.web_url)
                try:
                    ws.send(json.dumps(wspayload))
                except Exception as e:
                    self.logger.error(e)

            self.ws = websocket.WebSocketApp(self.web_url)
            self.ws.on_open = on_open
        except Exception as e:
            self.logger.error(e)

    def send_data(self, wspayload: any):
        try:
            self.ws.send(json.dumps(wspayload))
        except Exception as e:
            self.logger.error(e)

    def receive_data(self, msg: any):
        try:
            self.ws.on_message = msg
            self.ws.run_forever()
        except Exception as e:
            self.logger.error(e)

    def close_data(self):
        try:
            self.ws.close()
        except Exception as e:
            self.logger.error(e)

    def error_data(self, err: any):
        try:
            self.ws.on_error = err
        except Exception as e:
            self.logger.error(e)

    def place_order(self, **order):
        ## Send the order placed message after 1 second
        time.sleep(1)
        ## Add the order to the database
        self.collection.insert_one(
            {
                ## random ExchOrderID 16 char only digits
                "ExchOrderID": str(int(time.time()))[-16:],
                "Status": "Fully Executed",
                "ScripCode": order["ScripCode"],
                "RemoteOrderID": order["RemoteOrderID"],
                "Qty": order["Qty"],
                "Rate": order["Price"],
                "Price": order["Price"],
                "BuySell": order["OrderType"],
                "ExchType" : order["Exchange"],
                "DelvIntra": order["IsIntraday"],
                "ExchType" : order["ExchangeType"],
                "ScripName": "Dummy"
            }
        )
        ## Do not immediately send the order placed message when its sl order
        if not order["RemoteOrderID"].startswith("sl"):
            self.send_data({"placed": order["ScripCode"], "Price": order["Price"], "Qty": order["Qty"], "RemoteOrderID": order["RemoteOrderID"]})
        return {"Message": "Success"}

    def fetch_order_status(self, req_list: list):
        response = {"OrdStatusResLst": []}
        ## find the order in the database with each items in req_list matching the "RemoteOrderID" field
        for req in req_list:
            order = self.collection.find_one({"RemoteOrderID": req["RemoteOrderID"]})
            if order:
                ## change ExchOrderID to int(ExchOrderID)
                order["ExchOrderID"] = int(order["ExchOrderID"])
                order["PendingQty"] = 0 ## Nothing pending all executed
                response["OrdStatusResLst"].append(order)
        return response

    def modify_order(self, **order):
        self.logger.info(f"modify_order: {order}")

    def cancel_order(self, **order):
        self.logger.info(f"cancel_order: {order}")

    def get_tradebook(self):
        response = {"TradeBookDetail": []}
        ## find all orders in the database with status "Fully Executed"
        for order in self.collection.find({"Status": "Fully Executed"}):
            response["TradeBookDetail"].append(order)
        return response

    def order_book(self):
        response =  self.get_tradebook()["TradeBookDetail"]
        ## add "OrderStatus" same as "Status"
        for order in response:
            order["OrderStatus"] = order["Status"]
        return response

    def positions(self):
        self.logger.info(f"positions")

    def cancel_bulk_order(self, ExchOrderIDs: list):
        ## update the database with status "Cancelled" for each ExchOrderID in ExchOrderIDs
        for ExchOrderID in ExchOrderIDs:
            self.collection.update_one(
                {"ExchOrderID": ExchOrderID}, {"$set": {"Status": "Cancelled"}}
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

    def login(self, cred_file: str = "creds.json"):
        return self


if __name__ == "__main__":
    Client.configure_logger("DEBUG")

    def display(ws, msg):
        print(msg)

    client = Client("localhost", 8765)
    client.connect(client.Request_Feed("mf", "s", [201945003, 301945003]))
    client.receive_data(display)
