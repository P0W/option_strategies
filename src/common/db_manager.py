import json
import logging
import traceback
from enum import Enum
from typing import List, Optional, Union

import psycopg2
import redis


class OrderStatus(Enum):
    PLACED = "Placed"
    EXECUTED = "Executed"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    PARTIALLY_EXECUTED = "Partially Executed"

    def __str__(self):
        return self.value


class ExchangeType(Enum):
    NSE = "NSE"
    BSE = "BSE"

    def __str__(self):
        return self.value


class OrderType(Enum):
    REGULAR = "R"
    STOPLOSS = "SL"

    def __str__(self):
        return self.value


class ExchangeSegmentType(Enum):
    DERIVATIVE = "Derivative"
    EQUITY = "Equity"
    CURRENCY = "Currency"

    def __str__(self):
        return self.value


# pylint: disable=too-many-arguments,too-few-public-methods
class Order:
    def __init__(
        self,
        code: int,
        quantity: int,
        buy_sell: str,
        status: OrderStatus,
        avg_price: float,
        order_type: OrderType,
        comment: str = "",
        exchange_order_id: str = "",
        remote_order_id: str = "",
    ):
        self.script_code = code
        self.quantity = quantity
        self.buy_sell = buy_sell
        self.status = status
        self.avg_price = avg_price
        self.order_type = order_type
        self.comment = comment
        self.exchange_order_id = exchange_order_id
        self.remote_order_id = remote_order_id


class OrderRepository:
    def __init__(
        self, connection: psycopg2.extensions.connection, redis_client: redis.Redis
    ):
        self.connection = connection
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)

    def insert_order(self, order: Order, **kwargs) -> int:
        try:
            with self.connection:
                cursor = self.connection.cursor()

                ## get scrip name exchangeTye and exchange segment from kwargs, use null if not present
                scrip_name = kwargs.get("scrip_name", None)
                exchange_type = ExchangeType(kwargs.get("exchange_type", None))
                exchange_segment = ExchangeSegmentType(
                    kwargs.get("exchange_segment", None)
                )

                ## update scrips table on conflict disregard
                scrip_sql = """
                    INSERT INTO scrips (script_code, script_name, exchange, exchange_segment)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (script_code) DO NOTHING
                """
                cursor.execute(
                    scrip_sql,
                    (
                        order.script_code,
                        scrip_name,
                        exchange_type.value,
                        exchange_segment.value,
                    ),
                )
                sql = """
                    INSERT INTO orders (remote_order_id, exchange_order_id, 
                    script_code, quantity, buy_sell, avg_price, 
                    status, order_type,  comment)
                    VALUES (%s, %s, %s, %s, %s, %s,%s, %s,%s)
                    RETURNING order_id
                """
                cursor.execute(
                    sql,
                    (
                        order.remote_order_id,
                        order.exchange_order_id,
                        order.script_code,
                        order.quantity,
                        order.buy_sell,
                        order.avg_price,
                        order.status.value,
                        order.order_type.value,
                        order.comment,
                    ),
                )
                order_id = cursor.fetchone()[0]
                self._clear_cached_orders()
                self.logger.info("Inserted order with ID: %s", order_id)
                return order_id
        except Exception as exp:
            self.connection.rollback()
            self.logger.error("Failed to insert order: %s", exp)
            raise

    def fetch_orders(self, search: Optional[Union[str, int]] = None) -> List[Order]:
        try:
            cached_orders = self.redis_client.get(self._get_cache_key(search))
            if False and cached_orders:
                orders = self._deserialize_orders(cached_orders)
            else:
                orders = self._fetch_orders_from_database(search)
                self._cache_orders(orders, search)
            return orders
        except Exception as exp:
            self.logger.error("Failed to fetch orders: %s", exp)
            raise

    def _clear_cached_orders(self):
        self.redis_client.delete("all_orders")

    def _get_cache_key(self, search: Optional[Union[str, int]]) -> str:
        return f"orders_{search}"

    def _cache_orders(self, orders: List[Order], search: Optional[Union[str, int]]):
        if search is not None:
            cache_key = self._get_cache_key(search)
            serialized_orders = self._serialize_orders(orders)
            self.redis_client.set(cache_key, serialized_orders)
            self.logger.info("Cached orders for search: %s", search)

    def _serialize_orders(self, orders: List[Order]) -> str:
        return json.dumps([json.dumps(order.__dict__) for order in orders])

    def _deserialize_orders(self, serialized_orders: str) -> List[Order]:
        orders_data = json.loads(serialized_orders)
        return [Order(**json.loads(order)) for order in orders_data]

    def _fetch_orders_from_database(
        self, search: Optional[Union[str, int]] = None
    ) -> List[Order]:
        try:
            cursor = self.connection.cursor()
            if isinstance(search, int):
                sql = "SELECT * FROM orders WHERE script_code = %s"
                params = (search,)
            elif isinstance(search, str):
                sql = "SELECT * FROM orders WHERE remote_order_id = %s"
                params = (search,)
            else:
                sql = "SELECT * FROM orders"
                params = None
            self.logger.info("Executing query: %s | %s", sql, params)

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            orders = [
                Order(
                    remote_order_id=row[0],
                    code=row[3],
                    quantity=row[4],
                    buy_sell=row[5],
                    avg_price=row[6],
                    status=OrderStatus(row[7]),
                    order_type=OrderType(row[8]),
                )
                for row in rows
            ]

            self.logger.info("Fetched %d orders from database", len(orders))
            return orders
        except Exception as exp:
            self.logger.error("Failed to fetch orders from database: %s", exp)
            self.logger.error("Stack Trace :%s", traceback.format_exc())
            raise

    def update_order(self, **kwargs):
        try:
            with self.connection:
                cursor = self.connection.cursor()
                remote_order_id = kwargs.get("remote_order_id", None)
                comment = kwargs.get("comment", None)
                avg_price = float(kwargs.get("avg_price", None))
                qunantity = int(kwargs.get("quantity", None))
                status = OrderStatus(kwargs.get("status", None))
                sql = """
                    UPDATE orders SET status = %s, avg_price = %s, comment = %s, quantity = %s
                    WHERE remote_order_id = %s
                """
                cursor.execute(
                    sql,
                    (status.value, avg_price, comment, qunantity, remote_order_id),
                )
                self._clear_cached_orders()
                self.logger.info("Updated order with ID: %s", order.remote_order_id)
        except Exception as exp:
            self.connection.rollback()
            self.logger.error("Failed to update order: %s", exp)
            raise


