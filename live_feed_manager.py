import logging
import json
from typing import List, Callable


class LiveFeedManager:
    def __init__(self, client, config) -> None:
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)

    def monitor(self, scrip_codes: List[int], callback: Callable[[dict], None]) -> None:
        req_list = list(
            map(lambda x: {"Exch": "N", "ExchType": "D", "ScripCode": x}, scrip_codes)
        )
        req_data = self.client.Request_Feed("mf", "s", req_list)

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
        self.client.close_data()


if __name__ == "__main__":
    import daily_short

    client = daily_short.login("creds.json")
    lm = LiveFeedManager(client, {})

    def apply(response: dict) -> None:
        print(response)

    lm.monitor([58419, 40375], apply)
