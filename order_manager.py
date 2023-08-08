## Author : Prashant Srivastava
## Last Modified Date  : Aug 7th, 2023

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
        self.lm = None
        self.target_achieved = False

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
            self.logger.debug(textinfo)
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
                self.logger.debug("%s_done" % item)
            time.sleep(2)

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
            time.sleep(2)

        self.logger.info("Fetching TradeBookDetail for %s" % tag)
        trdbook = self.client.get_tradebook()["TradeBookDetail"]
        max_premium = 0.0
        max_loss = 0.0
        for eoid in id:
            for trade in trdbook:
                if eoid == int(trade["ExchOrderID"]):
                    scrip = trade["ScripCode"]
                    self.logger.debug(
                        "Matched for ExchOrderID: %d for Scrip: %d. Placing Stop Loss at %f times"
                        % (eoid, scrip, self.config["SL_FACTOR"])
                    )
                    qty = trade["Qty"]
                    avgprice = trade["Rate"]
                    max_premium += avgprice * qty

                    sl = int(avgprice * self.config["SL_FACTOR"])
                    higher_price = sl + 0.5
                    max_loss -= (higher_price - avgprice) * qty
                    self.logger.debug(
                        "Placing order ScripCode=%d QTY=%d Trigger Price = %f Stop Loss Price = %f"
                        % (scrip, qty, sl, higher_price)
                    )
                    self.logger.debug("USING STOPLOSS TAG:%s" % ("sl" + tag))
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
                    time.sleep(2)
        self.logger.info("Collecting Maximum Premium of :%f INR" % max_premium)
        self.logger.info("Maximum Loss of :%f INR" % max_loss)

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

    @DeprecationWarning
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

    def get_sl_pending_orders(self, slTag: str):
        r = self.client.fetch_order_status([{"Exch": "N", "RemoteOrderID": slTag}])[
            "OrdStatusResLst"
        ]
        ## get all ExchOrderID from r where "PendingQty" is not 0, Status is "Placed"
        slExchOrderIDs = [
            {"ExchOrderID": "%s" % x["ExchOrderID"]}
            for x in r
            if x["PendingQty"] != 0 and x["Status"] == "Placed"
        ]
        return slExchOrderIDs

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

    @DeprecationWarning
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
                self.logger.debug("MTM = %.2f" % mtom)
                time.sleep(5)
            self.logger.info("Not Monitoring Day Over!")

        th = threading.Thread(target=poll, args=())
        th.start()
        th.join()
        return

    def get_executed_orders(self, tag: str) -> dict:
        orderbook = self.client.order_book()
        pending_orders = list(filter(lambda x: x["RemoteOrderID"] == tag, orderbook))
        feeds = {}
        order_status = self.client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": tag}]
        )["OrdStatusResLst"]

        for order in pending_orders:
            if order["OrderStatus"] == "Fully Executed":
                exchId = int(order["ExchOrderID"])
                for executed_order in order_status:
                    if exchId == executed_order["ExchOrderID"]:
                        feeds[executed_order["ScripCode"]] = {
                            "qty": executed_order["OrderQty"],
                            "rate": executed_order["OrderRate"],
                        }
                        break
        return feeds

    def monitor_v2(self, target: float, tag: str, expiry_day: int) -> None:
        executedOrders = self.get_executed_orders(tag)
        sl_exchan_orders = self.get_sl_pending_orders("sl" + tag)
        self.lm = live_feed_manager.LiveFeedManagerV2(self.client, {})

        def pnl_calculator(res: dict, target: float, mtm_loss: float, items: dict):
            try:
                if self.day_over(items["expiry_day"]):
                    self.logger.info("Day Over!")
                    self.lm.stop()
                    return

                code = res["code"]
                ltp = res["c"]
                qty = items["executedOrders"][code]["qty"]
                avg = items["executedOrders"][code]["rate"]
                items["strikes"][code] = (avg - ltp) * qty

                if (
                    len(items["strikes"].keys()) == 2
                ):  ## wait for both legs prices availability
                    ## calculate MTM summing the pnl of each leg
                    total_pnl = sum(items["strikes"].values())
                    logging.info(
                        "Current MTM: %f %s"
                        % (total_pnl, json.dumps(items["strikes"], indent=3))
                    )
                    if total_pnl >= target:
                        # TARGET ACHEIVED
                        self.logging.info("Target Achieved: %f" % total_pnl)
                        # Sqaure off both legs
                        self.logging.info("Squaring off both legs")
                        self.squareoff(tag=tag)
                        self.logging.info("Cancelling pending stop loss orders")
                        self.client.cancel_bulk_order(items["sl_exchan_orders"])
                        self.logging.info("Stopping live feed")
                        self.lm.stop()
                    elif total_pnl <= mtm_loss:
                        # STOP LOSS HIT
                        self.logging.info("Stop Loss Hit: %f" % total_pnl)
                        # Sqaure off both legs
                        self.logging.info("Squaring off both legs")
                        self.squareoff(tag=tag)
                        self.logging.info("Cancelling pending target orders")
                        self.client.cancel_bulk_order(items["sl_exchan_orders"])
                        self.logging.info("Stopping live feed")
                        self.lm.stop()
            except Exception as e:
                self.logger.error(e)

        try:
            self.logger.info(
                "user_data: %s"
                % json.dumps(
                    {
                        "strikes": {},
                        "sl_exchan_orders": sl_exchan_orders,
                        "expiry_day": expiry_day,
                        "executedOrders": executedOrders,
                    },
                    indent=3,
                )
            )
            self.lm.monitor(
                list(executedOrders.keys()),
                callback=pnl_calculator,
                target_profit=target,
                max_stop_loss=-2 * target,
                user_data={
                    "strikes": {},
                    "sl_exchan_orders": sl_exchan_orders,
                    "expiry_day": expiry_day,
                    "executedOrders": executedOrders,
                },
            )
        except Exception as e:
            self.logger.error(e)
