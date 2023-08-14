import json
import logging
import iclientmanager
import websocket


class Client(iclientmanager.IClientManager):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_thread = None
        self.data_thread = None
        self.connected = False
        self.logger = logging.getLogger(__name__)

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

    def send_data(self, msg: any):
        try:
            self.ws.send(msg)
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

    ## mock all the other methods simple display args
    def place_order(self, **order):
        self.logger.info(f"place_order: {order}")

    def fetch_order_status(self, req_list: list):
        self.logger.info(f"fetch_order_status: {req_list}")

    def modify_order(self, **order):
        self.logger.info(f"modify_order: {order}")

    def cancel_order(self, **order):
        self.logger.info(f"cancel_order: {order}")

    def get_tradebook(self):
        self.logger.info(f"get_tradebook")

    def order_book(self):
        self.logger.info(f"order_book")

    def positions(self):
        self.logger.info(f"positions")

    def cancel_bulk_order(self, ExchOrderIDs: list):
        self.logger.info(f"cancel_bulk_order: {ExchOrderIDs}")

    def get_option_chain(self, exch: str, symbol: str, expire: int):
        return super().get_option_chain(exch, symbol, expire)

    def get_expiry(self, exch: str, symbol: str):
        return super().get_expiry(exch, symbol)

    def login(self, cred_file: str = "creds.json"):
        return super().login(cred_file)


if __name__ == "__main__":
    Client.configure_logger("DEBUG")

    def display(ws, msg):
        print(msg)

    client = Client("localhost", 8765)
    client.connect(client.Request_Feed("s", [6229, 6228, 6227]))
    client.receive_data(display)
    # client.close_data()
    # client.place_order(OrderType='B', Exchange='N', ExchangeType='D', ScripCode=256265, Qty=1, Price=1, IsIntraday=True, RemoteOrderID='1')
    # client.fetch_order_status([{'Exch': 'N', 'RemoteOrderID': '1'}])
    # client.modify_order(OrderType='B', Exchange='N', ExchangeType='D', ScripCode=256265, Qty=1, Price=1, IsIntraday=True, RemoteOrderID='1')
    # client.cancel_order(OrderType='B', Exchange='N', ExchangeType='D', ScripCode=256265, Qty=1, Price=1, IsIntraday=True, RemoteOrderID='1')
    # client.get_tradebook()
    # client.order_book()
    # client.positions()
    # client.cancel_bulk_order(['1'])
