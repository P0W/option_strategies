# Author: Prashant Srivastava

# pylint: disable=broad-exception-raised

import datetime
import json
import re

import pyotp
import redis
from py5paisa import FivePaisaClient

from . import iclientmanager


class Client(iclientmanager.IClientManager):
    ACCESS_TOKEN_KEY = "access_token"

    # implement all the abstract methods here
    def __init__(self, cred_file: str = "creds.json"):
        with open(cred_file, encoding="utf-8") as cred_fh:
            self.cred = json.load(cred_fh)
        self._client = None

    # @override - @TODO: Move redis to basse class
    def login(self):
        self._client = FivePaisaClient(self.cred)
        try:
            redis_client = redis.Redis(host="127.0.0.1")
            access_token = redis_client.get(Client.ACCESS_TOKEN_KEY)
            if access_token:
                access_token = access_token.decode("utf-8")
                # 5paisa hack, no way to set acess token directly using sdk API
                self._client.client_code = self.cred["clientcode"]
                self._client.access_token = access_token
                self._client.Jwt_token = access_token
            else:
                raise Exception("No access token found")
        except Exception:
            print("No access token found in cache, logging in")
            totp = pyotp.TOTP(self.cred["totp_secret"])
            access_token = self._client.get_totp_session(
                self.cred["clientcode"], totp.now(), self.cred["pin"]
            )
            try:
                redis_client.set(
                    Client.ACCESS_TOKEN_KEY, access_token, ex=2 * 60 * 60
                )  # 2 hours expiry
            except Exception:
                pass
        return self

    # @override
    def get_option_chain(self, exch: str, symbol: str, expire: int):
        return self._client.get_option_chain(exch, symbol, expire)

    # @override
    def get_expiry(self, exch: str, symbol: str):
        return self._client.get_expiry(exch, symbol)

    # @override
    def place_order(self, **order):
        return self._client.place_order(**order)

    # @override
    def fetch_order_status(self, req_list: list):
        return self._client.fetch_order_status(req_list)

    # @override
    def modify_order(self, **order):
        return self._client.modify_order(**order)

    # @override
    def cancel_order(self, **order):
        return self._client.cancel_order(**order)

    # @override
    def get_tradebook(self):
        return self._client.get_tradebook()

    # @override
    def order_book(self):
        return self._client.order_book()

    # @override
    def positions(self):
        return self._client.positions()

    # @override
    def cancel_bulk_order(self, exch_order_ids: list):
        return self._client.cancel_bulk_order(exch_order_ids)

    # @override
    def Request_Feed(self, method: str, operation: str, req_list: list):
        return self._client.Request_Feed(method, operation, req_list)

    # @override
    def connect(self, wspayload: dict):
        return self._client.connect(wspayload)

    # @override
    def error_data(self, err: any):
        return self._client.error_data(err)

    # @override
    def close_data(self):
        return self._client.close_data()

    # @override
    def receive_data(self, msg: any):
        return self._client.receive_data(msg)

    # @override
    def send_data(self, wspayload: dict):
        # bug in 5paisa websocket send_data implementation, use the object
        # directly
        if self._client.ws:
            return self._client.ws.send(json.dumps(wspayload))
        return None

    # @override
    def get_pnl_summary(self, tag: str = None):
        if not tag:
            tags = self.get_todays_tags()
        else:
            tags = [tag]
        order_status = self._client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": tag} for tag in tags]
        )["OrdStatusResLst"]
        exch_order_ids = [
            int(x["ExchOrderID"])
            for x in order_status
            if x["PendingQty"] == 0 and x["Status"] == "Fully Executed"
        ]
        trade_book = self._client.get_tradebook()["TradeBookDetail"]
        matching_orders = [
            {
                "ExchOrderID": trade["ExchOrderID"],
                "ScripCode": trade["ScripCode"],
                "Rate": trade["Rate"],
                "Qty": trade["Qty"],
                "BuySell": trade["BuySell"],
                "ScripName": trade["ScripName"],
                "LastTradedPrice": None,
                "Pnl": None,
            }
            for trade in trade_book
            if int(trade["ExchOrderID"]) in exch_order_ids
        ]

        request_prices = list(
            map(
                lambda order: {
                    "Exchange": "N",
                    "ExchangeType": "D",
                    "ScripCode": order["ScripCode"],
                },
                matching_orders,
            )
        )

        depth = self.fetch_market_depth(request_prices)["Data"]
        ltp_dict = {dep["ScripCode"]: dep["LastTradedPrice"] for dep in depth}
        for order in matching_orders:
            order["LastTradedPrice"] = ltp_dict[order["ScripCode"]]
            order["Pnl"] = (
                (order["LastTradedPrice"] - order["Rate"])
                * order["Qty"]
                * (1 if order["BuySell"] == "B" else -1)
            )
        return matching_orders

    # @override
    def get_todays_tags(self):
        order_book = self._client.order_book()
        tags = []
        for order in order_book:
            if "RemoteOrderID" not in order:
                print(order)
            try:
                search_text = re.search("\\w(\\d+)$", order["RemoteOrderID"])
                if search_text:
                    timestamp_str = int(
                        search_text.group(1)
                    )  # Extract the timestamp part from the text
                    # Convert the timestamp to a datetime object
                    timestamp_unix = int(timestamp_str)
                    timestamp_datetime = datetime.datetime.utcfromtimestamp(
                        timestamp_unix
                    )
                    # Get the current date
                    current_date = datetime.date.today()
                    if timestamp_datetime.date() == current_date:
                        if order["RemoteOrderID"] not in tags:
                            tags.append(order["RemoteOrderID"])
            except Exception:
                pass
        return tags

    # @override
    def fetch_market_depth(self, req_list: list):
        return self._client.fetch_market_depth(req_list)
    
    # @override
    def historical_data(self, exch: str,
                        exchange_segment: str,
                        scrip_code: int,
                        interval: str,
                        start_date: str,
                        end_date: str):
        return self._client.historical_data(exch, exchange_segment, scrip_code, interval, start_date, end_date)
