# Author : Prashant Srivastava
import json
import logging
import queue
import threading
from typing import Callable
from typing import List

from src.clients.iclientmanager import IClientManager


class LiveFeedManager:
    NIFTY_INDEX = 999920000
    BANKNIFTY_INDEX = 999920005

    def __init__(self, client: IClientManager, config: dict):
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
        self.exchange_type = config["exchangeType"] if "exchangeType" in config else "D"

    def callback_dequeuer(
        self,
        callback: Callable[[dict, dict], None],
        user_data: dict = None,
    ):
        while not self.shutdown_flag.is_set():
            try:
                callback_data = self.callback_queue.get(
                    timeout=15
                )  # wait for 60 seconds for new data
                callback(callback_data, user_data)
                self.callback_queue.task_done()
            except queue.Empty:
                # no live feed data received in the last 5 seconds
                # stop the monitoring session
                self.logger.warning(
                    "No live feed data received in the last 15 seconds. \
                     Stoping the monitoring session."
                )
                self.stop()

    def order_dequeuer(
        self,
        subscription_list: list,
        user_data: dict = None,
        user_callback: Callable[[dict, list, dict], None] = None,
    ):
        while not self.shutdown_flag.is_set():
            try:
                order_data = self.order_queue.get(timeout=1)
                self._on_order_update(
                    order_data, subscription_list, user_data, user_callback
                )
                self.order_queue.task_done()
            except queue.Empty:
                # no order data received in the last 1 seconds
                pass

    def monitor(
        self,
        scrip_codes: List[int],
        on_scrip_data: Callable[[dict, dict], None],
        on_order_update: Callable[[dict, list, dict], None] = None,
        user_data: dict = None,
    ) -> None:
        with self.monitoring_lock:
            self.logger.info("Starting monitoring session for scrips %s", scrip_codes)
            if self.monitoring_active:
                self.logger.warning(
                    "Monitoring is already active. Not starting a new session."
                )
                return

            def on_error(_ws, err):
                self.logger.error("WebSocket error: %s", err)

            def process_msg(msg: dict):
                if "Status" in msg:
                    self.order_queue.put(msg)
                elif "LastRate" in msg:
                    # convert the json message to a list of dict only ohlcv
                    # values
                    self.callback_queue.put(
                        {
                            "o": msg["OpenRate"],
                            "h": msg["High"],
                            "l": msg["Low"],
                            "c": msg["LastRate"],
                            "v": msg["LastQty"],
                            "code": msg["Token"],
                            "t": int(msg["TickDt"][6:-2])
                            / 1000,  # '/Date(1691557402000)/'
                            "ChgPcnt": msg["ChgPcnt"],
                        }
                    )

            def on_message(_ws, message):
                json_msg = json.loads(message)
                try:
                    # if json_msg is a list
                    if isinstance(json_msg, list):
                        for msg in json_msg:
                            process_msg(msg)

                    # if json_msg is a dict
                    elif isinstance(json_msg, dict):
                        process_msg(json_msg)
                    else:
                        self.logger.error(
                            "Unknown message type received: %s", type(json_msg)
                        )
                        self.logger.error("Message: %s", json_msg)
                except Exception as exp:
                    self.logger.error("Error processing message: %s", exp)

            if LiveFeedManager.NIFTY_INDEX in scrip_codes:
                self.req_list.append(
                    {
                        "Exch": "N",
                        "ExchType": "C",
                        "ScripCode": LiveFeedManager.NIFTY_INDEX,
                    }
                )
                scrip_codes.pop(scrip_codes.index(LiveFeedManager.NIFTY_INDEX))

            self.req_list.extend(
                [
                    {"Exch": "N", "ExchType": self.exchange_type, "ScripCode": x}
                    for x in scrip_codes
                ]
            )
            req_data = self.client.Request_Feed("mf", "s", self.req_list)
            self.client.connect(req_data)
            self.client.error_data(on_error)

            # Start the threads only after the connection is established

            # Note: Three threads are kicked off
            # To avoid contention of resources create order thread and scrip data threads
            # Queue only data on individual queues and process them in the threads
            # 5paisa receive_data is a blocking call and hence it is run in
            # a separate thread as well we don't want to block the receive_data
            # as to stop the monitoring session we need to gracefully close the
            # connection unsubscribing from the feeds as well

            # Start the callback_dequeuer thread
            self.scrip_dequeuer_thread = threading.Thread(
                target=self.callback_dequeuer,
                args=(on_scrip_data, user_data),
            )
            self.logger.info("Starting scrip data callback thread.")
            self.scrip_dequeuer_thread.start()

            # Start the order_dequeuer thread
            self.order_dequeuer_thread = threading.Thread(
                target=self.order_dequeuer,
                args=(self.req_list, user_data, on_order_update),
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

            self.client.send_data(payload)
            # close the websocket connection
            self.client.close_data()
            self.req_list = []
            self.monitoring_active = False

            # Optionally wait for the receiver thread to complete
            self.receiver_thread.join()

    def on_cancel_order(self, message: dict):
        # Default implementation - simply log
        self.logger.info("Order cancelled:%s", message)

    def on_sl_order(self, message: dict):
        # Default implementation - simply log
        self.logger.info("Stop loss order:%s", message)

    def _on_order_update(
        self,
        message: dict,
        subscription_list: list,
        user_data: dict = None,
        user_callback: Callable[[dict, list, dict], None] = None,
    ):
        if not "order_update" in user_data:
            user_data["order_update"] = []
        if message["Status"] == "Fully Executed":
            scrip_codes = [item["ScripCode"] for item in subscription_list]
            if message["ScripCode"] in scrip_codes and message[
                "RemoteOrderID"
            ].startswith(
                "sl"
            ):  # Unsubscribe from the scrip only if sl is hit
                if self.unsubscribe([message["ScripCode"]]):
                    user_data["order_update"].append(message["ScripCode"])

        elif message["Status"] == "Cancelled":
            self.on_cancel_order(message)
        elif message["Status"] == "SL Triggered":
            self.on_sl_order(message)
        else:
            self.logger.info("Order update:%s", message)
        if user_callback:
            user_callback(message, subscription_list, user_data)

    @DeprecationWarning  # Doesn't work - Don't use
    def subscribe(self, scrip_codes: List[int]) -> bool:
        with self.monitoring_lock:
            self.logger.info("Subscribing to scrips:%s", scrip_codes)
            self.req_list.extend(
                [
                    {"Exch": "N", "ExchType": self.exchange_type, "ScripCode": x}
                    for x in scrip_codes
                ]
            )
            req_data = self.client.Request_Feed("mf", "s", self.req_list)
            self.client.send_data(req_data)
        return True

    def unsubscribe(self, scrip_codes: List[int]) -> bool:
        with self.monitoring_lock:
            unsubscribe_list = [
                {"Exch": "N", "ExchType": self.exchange_type, "ScripCode": x}
                for x in scrip_codes
            ]
            req_data = self.client.Request_Feed("mf", "u", unsubscribe_list)
            self.client.send_data(req_data)
            # update the original subscribe_list
            self.req_list = [
                item for item in self.req_list if item["ScripCode"] not in scrip_codes
            ]
            self.logger.info("Unsubscribed from scrips:%s", scrip_codes)
        return True
