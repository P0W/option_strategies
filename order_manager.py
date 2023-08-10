## Author : Prashant Srivastava
## Last Modified Date  : Aug 10th, 2023

import logging
import time
import json
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

    def reverse_order(self, buysell: str) -> str:
        if buysell == "B":
            return "S"
        if buysell == "S":
            return "B"

    def intraday(self, intra):
        if intra == "I":
            return True
        else:
            return False

    def square_off_price(self, ltp: float, buysell: str) -> float:
        ## To account for slippages
        ## We want the order to be placed at 0.5% higher/(lower for sello) than LTP, to increase the chances of execution
        if buysell == "B":
            return round(ltp * 1.005, 2)
        if buysell == "S":
            return round(ltp * 0.995, 2)

    def squareoff(self, tag: str, strikes: dict) -> None:
        exchange_order_list = []
        order_status = self.client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": tag}]
        )["OrdStatusResLst"]
        for order in order_status:
            eoid = order["ExchOrderID"]
            if eoid != "":
                exchange_order_list.append(eoid)
        tradeBook = self.client.get_tradebook()["TradeBookDetail"]
        for eoid in exchange_order_list:
            for trade in tradeBook:
                if eoid == int(trade["ExchOrderID"]):
                    buysell_type = self.reverse_order(trade["BuySell"])
                    scrip = trade["ScripCode"]
                    qty = trade["Qty"]
                    segment = trade["ExchType"]
                    ltp = self.square_off_price(
                        ltp=strikes[scrip], buysell=buysell_type
                    )
                    isIntraday = trade["IsIntraday"]
                    scripName = trade["ScripName"]
                    self.client.place_order(
                        OrderType=buysell_type,
                        Exchange="N",
                        ExchangeType=segment,
                        ScripCode=scrip,
                        Qty=qty,
                        Price=ltp,
                        IsIntraday=self.intraday(isIntraday),
                        remote_order_id="sq" + tag,
                    )
                    self.logger.info(
                        "Square off: ScripCode:%d | ScripName:%s | Price:%.2f | Qty:%d | Tag:%s"
                        % (scrip, scripName, ltp, qty, "sq" + tag)
                    )

        ## Wait till all orders are squared off
        keepPolling = True
        while keepPolling:
            order_book = self.client.order_book()
            order_status = {
                order["ScripCode"]: order["OrderStatus"]
                for order in order_book
                if order["RemoteOrderID"] == "sq" + tag
            }
            if any([status == "Placed" for status in order_status.values()]):
                keepPolling = True
                self.logger.info(
                    "Waiting for square off orders to be executed/rejected"
                )
                time.sleep(2)
            else:
                keepPolling = False
                self.logger.info("All orders executed or rejected")

    def day_over(self, expiry_day: int) -> bool:
        ## Look for 15:26 PM on non expiry
        current_time = datetime.datetime.now()

        if (
            current_time.weekday != expiry_day
            and current_time.hour >= 15
            and current_time.minute >= 26
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

        # @TODO filter out closed orders
        # scripsCodes = list(feeds.keys())
        # tradeBookDetail = self.client.get_tradebook()["TradeBookDetail"]
        # filteredTradeBook = list(filter(lambda x: x["ScripCode"] in scripsCodes and x["BuySell"] == "B", tradeBookDetail))
        # for f in filteredTradeBook:
        #     if f["ScripCode"] in feeds:
        #         self.logger.info("Got a Buy Trade for %s %f" % (f["ScripCode"], f["Qty"]))
        #         feeds[f["ScripCode"]]["qty"] -= f["Qty"]
        #         if feeds[f["ScripCode"]]["qty"] == 0:
        #             feeds.pop(f["ScripCode"])

        return feeds

    def monitor_v2(self, target: float, tag: str, expiry_day: int) -> None:
        executedOrders = self.get_executed_orders(tag)
        if len(executedOrders.keys()) == 0:
            self.logger.info("No Executed Orders Found!")
            return
        sl_exchan_orders = self.get_sl_pending_orders("sl" + tag)
        self.lm = live_feed_manager.LiveFeedManager(self.client, {})

        def pnl_calculator(res: dict, items: dict):
            try:
                if self.day_over(items["expiry_day"]):
                    self.logger.info("Day Over!")
                    self.lm.stop()
                    return

                code = res["code"]
                ltp = res["c"]
                ## Get user_data from items
                qty = items["executedOrders"][code]["qty"]
                avg = items["executedOrders"][code]["rate"]
                mtm_target = items["mtm_target"]
                mtm_loss = items["mtm_loss"]
                ## Calculate MTM on each leg
                items["strikes"][code] = (avg - ltp) * qty
                freq = items["freq"]

                if len(items["strikes"].keys()) == len(
                    items["executedOrders"].keys()
                ):  ## wait for both legs prices availability
                    ## calculate MTM summing the pnl of each leg
                    total_pnl = sum(items["strikes"].values())
                    ## log when time elaspse since last is more than freq
                    if time.time() - items["last"] > freq:
                        self.logger.info(
                            "Current MTM: %f %s"
                            % (total_pnl, json.dumps(items["strikes"], indent=2))
                        )
                        items["last"] = time.time()
                    if total_pnl >= mtm_target:
                        # TARGET ACHEIVED
                        self.logger.info(
                            "Current MTM: %f %s"
                            % (total_pnl, json.dumps(items["strikes"], indent=2))
                        )
                        self.logger.info(
                            "Target Achieved: %f | Profit Threshold %f "
                            % (total_pnl, mtm_target)
                        )
                        # Sqaure off both legs
                        self.logger.info("Squaring off both legs")
                        self.squareoff(tag=tag, strikes=items["strikes"])
                        self.logger.info("Cancelling pending stop loss orders")
                        self.client.cancel_bulk_order(items["sl_exchan_orders"])
                        self.logger.info("Stopping live feed")
                        self.lm.stop()
                    elif total_pnl <= mtm_loss:
                        # STOP LOSS HIT
                        self.logger.info(
                            "Current MTM: %f %s"
                            % (total_pnl, json.dumps(items["strikes"], indent=2))
                        )
                        self.logger.info(
                            "Stop Loss Hit: %f | Loss Threshold %f"
                            % (total_pnl, mtm_loss)
                        )
                        # Sqaure off both legs
                        self.logger.info("Squaring off both legs")
                        self.squareoff(tag=tag, strikes=items["strikes"])
                        self.logger.info("Cancelling pending target orders")
                        self.client.cancel_bulk_order(items["sl_exchan_orders"])
                        self.logger.info("Stopping live feed")
                        self.lm.stop()
            except Exception as e:
                self.logger.error(e)
                self.lm.stop()

        try:
            current_order_state = {
                "strikes": {},
                "sl_exchan_orders": sl_exchan_orders,
                "expiry_day": expiry_day,
                "executedOrders": executedOrders,
                "freq": 15,  # seconds
                "last": time.time(),
                "mtm_target": target,
                "mtm_loss": -2 * target,
            }
            self.logger.info(
                "user_data: %s"
                % json.dumps(
                    current_order_state,
                    indent=2,
                )
            )
            self.lm.monitor(
                scrip_codes=list(executedOrders.keys()),
                on_scrip_data=pnl_calculator,
                user_data=current_order_state,
            )
        except Exception as e:
            self.logger.error(e)
