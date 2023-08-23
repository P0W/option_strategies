# Author : Prashant Srivastava
import datetime
import json
import logging
import time

from src.clients.iclientmanager import IClientManager
from src.common import live_feed_manager


# This class is responsible for placing orders, monitoring them and squaring off
# Currently its too much tied to 5paisa, need to make it generic
class OrderManager:
    def __init__(self, client: IClientManager, config) -> None:
        self.client = client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.live_feed_mgr = None
        self.target_achieved = False
        self.exchange_type = "D"

    def set_exchange_type(self, exch_type: str) -> str:
        self.exchange_type = exch_type

    def place_short(self, strikes: dict, tag: str) -> None:
        for item in ["ce", "pe"]:
            # strikes["%s_ltp" % item] # Market Order if price =0.0
            price = 0.0
            scrip_code = strikes[f"{item}_code"]
            textinfo = f"""client.place_order(OrderType='S',
                                  Exchange='N',
                                  ExchangeType={self.exchange_type},
                                  ScripCode={scrip_code},
                                  Qty={self.config["QTY"]},
                                  Price={price}, IsIntraday=True,
                                  RemoteOrderID={tag})"""

            self.logger.debug(textinfo)
            order_status = self.client.place_order(
                OrderType="S",
                Exchange="N",
                ExchangeType=self.exchange_type,
                ScripCode=scrip_code,
                Qty=self.config["QTY"],
                Price=price,
                IsIntraday=True,
                RemoteOrderID=tag,
            )
            if order_status["Message"] == "Success":
                self.logger.debug("%s_done", item)
            time.sleep(2)

    def aggregate_sl_orders(self, tag: str, sl_factor=1.65):
        sl_details = None
        response = self.client.get_tradebook()
        if response:
            trade_book = response["TradeBookDetail"]
            response = self.client.fetch_order_status(
                [{"Exch": "N", "RemoteOrderID": tag}]
            )
            if response:
                order_status = response["OrdStatusResLst"]
                sl_exch_order_ids = [
                    int(x["ExchOrderID"])
                    for x in order_status
                    if x["PendingQty"] == 0 and x["Status"] == "Fully Executed"
                ]
                for items in trade_book:
                    exch_order_id = int(items["ExchOrderID"])
                    if exch_order_id not in sl_exch_order_ids:
                        continue
                    scrip_code = items["ScripCode"]
                    if sl_details is None:
                        sl_details = {}
                    if scrip_code not in sl_details:
                        sl_details[scrip_code] = {
                            "Rate": 0,
                            "Qty": 0,
                            "Premium": 0,
                            "Avg": 0,
                            "max_loss": 0,
                            "sl": 0,
                            "higher_price": 0,
                        }
                    sl_details[scrip_code]["Rate"] += items["Rate"]
                    sl_details[scrip_code]["Qty"] += items["Qty"]
                    sl_details[scrip_code]["Premium"] += items["Rate"] * items["Qty"]
                    sl_details[scrip_code]["Avg"] = (
                        sl_details[scrip_code]["Premium"]
                        / sl_details[scrip_code]["Qty"]
                        if sl_details[scrip_code]["Qty"] != 0
                        else 0
                    )

                    sl_details[scrip_code]["sl"] = int(
                        sl_details[scrip_code]["Avg"] * sl_factor
                    )
                    sl_details[scrip_code]["higher_price"] = (
                        sl_details[scrip_code]["sl"] + 0.5
                    )
                    sl_details[scrip_code]["max_loss"] = (
                        sl_details[scrip_code]["higher_price"]
                        - sl_details[scrip_code]["Avg"]
                    ) * sl_details[scrip_code]["Qty"]
            else:
                self.logger.warning("No Order Status found for %s", tag)
        else:
            self.logger.warning("No TradeBookDetail found for %s", tag)
        return sl_details

    # Client APIs split the fully executed order into multiple orders,
    # so we need to aggregate them based on scrip code
    # This is done to reduce brokerage when sl hits, we want one sl order to
    # be executed, instead of multiple orders
    def place_short_stop_loss_v2(self, tag: str, retries: int = 0) -> None:
        while retries < 3:
            sl_details = self.aggregate_sl_orders(tag)
            if sl_details is None:
                self.logger.info(
                    "No fully executed Orders found for %s waiting for 2 seconds", tag
                )
                retries += 1
                time.sleep(2)
            else:
                break
        if sl_details is None:
            self.logger.error(
                "No fully executed Orders found for %s in %d retries", tag, retries
            )
            return
        max_premium = 0.0
        max_loss = 0.0
        for scrip_code, detail in sl_details.items():
            self.logger.info("Placing stop loss for %s", scrip_code)
            self.logger.info(
                "Placing order ScripCode=%d QTY=%d Trigger Price = %f Stop Loss Price = %f",
                scrip_code,
                detail["Qty"],
                detail["sl"],
                detail["higher_price"],
            )
            self.logger.info("USING STOPLOSS TAG:%s", ("sl" + tag))
            order_status = self.client.place_order(
                OrderType="B",
                Exchange="N",
                ExchangeType=self.exchange_type,
                ScripCode=scrip_code,
                Qty=detail["Qty"],
                Price=detail["higher_price"],
                StopLossPrice=detail["sl"],
                IsIntraday=True,
                RemoteOrderID="sl" + tag,
            )
            max_premium += detail["Premium"]
            max_loss -= detail["max_loss"]
            if order_status["Message"] == "Success":
                self.logger.info("Placed for %d", scrip_code)
            else:
                self.logger.error("Failed to place stop loss for %d", scrip_code)
            time.sleep(0.5)

        self.logger.info("Collecting Maximum Premium of :%f INR", max_premium)
        self.logger.info("Maximum Loss of :%f INR", max_loss)

    def debug_status(self, tag: str) -> None:
        order_status = self.client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": tag}]
        )["OrdStatusResLst"]
        self.logger.debug("Order Status %s", json.dumps(order_status, indent=2))
        trdbook = self.client.get_tradebook()["TradeBookDetail"]
        self.logger.debug("Trade Book %s", json.dumps(trdbook, indent=2))
        self.logger.debug(
            "Order Book %s", json.dumps(self.client.order_book(), indent=2)
        )

    def pnl(self, tag: str) -> float:
        positions = self.client.get_pnl_summary(tag)
        total = 0.0
        if positions:
            for item in positions:
                self.logger.info("%s : %.2f", item["ScripName"], item["Pnl"])
                total += item["Pnl"]
        return total

    def get_sl_pending_orders(self, sl_tag: str):
        order_status = self.client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": sl_tag}]
        )["OrdStatusResLst"]
        # get all ExchOrderID from r where "PendingQty" is not 0, Status is
        # "Pending"
        sl_exch_order_ids = [
            {"ExchOrderID": f"{x['ExchOrderID']}"}
            for x in order_status
            if x["PendingQty"] != 0 and x["Status"] == "Pending"
        ]

        return sl_exch_order_ids

    def reverse_order(self, buysell: str) -> str:
        return "S" if buysell == "B" else "B"

    def intraday(self, intra):
        return intra == "I"

    def square_off_price(self, rate: float) -> float:
        # To account for slippages
        # We want the order to be placed at 0.5% higher/(lower for sell) than
        # LTP, to increase the chances of execution
        return round(
            round(rate * 2) / 2, 2
        )  # Round to nearest 0.05 (considering same tick size)

    def squareoff(self, tag: str, strikes: dict) -> None:
        exchange_order_list = []
        keep_polling = False
        placed_sq_off = 0
        order_status = self.client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": tag}]
        )["OrdStatusResLst"]
        for order in order_status:
            eoid = order["ExchOrderID"]
            if eoid != "":
                exchange_order_list.append(eoid)
        trade_book = self.client.get_tradebook()["TradeBookDetail"]
        for eoid in exchange_order_list:
            for trade in trade_book:
                if eoid == int(trade["ExchOrderID"]):
                    buysell_type = self.reverse_order(trade["BuySell"])
                    scrip = trade["ScripCode"]
                    qty = trade["Qty"]
                    segment = trade["ExchType"]
                    ltp = self.square_off_price(rate=strikes[scrip])
                    is_intraday = trade["DelvIntra"]
                    scrip_name = trade["ScripName"]
                    self.logger.info(
                        "Square off: ScripCode:%d | ScripName:%s | Price:%.2f | Qty:%d | Tag:%s",
                        scrip,
                        scrip_name,
                        ltp,
                        qty,
                        "sq" + tag,
                    )
                    self.logger.info(
                        """place_order(
                        OrderType=%s,
                        Exchange="N",
                        ExchangeType=%s,
                        ScripCode=%d,
                        Qty=%d,
                        Price=%f,
                        IsIntraday=%s,
                        StopLossPrice=0.0,
                        RemoteOrderID=%s,
                    )""",
                        buysell_type,
                        segment,
                        scrip,
                        qty,
                        ltp,
                        self.intraday(is_intraday),
                        "sq" + tag,
                    )
                    order_status = self.client.place_order(
                        OrderType=buysell_type,
                        Exchange="N",
                        ExchangeType=segment,
                        ScripCode=scrip,
                        Qty=qty,
                        Price=ltp,
                        StopLossPrice=0.0,
                        IsIntraday=self.intraday(is_intraday),
                        RemoteOrderID="sq" + tag,
                    )
                    if order_status["Message"] == "Success":
                        self.logger.info("Square off order Placed for %d", scrip)
                        placed_sq_off = placed_sq_off + 1

        # Wait till all orders are squared off
        keep_polling = placed_sq_off > 0
        retries = 0
        while keep_polling:
            order_book = self.client.order_book()
            if order_book:
                order_status = {
                    order["ScripCode"]: order["OrderStatus"]
                    for order in order_book
                    if order["RemoteOrderID"] == "sq" + tag
                }
                if order_status:
                    if any(
                        "Placed" in status or "Partially Executed" in status
                        for status in order_status.values()
                    ):
                        keep_polling = True
                        self.logger.info(
                            "Waiting for square off orders to be executed/rejected"
                        )
                        time.sleep(2)
                    else:
                        keep_polling = False
                        self.logger.info("All orders executed or rejected")

                else:
                    keep_polling = False
                    self.logger.info(
                        "No matching %s tag found %s",
                        "sq" + tag,
                        json.dumps(order_book, indent=2),
                    )
            else:
                # At times 5paisa API returns empty order_book
                retries = retries + 1
                # if 3 retries are done, then stop polling
                if retries > 3:
                    keep_polling = False
                    self.logger.info("order_book empty")

    def day_over(self, expiry_day: int) -> bool:
        # Look for 15:26 PM on non expiry
        current_time = datetime.datetime.now()

        if (
            current_time.weekday != expiry_day
            and current_time.hour >= 15
            and current_time.minute >= 26
        ):
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
                exch_id = int(order["ExchOrderID"])
                for executed_order in order_status:
                    if exch_id == executed_order["ExchOrderID"]:
                        feeds[executed_order["ScripCode"]] = {
                            "qty": executed_order["OrderQty"],
                            "rate": executed_order["OrderRate"],
                        }
                        break
        return feeds

    def squareoff_sl_order(self, tag: str) -> None:
        sl_exchan_orders = self.get_sl_pending_orders("sl" + tag)
        self.logger.info("Pending stop loss orders %s", json.dumps(sl_exchan_orders))
        self.client.cancel_bulk_order(sl_exchan_orders)

    def monitor_v2(self, target: float, tag: str, expiry_day: int) -> None:
        executed_orders = self.get_executed_orders(tag)
        if len(executed_orders.keys()) == 0:
            self.logger.info("No Executed Orders Found!")
            return
        sl_exchan_orders = self.get_sl_pending_orders("sl" + tag)
        self.live_feed_mgr = live_feed_manager.LiveFeedManager(self.client, {})

        def pnl_calculator(res: dict, items: dict):
            try:
                if self.day_over(items["expiry_day"]):
                    self.logger.info("Day Over!")
                    self.live_feed_mgr.stop()
                    return

                code = res["code"]
                ltp = res["c"]
                # Get user_data from items
                qty = items["executedOrders"][code]["qty"]
                avg = items["executedOrders"][code]["rate"]
                mtm_target = items["mtm_target"]
                # mtm_loss = items["mtm_loss"]
                # Calculate MTM on each leg
                items["strikes"][code] = (avg - ltp) * qty
                # Add LTP for each leg, required for square off
                if "ltp" not in items:
                    items["ltp"] = {}
                items["ltp"][code] = ltp
                freq = items["freq"]

                if len(items["strikes"].keys()) == len(
                    items["executedOrders"].keys()
                ):  # wait for both legs prices availability
                    # calculate MTM summing the pnl of each leg
                    total_pnl = sum(items["strikes"].values())
                    # log when time elaspse since last is more than freq
                    if time.time() - items["last"] > freq:
                        self.logger.info(
                            "Current MTM: %f %s",
                            total_pnl,
                            json.dumps(items["strikes"], indent=2),
                        )
                        items["last"] = time.time()
                    if total_pnl >= mtm_target:
                        # TARGET ACHEIVED
                        self.logger.info(
                            "Current MTM: %f %s",
                            total_pnl,
                            json.dumps(items["strikes"], indent=2),
                        )
                        self.logger.info(
                            "Target Achieved: %f | Profit Threshold %f ",
                            total_pnl,
                            mtm_target,
                        )
                        # Sqaure off both legs
                        self.logger.info("Squaring off both legs")
                        self.squareoff(tag=tag, strikes=items["ltp"])
                        self.logger.info("Cancelling pending stop loss orders")
                        self.squareoff_sl_order(tag=tag)
                        self.logger.info("Stopping live feed")
                        self.live_feed_mgr.stop()
                    # elif total_pnl <= mtm_loss:
                    #     # STOP LOSS HIT
                    #     self.logger.info(
                    #         "Current MTM: %f %s"
                    #         % (total_pnl, json.dumps(items["strikes"], indent=2))
                    #     )
                    #     self.logger.info(
                    #         "Stop Loss Hit: %f | Loss Threshold %f"
                    #         % (total_pnl, mtm_loss)
                    #     )
                    #     # Sqaure off both legs
                    #     self.logger.info("Squaring off both legs")
                    #     self.squareoff(tag=tag, strikes=items["ltp"])
                    #     self.logger.info("Cancelling pending target orders")
                    #     self.client.cancel_bulk_order(items["sl_exchan_orders"])
                    #     self.logger.info("Stopping live feed")
                    #     self.live_feed_mgr.stop()
            except Exception as exp:
                self.logger.error(exp)
                self.live_feed_mgr.stop()

        def order_update(_message: dict, _subs_list: dict, user_data: dict):
            unsubscribe_list = user_data["order_update"]
            if len(unsubscribe_list) == 1 and "mtm_target" in user_data:
                # reduce mtm_target by 50%
                user_data["mtm_target"] = user_data["mtm_target"] / 2
                self.logger.info("Reducing MTM Target to %f", user_data["mtm_target"])
            # if its 0 i.e. both legs are executed, we will eventually
            # gracefully shutdown

        try:
            current_order_state = {
                "strikes": {},
                "sl_exchan_orders": sl_exchan_orders,
                "expiry_day": expiry_day,
                "executedOrders": executed_orders,
                "freq": 15,  # seconds
                "last": time.time(),
                "mtm_target": target,
                # "mtm_loss": -2 * target,
            }
            self.logger.info(
                "user_data: %s",
                json.dumps(
                    current_order_state,
                    indent=2,
                ),
            )
            self.live_feed_mgr.monitor(
                scrip_codes=list(executed_orders.keys()),
                on_scrip_data=pnl_calculator,
                user_data=current_order_state,
                on_order_update=order_update,
            )
        except Exception as exp:
            self.logger.error(exp)

    def modify_stop_loss_order(self, tag: str, scrip_code: int, price: float):
        order_status = self.client.fetch_order_status(
            [{"Exch": "N", "RemoteOrderID": "sl" + tag}]
        )["OrdStatusResLst"]
        for order in order_status:
            eoid = order["ExchOrderID"]
            if eoid != "" and scrip_code == order["ScripCode"]:
                id.append(eoid)
                self.client.modify_order(
                    ExchOrderID=eoid, Price=price + 0.5, StopLossPrice=price
                )
