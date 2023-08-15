import asyncio
import websockets
import threading
import json
import random
import time
import logging
import numpy as np
from scipy.stats import norm


class MockDataGenerator:
    def __init__(self):
        self.exch = "N"
        self.exch_type = "D"
        self.tick_id = 0
        self.subscriptions = set()

        # Configurable parameters
        self.initial_nifty = 19434.5
        # self.time_to_expiration = 3 / 365  # 3 days in years
        self.risk_free_rate = 0.07209
        self.volatility = 0.12

    def option_price_generator(self, strike_price, days_to_expiration):
        time_to_expiration = days_to_expiration / 365
        while True:
            nifty = self.initial_nifty + np.random.uniform(-0.5, 0.6)
            d1 = (
                np.log(nifty / strike_price)
                + (self.risk_free_rate + 0.5 * self.volatility**2)
                * time_to_expiration
            ) / (self.volatility * np.sqrt(time_to_expiration))
            d2 = d1 - self.volatility * np.sqrt(time_to_expiration)

            call_price = nifty * norm.cdf(d1) - strike_price * np.exp(
                -self.risk_free_rate * time_to_expiration
            ) * norm.cdf(d2)
            put_price = strike_price * np.exp(
                -self.risk_free_rate * time_to_expiration
            ) * norm.cdf(-d2) - nifty * norm.cdf(-d1)

            yield {"Nifty": nifty, "CE": call_price, "PE": put_price}

            # Simulate changes
            ## Reduce the time to expiration by 1 sec
            time_to_expiration -= 1 / (365 * 24 * 60 * 60)
            self.volatility = max(
                0.01, self.volatility + np.random.uniform(-0.05, 0.05)
            )

    ## Randome cooked logic:
    ## If scripCode starts with 20 its CE, if its 30 its PE, following digit present strike 19450, 19100, etc
    ## first 2 digit represent time to expiry in days example 03 - 3 days,  07-7 days, 30 30 -days, etc
    ## So for instance:
    ## 201945007 represent 19450 CE 7 days to expiry
    def generate_tick(self, scrip_code):
        self.tick_id += 1
        ce_pe = None
        if scrip_code >= 300000000:
            ce_pe = "PE"
            remain = scrip_code - 300000000
        elif scrip_code >= 200000000:
            ce_pe = "CE"
            remain = scrip_code - 200000000
        if ce_pe:
            strike = remain // 100
            time_to_expiry = scrip_code % 100
            option_prices = self.option_price_generator(strike, time_to_expiry / 365)
            option_price = next(option_prices)
        return {
            "Exch": self.exch,
            "ExchType": self.exch_type,
            "Token": scrip_code,
            "LastRate": round(random.uniform(4, 50), 2)
            if not ce_pe
            else option_price[ce_pe],
            "LastQty": random.randint(100, 1000),
            "TotalQty": random.randint(1000000, 10000000),
            "High": round(random.uniform(100, 150), 2),
            "Low": round(random.uniform(50, 100), 2),
            "OpenRate": round(random.uniform(50, 100), 2),
            "PClose": round(random.uniform(50, 100), 2),
            "AvgRate": round(random.uniform(100, 150), 2),
            "Time": int(time.time()),
            "BidQty": random.randint(10, 50),
            "BidRate": round(random.uniform(100, 150), 2),
            "OffQty": random.randint(800, 1200),
            "OffRate": round(random.uniform(100, 150), 2),
            "TBidQ": random.randint(100000, 200000),
            "TOffQ": random.randint(100000, 200000),
            "TickDt": f"/Date({int(time.time())}000)/",
            "ChgPcnt": round(random.uniform(-2, 2), 5),
        }

    def subscribe(self, scrip_codes):
        self.subscriptions.update(scrip_codes)

    def unsubscribe(self, scrip_codes):
        self.subscriptions.difference_update(scrip_codes)

    async def generate_data(self):
        while True:
            for scrip_code in self.subscriptions:
                tick_data = self.generate_tick(scrip_code)
                yield json.dumps([tick_data])
            await asyncio.sleep(1)


class WebSocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.data_generator = MockDataGenerator()
        self.data_queue = asyncio.Queue()
        self.clients = set()

    async def handle_client(self, websocket, path):
        self.clients.add(websocket)
        try:
            async for message in websocket:
                data = json.loads(
                    message
                )  ## {"Operation": Operation, "MarketFeedData": req_list}
                if "Operation" in data:
                    scrip_codes = [req["ScripCode"] for req in data["MarketFeedData"]]
                    if data.get("Operation") == "s":
                        self.data_generator.subscribe(scrip_codes)
                    elif data.get("Operation") == "u":
                        self.data_generator.unsubscribe(scrip_codes)
                elif "placed" in data:
                    await websocket.send(
                        json.dumps(
                            {
                                "Status": "Fully Executed",
                                "ScripCode": data["placed"],
                                "Price": data["Price"],
                                "Qty": data["Qty"],
                                "RemoteOrderID": data["RemoteOrderID"],
                            }
                        )
                    )
        except websockets.exceptions.ConnectionClosedOK:
            pass
        finally:
            self.clients.remove(websocket)

    async def generate_data(self):
        while True:
            for scrip_code in self.data_generator.subscriptions:
                tick_data = self.data_generator.generate_tick(scrip_code)
                data = json.dumps([tick_data])
                for client in self.clients:
                    await client.send(data)
            await asyncio.sleep(1)

    async def start(self):
        start_server = websockets.serve(self.handle_client, self.host, self.port)
        await asyncio.gather(
            start_server,
            self.generate_data(),
        )


if __name__ == "__main__":
    server = WebSocketServer("localhost", 8765)
    asyncio.run(server.start())
