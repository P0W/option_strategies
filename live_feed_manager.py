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
        self.unsubscribe_list = []
        self.monitoring_active = False
        self.monitoring_lock = threading.Lock()
        self.shutdown_flag = threading.Event()
        self.callback_queue = queue.Queue()
        self.receiver_thread = None
        self.dequeuer_thread = None

    def callback_dequeuer(
        self,
        callback: dict,
        target_profit: float,
        max_stop_loss: float,
        user_data: dict,
    ):
        while not self.shutdown_flag.is_set():
            try:
                callback_data = self.callback_queue.get(
                    timeout=15
                )  ## wait for 60 seconds for new data
                callback(callback_data, target_profit, max_stop_loss, user_data)
                self.callback_queue.task_done()
            except queue.Empty:
                ## no live feed data received in the last 5 seconds
                ## stop the monitoring session
                self.stop()

    def monitor(
        self,
        scrip_codes: List[int],
        callback: Callable[[dict, float, float, dict], None],
        target_profit: float,
        max_stop_loss: float,
        user_data: dict,
    ) -> None:
        self.logger.info("Starting monitoring session for scrips: %s", scrip_codes)
        self.logger.info("Target Profit: %f", target_profit)
        self.logger.info("Max Stop Loss: %f", max_stop_loss)
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
                    if "Status" in message and "Fully Executed" in message:
                        ## if message["ScripCode"] in self.req_list add to unsubscribe_list
                        ## and send the list to the client
                        if message["ScripCode"] in list(
                            map(self.req_list, lambda x: x["ScripCode"])
                        ):
                            self.unsubscribe_list.append(
                                {
                                    "Exch": "N",
                                    "ExchType": "D",
                                    "ScripCode": message["ScripCode"],
                                }
                            )
                            self.logger.info(
                                f"Unsubscribing from scrip: {message['ScripCode']}"
                            )
                            req_data = self.client.Request_Feed(
                                "mf", "u", self.unsubscribe_list
                            )
                            ## bug in 5paisa websocket send_data implementation, use the object directly
                            self.client.ws.send(json.dumps(req_data))
                            self.unsubscribe_list = []
                        else:
                            self.logger.info(
                                f"Order Executed response on websocket: {message}"
                            )
                    else:
                        self.logger.error(f"Error processing message: {message}")
                        self.logger.error(f"Error: {e}")

            self.logger.info("Connecting to live feed.")
            self.client.connect(req_data)
            self.client.error_data(on_error)

            # Start the callback_dequeuer thread
            self.dequeuer_thread = threading.Thread(
                target=self.callback_dequeuer,
                args=(callback, target_profit, max_stop_loss, user_data),
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


## Example usage
if __name__ == "__main__":
    import daily_short
    import strikes_manager

    client = daily_short.login("creds.json")
    daily_short.configure_logger("DEBUG")
    sm = strikes_manager.StrikesManager(client, {})
    staddle_strikes = sm.straddle_strikes("FINNIFTY")

    straddle_premium = staddle_strikes["ce_ltp"] + staddle_strikes["pe_ltp"]
    lm = LiveFeedManagerV2(client, {})

    def straddle_calculator(res: dict, target: float, mtm_loss: float, items: dict):
        code = res["code"]
        ltp = res["c"]

        items[code] = (ltp) * 1
        if len(items.keys()) == 2:  ## wait for both legs prices availability
            ## calculate MTM summing the pnl of each leg
            total_pnl = sum(items.values())
            logging.info(
                "Total Straddle Preminum: %f %s"
                % (total_pnl, json.dumps(items, indent=3))
            )
            if total_pnl >= target:
                # TARGET ACHEIVED
                logging.info("Target Achieved: %f" % total_pnl)
                # Sqaure off both legs
                logging.info("Squaring off both legs")
                logging.info("Cancelling pending stop loss orders")
                logging.info("Stopping live feed")
                lm.stop()
            elif total_pnl <= mtm_loss:
                # STOP LOSS HIT
                logging.info("Stop Loss Hit: %f" % total_pnl)
                # Sqaure off both legs
                logging.info("Squaring off both legs")
                logging.info("Cancelling pending target orders")
                logging.info("Stopping live feed")
                lm.stop()

    lm.monitor(
        [staddle_strikes["ce_code"], staddle_strikes["pe_code"]],
        straddle_calculator,
        target_profit=straddle_premium * 1.01,
        max_stop_loss=straddle_premium * 0.99,
        user_data={},
    )
