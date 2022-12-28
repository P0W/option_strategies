## Author : Prashant Srivastava
## Last Modified Date  : Dec 28th, 2022

import logging
import json
from typing import List, Callable


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


if __name__ == "__main__":
    import daily_short

    client = daily_short.login("creds.json")
    lm = LiveFeedManager(client, {})
    test_counter = 0

    def apply(response: dict) -> None:
        global tetest_counterst
        print(response)
        if test_counter == 5:
            lm.stop()
        test_counter += 1

    lm.monitor([58419, 40375], apply)
