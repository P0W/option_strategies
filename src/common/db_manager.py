import json
import logging
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


class ExchangeType(Enum):
    NSE = "NSE"
    BSE = "BSE"


class ExchangeSegmentType(Enum):
    DERIVATIVE = "Derivative"
    EQUITY = "Equity"
    CURRENCY = "Currency"


# pylint: disable=too-many-arguments,too-few-public-methods
class Order:
    def __init__(
        self,
        script_code: int,
        quantity: int,
        buy_sell: str,
        status: OrderStatus,
        order_type: str,
        comment: str = "",
        exchange_order_id: str = "",
        remote_order_id: str = "",
    ):
        self.script_code = script_code
        self.quantity = quantity
        self.buy_sell = buy_sell
        self.status = status
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

    def insert_order(self, order: Order) -> int:
        try:
            with self.connection:
                cursor = self.connection.cursor()
                sql = """
                    INSERT INTO orders (script_code, quantity, buy_sell, status, order_type, comment)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING order_id
                """
                cursor.execute(
                    sql,
                    (
                        order.script_code,
                        order.quantity,
                        order.buy_sell,
                        order.status.value,
                        order.order_type,
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
            if cached_orders:
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
        serialized_orders = [json.dumps(order.__dict__) for order in orders]
        return json.dumps(serialized_orders)

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

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            orders = [
                Order(
                    script_code=row[3],
                    quantity=row[4],
                    buy_sell=row[5],
                    status=OrderStatus(row[7]),
                    order_type=row[8],
                    comment=row[9],
                )
                for row in rows
            ]

            self.logger.info("Fetched %d orders from database", len(orders))
            return orders
        except Exception as exp:
            self.logger.error("Failed to fetch orders from database: %s", exp)
            raise


# pylint: disable=too-few-public-methods,not-context-manager
class DatabaseConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls.db_params = {
                "dbname": "order_manager",
                "user": "postgres",
                "password": "postgres",
                "host": "localhost",
                "port": "5432",
            }
            cls._instance = super().__new__(cls)
            conn_string = f"dbname={cls.db_params['dbname']} user={cls.db_params['user']}\
            password={cls.db_params['password']}"
            cls._instance.connection = psycopg2.connect(conn_string)
        return cls._instance


## Example
def main():
    try:
        with DatabaseConnection() as connection:
            redis_client = redis.Redis(host="127.0.0.1")
            repository = OrderRepository(connection, redis_client)

            new_order = Order(
                script_code=123,
                quantity=100,
                buy_sell="B",
                status=OrderStatus.PLACED,
                order_type="SL",
                exchange_order_id="XYZ456",
                remote_order_id="ABC123",
            )
            repository.insert_order(new_order)
    except Exception as exp:
        print("An error occurred: %s", exp)


if __name__ == "__main__":
    main()
