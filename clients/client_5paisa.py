## Author: Prashant Srivastava

import json
from py5paisa import FivePaisaClient
import pyotp
from . import iclientmanager


class Client(iclientmanager.IClientManager):
    ## implement all the abstract methods here
    def __init__(self, cred_file: str = "creds.json"):
        with open(cred_file) as cred_fh:
            self.cred = json.load(cred_fh)
        self._client = None

    ## @override
    def login(self):
        self._client = FivePaisaClient(self.cred)
        totp = pyotp.TOTP(self.cred["totp_secret"])
        self._client.get_totp_session(
            self.cred["clientcode"], totp.now(), self.cred["pin"]
        )
        return self

    ## @override
    def get_option_chain(self, exch: str, symbol: str, expire: int):
        return self._client.get_option_chain(exch, symbol, expire)

    ## @override
    def get_expiry(self, exch: str, symbol: str):
        return self._client.get_expiry(exch, symbol)

    ## @override
    def place_order(self, **order):
        return self._client.place_order(**order)

    ## @override
    def fetch_order_status(self, req_list: list):
        return self._client.fetch_order_status(req_list)

    ## @override
    def modify_order(self, **order):
        return self._client.modify_order(**order)

    ## @override
    def cancel_order(self, **order):
        return self._client.cancel_order(**order)

    ## @override
    def get_tradebook(self):
        return self._client.get_tradebook()

    ## @override
    def order_book(self):
        return self._client.order_book()

    ## @override
    def positions(self):
        return self._client.positions()

    ## @override
    def cancel_bulk_order(self, ExchOrderIDs: list):
        return self._client.cancel_bulk_order(ExchOrderIDs)

    ## @override
    def Request_Feed(self, Method: str, Operation: str, req_list: list):
        return self._client.Request_Feed(Method, Operation, req_list)

    ## @override
    def connect(self, wspayload: dict):
        return self._client.connect(wspayload)

    ## @override
    def error_data(self, err: any):
        return self._client.error_data(err)

    ## @override
    def close_data(self):
        return self._client.close_data()

    ## @override
    def receive_data(self, msg: any):
        return self._client.receive_data(msg)

    ## @override
    def send_data(self, wspayload: dict):
        ## bug in 5paisa websocket send_data implementation, use the object directly
        if self._client.ws:
            return self._client.ws.send(wspayload)
        return None
