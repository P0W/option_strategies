## Author : Prashant Srivastava
## Last Modified Date  : Dec 25th, 2022

import logging
import time
import json
import threading
import datetime


class Ordermanager:
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
        print(json.dumps(r, indent=2))
        trdbook = self.client.get_tradebook()["TradeBookDetail"]
        print(json.dumps(trdbook, indent=2))

    def pnl(self) -> float:
        positions = self.client.positions()
        mtom = 0.0
        for item in positions:
            mtom += item["MTOM"]
        return mtom

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
            and current_time.minute >= 20
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
                self.logger.info("MTM = %.2f" % mtom)
                time.sleep(5)
            self.logger.info("Not Monitoring Day Over!")

        th = threading.Thread(target=poll, args=())
        th.start()
        th.join()
        return
