## Author : Prashant Srivastava

import logging
import json
import queue
import threading
from typing import List, Callable


class LiveFeedManager:
    def __init__(self, client, config: dict):
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.req_list = []
        self.unsubscribe_list = []
        self.monitoring_active = False
        self.monitoring_lock = threading.Lock()
        self.shutdown_flag = threading.Event()
        self.callback_queue = queue.Queue()
        self.order_queue = queue.Queue()
        self.receiver_thread = None
        self.scrip_dequeuer_thread = None
        self.order_dequeuer_thread = None

    def callback_dequeuer(
        self,
        callback: Callable[[dict, dict], None],
        user_data: dict = {},
    ):
        while not self.shutdown_flag.is_set():
            try:
                callback_data = self.callback_queue.get(
                    timeout=15
                )  ## wait for 60 seconds for new data
                callback(callback_data, user_data)
                self.callback_queue.task_done()
            except queue.Empty:
                ## no live feed data received in the last 5 seconds
                ## stop the monitoring session
                self.logger.warning(
                    "No live feed data received in the last 15 seconds. Stoping the monitoring session."
                )
                self.stop()

    def order_dequeuer(
        self,
        callback: Callable[[dict, list, dict], None],
        subscription_list: list,
        user_data: dict = {},
    ):
        while not self.shutdown_flag.is_set():
            try:
                order_data = self.order_queue.get(timeout=1)
                callback(order_data, subscription_list, user_data)
                self.order_queue.task_done()
            except queue.Empty:
                ## no order data received in the last 5 seconds
                pass

    def monitor(
        self,
        scrip_codes: List[int],
        on_scrip_data: Callable[[dict, dict], None],
        on_order_update: Callable[[dict, list, dict], None] = None,
        user_data: dict = {},
    ) -> None:
        with self.monitoring_lock:
            self.logger.info(f"Starting monitoring session for scrips: {scrip_codes}")
            if self.monitoring_active:
                self.logger.warning(
                    "Monitoring is already active. Not starting a new session."
                )
                return

            def on_error(ws, err):
                self.logger.error(f"WebSocket error: {err}")

            def process_msg(msg: dict):
                if "Status" in msg:
                    ## Example :{"ReqType":"P","ClientCode":"58194614","Exch":"N","ExchType":"D","ScripCode":47879,"Symbol":"NIFTY 10 Aug 2023 CE 19650.00","Series":"","BrokerOrderID":924914129,"ExchOrderID":"1000000021635748","ExchOrderTime":"2023-08-09 10:14:01","BuySell":"B","Qty":50,"Price":13.25,"ReqStatus":0,"Status":"Placed","OrderRequestorCode":"58194614","AtMarket":"N","Product":"I","WithSL":"N","SLTriggerRate":0,"DisclosedQty":0,"PendingQty":50,"TradedQty":0,"RemoteOrderId":"581946142023080910140176"}
                    self.order_queue.put(msg)
                elif "LastRate" in msg:
                    ## convert the json message to a list of dict only ohlcv values
                    ## Example :[{'Exch': 'N', 'ExchType': 'D', 'Token': 50474, 'LastRate': 132.25, 'LastQty': 600, 'TotalQty': 6461680, 'High': 132.4, 'Low': 75.75, 'OpenRate': 85.1, 'PClose': 78.25, 'AvgRate': 109.84, 'Time': 16401, 'BidQty': 40, 'BidRate': 131.95, 'OffQty': 880, 'OffRate': 132.3, 'TBidQ': 131720, 'TOffQ': 143160, 'TickDt': '/Date(1691557401000)/', 'ChgPcnt': 69.00958}]
                    self.callback_queue.put(
                        {
                            "o": msg["OpenRate"],
                            "h": msg["High"],
                            "l": msg["Low"],
                            "c": msg["LastRate"],
                            "v": msg["LastQty"],
                            "code": msg["Token"],
                            "t": int(msg["TickDt"][6:-2])
                            / 1000,  ##  '/Date(1691557402000)/'
                            "ChgPcnt": msg["ChgPcnt"],
                        }
                    )

            def on_message(ws, message):
                json_msg = json.loads(message)
                try:
                    ## if json_msg is a list
                    if isinstance(json_msg, list):
                        for msg in json_msg:
                            process_msg(msg)

                    ## if json_msg is a dict
                    elif isinstance(json_msg, dict):
                        process_msg(json_msg)
                    else:
                        self.logger.error(
                            f"Unknown message type received: {type(json_msg)}"
                        )
                        self.logger.error(f"Message: {json_msg}")
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")

            self.req_list.extend(
                [{"Exch": "N", "ExchType": "D", "ScripCode": x} for x in scrip_codes]
            )
            req_data = self.client.Request_Feed("mf", "s", self.req_list)
            self.client.connect(req_data)
            self.client.error_data(on_error)

            ## Start the threads only after the connection is established

            ## Note: Three threads are kicked off
            ## To avoid contention of resources create order thread and scrip data threads
            ## Queue only data on individual queues and process them in the threads
            ## 5paisa receive_data is a blocking call and hence it is run in a separate thread as well
            ## we don't want to block the receive_data as to stop the monitoring session we need to gracefully close the connection
            ## unsubscribing from the feeds as well

            # Start the callback_dequeuer thread
            self.scrip_dequeuer_thread = threading.Thread(
                target=self.callback_dequeuer,
                args=(on_scrip_data, user_data),
            )
            self.logger.info("Starting scrip data callback thread.")
            self.scrip_dequeuer_thread.start()

            # Start the order_dequeuer thread
            if on_order_update:
                self.on_order_update = on_order_update
                ## use lambda to use on_order callback as free function
            callback_args = (
                lambda x, y: self._on_order_update(x, y),
                self.req_list,
                user_data,
            )
            self.order_dequeuer_thread = threading.Thread(
                target=self.order_dequeuer, args=callback_args
            )
            self.logger.info("Starting order update callback thread.")
            self.order_dequeuer_thread.start()

            # Start receiving data in a separate thread to avoid blocking
            self.receiver_thread = threading.Thread(
                target=self.client.receive_data, args=(on_message,)
            )
            self.logger.info("Starting data receiver thread.")
            self.receiver_thread.start()

            self.monitoring_active = True

    def stop(self):
        with self.monitoring_lock:
            if not self.monitoring_active:
                self.logger.warning("Monitoring is not active. Cannot stop.")
                return

            # Signal the monitoring thread to stop
            self.shutdown_flag.set()

            self.logger.info("Stopping monitoring session.")

            # Clean up resources
            payload = self.client.Request_Feed("mf", "u", self.req_list)

            ## bug in 5paisa websocket send_data implementation, use the object directly
            self.client.ws.send(json.dumps(payload))
            ## close the websocket connection
            self.client.close_data()
            self.req_list = []
            self.monitoring_active = False

            # Optionally wait for the receiver thread to complete
            self.receiver_thread.join()

    def on_cancel_order(self, message: dict):
        ## Default implementation - simply log
        self.logger.info(f"Order cancelled: {message}")

    def on_sl_order(self, message: dict):
        ## Default implementation - simply log
        self.logger.info(f"Stop loss order: {message}")

    def on_order_update(
        self, message: dict, subscription_list: list, user_data: dict = {}
    ):
        pass

    def _on_order_update(
        self, message: dict, subscription_list: list, user_data: dict = {}
    ):
        if not "order_update" in user_data:
            user_data["order_update"] = []
        if message["Status"] == "Fully Executed":
            scrip_codes = [item["ScripCode"] for item in subscription_list]
            if message["ScripCode"] in scrip_codes:
                if self.unsubscribe([message["ScripCode"]]):
                    user_data["order_update"].append(message["ScripCode"])

        elif message["Status"] == "Cancelled":
            self.on_cancel_order(message)
        elif message["Status"] == "SL Triggered":
            self.on_sl_order(message)
        else:
            self.logger.info(f"Order update: {message}")
        self.on_order_update(message, subscription_list, user_data)

    @DeprecationWarning  ## Doesn't work - Don't use
    def subscribe(self, scrip_codes: List[int]) -> bool:
        with self.monitoring_lock:
            self.logger.info(f"Subscribing to scrips: {scrip_codes}")
            self.req_list.extend(
                [{"Exch": "N", "ExchType": "D", "ScripCode": x} for x in scrip_codes]
            )
            req_data = self.client.Request_Feed("mf", "s", self.req_list)
            ## bug in 5paisa websocket send_data implementation, use the object directly
            if self.client.ws is not None:
                self.client.ws.send(json.dumps(req_data))
                return True
        return False

    def unsubscribe(self, scrip_codes: List[int]) -> bool:
        with self.monitoring_lock:
            unsubscribe_list = [
                {"Exch": "N", "ExchType": "D", "ScripCode": x} for x in scrip_codes
            ]
            req_data = self.client.Request_Feed("mf", "u", unsubscribe_list)
            ## bug in 5paisa websocket send_data implementation, use the object directly
            if self.client.ws is not None:
                self.client.ws.send(json.dumps(req_data))
                ## update the original subscribe_list
                self.req_list = [
                    item
                    for item in self.req_list
                    if item["ScripCode"] not in scrip_codes
                ]
                self.logger.info(f"Unsubscribed from scrips: {scrip_codes}")
                return True
        return False
