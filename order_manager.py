## Author : Prashant Srivastava
## Last Modified Date  : Dec 25th, 2022

import logging
import time
import json
import threading
import datetime
import live_feed_manager


class OrderManager:
    def __init__(self, client, config) -> None:
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)

    def place_short(self, strikes: dict, tag: str) -> None:
        for item in ["ce", "pe"]:
            price = 0.0  # strikes["%s_ltp" % item] # Market Order if price =0.0
            textinfo = """client.place_order(OrderType='S', 
                                            Exchange='N', 
                                            ExchangeType='D', 
                                            ScripCode=%d,
                                            Qty=%d,
                                            Price=%f, IsIntraday=True,
                                            RemoteOrderID=%s)""" % (
                strikes["%s_code" % item],
                self.config["QTY"],
                price,
                tag,
            )
            self.logger.info(textinfo)
            order_status = self.client.place_order(
                OrderType="S",
                Exchange="N",
                ExchangeType="D",
                ScripCode=strikes["%s_code" % item],
                Qty=self.config["QTY"],
                Price=price,
                IsIntraday=True,
                RemoteOrderID=tag,
            )
            if order_status["Message"] == "Success":
                self.logger.info("%s_done" % item)

    def place_short_stop_loss(self, tag: str) -> None:
        self.logger.info("Fetching order status for %s" % tag)
        id = []
        while len(id) != 2:
            r = self.client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
                "OrdStatusResLst"
            ]
            for order in r:
                eoid = order["ExchOrderID"]
                self.logger.info("ExchOrderID: %d" % eoid)
                if eoid != "":
                    id.append(eoid)
            self.logger.info("Waiting for order execution")
            time.sleep(5)

        self.logger.info("Fetching TradeBookDetail for %s" % tag)
        trdbook = self.client.get_tradebook()["TradeBookDetail"]
        max_premium = 0.0
        for eoid in id:
            for trade in trdbook:
                if eoid == int(trade["ExchOrderID"]):
                    scrip = trade["ScripCode"]
                    self.logger.info(
                        "Matched for ExchOrderID: %d for Scrip: %d. Placing Stop Loss at %f times"
                        % (eoid, scrip, self.config["SL_FACTOR"])
                    )
                    qty = trade["Qty"]
                    avgprice = trade["Rate"]
                    max_premium += avgprice * qty
                    sl = int(avgprice * self.config["SL_FACTOR"])
                    higher_price = sl + 0.5
                    self.logger.info(
                        "Placing order ScripCode=%d QTY=%d Trigger Price = %f Stop Loss Price = %f"
                        % (scrip, qty, sl, higher_price)
                    )
                    self.logger.info("USING STOPLOSS TAG:%s" % ("sl" + tag))
                    order_status = self.client.place_order(
                        OrderType="B",
                        Exchange="N",
                        ExchangeType="D",
                        ScripCode=scrip,
                        Qty=qty,
                        Price=higher_price,
                        StopLossPrice=sl,
                        IsIntraday=True,
                        RemoteOrderID="sl" + tag,
                    )
                    if order_status["Message"] == "Success":
                        self.logger.info("Placed for %d" % scrip)
        self.logger.info("Collecting Maximum Premium of :%f INR" % max_premium)

    def debug_status(self, tag: str) -> None:
        r = self.client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
            "OrdStatusResLst"
        ]
        print("Order Status", json.dumps(r, indent=2))
        trdbook = self.client.get_tradebook()["TradeBookDetail"]
        print("Trade Book", json.dumps(trdbook, indent=2))
        print("Order Book", json.dumps(self.client.order_book(), indent=2))
        # print("Positions", print(json.dumps(self.client.positions(), indent=2)))

    def pnl(self) -> float:
        positions = self.client.positions()

        mtom = 0.0
        if positions:
            for item in positions:
                mtom += item["MTOM"]
        return mtom

    def cancel_pendings(self, tag: str) -> None:
        orderbook = self.client.order_book()
        pending_orders = list(
            filter(lambda x: x["RemoteOrderID"] == "sl" + tag, orderbook)
        )
        for order in pending_orders:
            if order["OrderStatus"] == "Pending":
                self.logger.info(
                    "Cancelled Exchange Order ID %d" % order["ExchOrderID"]
                )
                self.client.cancel_order(exch_order_id=order["ExchOrderID"])

    def squareoff(self, tag: str) -> None:
        id = []
        r = self.client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
            "OrdStatusResLst"
        ]
        for order in r:
            eoid = order["ExchOrderID"]
            if eoid != "":
                id.append(eoid)
        trdbook = self.client.get_tradebook()["TradeBookDetail"]
        for eoid in id:
            for trade in trdbook:
                if eoid == int(trade["ExchOrderID"]):
                    buysell_type = "B"
                    intra = trade["DelvIntra"]
                    scrip = trade["ScripCode"]
                    qty = trade["Qty"]
                    segment = trade["ExchType"]
                    order_status = self.client.place_order(
                        OrderType=buysell_type,
                        Exchange="N",
                        ExchangeType=segment,
                        ScripCode=scrip,
                        Qty=qty,
                        Price=0,
                        IsIntraday=True,
                        remote_order_id=tag,
                    )
                else:
                    continue

    def day_over(self, expiry_day: int) -> bool:
        ## Look for 15:20 PM on non expiry
        current_time = datetime.datetime.now()

        if (
            current_time.weekday != expiry_day
            and current_time.hour >= 15
            and current_time.minute >= 24
        ):
            return True

        elif (
            current_time.weekday == expiry_day
            and current_time.hour >= 15
            and current_time.minute >= 31
        ):
            ## On expiry day stop this thread after 15:31 PM
            ## The contract will expire worthless or stop loss must have triggered
            return True
        return False

    def monitor(self, target: float, tag: str, expiry_day: int) -> None:
        def poll():
            while not self.day_over(expiry_day):
                mtom = self.pnl()
                if mtom >= target:
                    ## TARGET ACCHEIVED
                    ## Sqaure off both legs
                    self.squareoff(tag=tag)
                    self.cancel_pendings(tag=tag)
                    break
                self.logger.info("MTM = %.2f" % mtom)
                time.sleep(5)
            self.logger.info("Not Monitoring Day Over!")

        th = threading.Thread(target=poll, args=())
        th.start()
        th.join()
        return

    def monitor_v2(self, target: float, tag: str, expiry_day: int) -> None:
        orderbook = self.client.order_book()
        pending_orders = list(filter(lambda x: x["RemoteOrderID"] == tag, orderbook))
        feeds = {}
        r = self.client.fetch_order_status([{"Exch": "N", "RemoteOrderID": tag}])[
            "OrdStatusResLst"
        ]

        for order in pending_orders:
            if order["OrderStatus"] == "Fully Executed":
                exchId = int(order["ExchOrderID"])
                print(exchId)
                for executed_order in r:
                    if exchId == executed_order["ExchOrderID"]:
                        feeds[executed_order["ScripCode"]] = (
                            executed_order["OrderQty"],
                            executed_order["OrderRate"],
                        )
                        break

        self.items = {}

        def pnl_calculator(res: dict):
            code = res["code"]
            ltp = res["c"]
            qty = feeds[code][0]
            avg = feeds[code][1]
            self.items[code] = (avg - ltp) * qty
            if len(self.items.keys()) == 2:
                pnl = 0.0
                for k, v in self.items.items():
                    pnl += v
                self.items = {}
                if pnl >= target:
                    # TARGET ACCHEIVED
                    # Sqaure off both legs
                    self.squareoff(tag=tag)
                    self.cancel_pendings(tag=tag)
                self.logger.info("Tag = %s MTM = %.2f" % (tag, pnl))

        lm = live_feed_manager.LiveFeedManager(self.client, {})
        lm.monitor(list(feeds.keys()), pnl_calculator)