# pylint: disable=too-few-public-methods,not-context-manager
class DatabaseConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls.db_params = {
                "dbname": "order_manager",
                "user": "admin",
                "password": "admin",
                "host": "localhost",
                "port": "5432",
            }
            cls._instance = super().__new__(cls)
            conn_string = f"dbname={cls.db_params['dbname']} user={cls.db_params['user']}\
            password={cls.db_params['password']}"
            cls._instance.connection = psycopg2.connect(conn_string)
        return cls._instance


## Example usage:
if __name__ == "__main__":
    db_conn = DatabaseConnection()
    order_repo = OrderRepository(db_conn.connection, redis.Redis(host="127.0.0.1"))
    order = Order(
        remote_order_id="straddle_1234",
        exchange_order_id="4242123618",
        code=61842,
        quantity=400,
        buy_sell="S",
        avg_price=123.45,
        status=OrderStatus.EXECUTED,
        order_type=OrderType.REGULAR,
    )
    # order_repo.insert_order(order, scrip_name="NIFTY CE SEP 28 2023 20500.00",
    #                         exchange_type=ExchangeType.NSE,
    #                         exchange_segment=ExchangeSegmentType.DERIVATIVE)
    orders = order_repo.fetch_orders()
    ## display orders
    for order in orders:
        print(order.__dict__)
    # orders = order_repo.fetch_orders(search=123)
    # print(orders)
    # orders = order_repo.fetch_orders(search="1234")
    # print(orders)
    # orders = order_repo.fetch_orders(search="12345")
    # print(orders)
    # orders = order_repo.fetch_orders(search=12345)
    # print(orders)
    # orders = order_repo.fetch_orders(search=1234)

    order_repo.update_order(
        remote_order_id="12345",
        status=OrderStatus.CANCELLED,
        quantity=200,
        avg_price=123.45,
    )
