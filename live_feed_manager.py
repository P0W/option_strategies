## Author : Prashant Srivastava
## Last Modified Date  : Aug 7th, 2023

import logging
import json
import queue
import threading
from typing import List, Callable

@DeprecationWarning
class LiveFeedManager:
    def __init__(self, client, config) -> None:
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.req_list = []

    def monitor(self, scrip_codes: List[int], callback: Callable[[dict], None]) -> None:
        self.req_list = list(
            map(lambda x: {"Exch": "N", "ExchType": "D", "ScripCode": x}, scrip_codes)
        )
        req_data = self.client.Request_Feed("mf", "s", self.req_list)

        def on_error(ws, err):
            self.logger.error(ws, err)

        def on_message(ws, message):
            x = json.loads(message)[0]
            callback(
                {
                    "o": x["OpenRate"],
                    "h": x["High"],
                    "l": x["Low"],
                    "c": x["LastRate"],
                    "v": x["TotalQty"],
                    "code": x["Token"],
                }
            )

        self.client.connect(req_data)
        self.client.error_data(on_error)
        self.client.receive_data(on_message)

    def stop(self):
        if len(self.req_list) > 0:
            self.client.Request_Feed("mf", "u", self.req_list)
            self.client.close_data()
            self.req_list = []


class LiveFeedManagerV2:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.req_list = []
        self.monitoring_active = False
        self.monitoring_lock = threading.Lock()
        self.shutdown_flag = threading.Event()
        self.callback_queue = queue.Queue()
        self.receiver_thread = None
        self.dequeuer_thread = None

    def callback_dequeuer(self, callback):
        while not self.shutdown_flag.is_set():
            try:
                callback_data = self.callback_queue.get(
                    timeout=60
                )  ## wait for 60 seconds for new data
                callback(callback_data)
                self.callback_queue.task_done()
            except queue.Empty:
                ## no live feed data received in the last 5 seconds
                ## stop the monitoring session
                self.stop()

    def monitor(self, scrip_codes: List[int], callback: Callable[[dict], None]) -> None:
        self.logger.info("Starting monitoring session.")
        with self.monitoring_lock:
            if self.monitoring_active:
                self.logger.warning(
                    "Monitoring is already active. Not starting a new session."
                )
                return

            self.req_list = [
                {"Exch": "N", "ExchType": "D", "ScripCode": x} for x in scrip_codes
            ]
            req_data = self.client.Request_Feed("mf", "s", self.req_list)

            def on_error(ws, err):
                self.logger.error(f"WebSocket error: {err}")

            def on_message(ws, message):
                try:
                    x = json.loads(message)[0]
                    self.callback_queue.put(
                        {
                            "o": x["OpenRate"],
                            "h": x["High"],
                            "l": x["Low"],
                            "c": x["LastRate"],
                            "v": x["TotalQty"],
                            "code": x["Token"],
                        }
                    )
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")

            self.logger.info("Connecting to live feed.")
            self.client.connect(req_data)
            self.client.error_data(on_error)

            # Start the callback_dequeuer thread
            self.dequeuer_thread = threading.Thread(
                target=self.callback_dequeuer, args=(callback,)
            )
            self.dequeuer_thread.start()

            # Start receiving data in a separate thread to avoid blocking
            self.receiver_thread = threading.Thread(
                target=self.client.receive_data, args=(on_message,)
            )
            self.receiver_thread.start()

            self.monitoring_active = True

    def stop(self):
        with self.monitoring_lock:
            if not self.monitoring_active:
                self.logger.warning("Monitoring is not active. Cannot stop.")
                return

            self.logger.info("Stopping monitoring session.")

            # Signal the monitoring thread to stop
            self.shutdown_flag.set()

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


if __name__ == "__main__":
    import daily_short

    client = daily_short.login("creds.json")
    daily_short.configure_logger("DEBUG")
    lm = LiveFeedManagerV2(client, {})
    test_counter = 0

    def apply(response: dict) -> None:
        global test_counter
        logging.info(response)
        if test_counter == 5:
            lm.stop()
        test_counter += 1

    lm.monitor([58419, 40375], apply)
