import logging
import psycopg2
from psycopg2.extras import execute_values


class TimescaleDB:
    def __init__(self, db_params):
        self.db_params = db_params
        self.connection = None
        self.cursor = None
        self.logger = logging.getLogger(__name__)

    def connect(self, db_name=None):
        if self.connection and self.cursor and not db_name:
            return
        if db_name:
            conn_string = f"dbname={db_name} user={self.db_params['user']}\
            password={self.db_params['password']}"
        else:
            conn_string = (
                f"user={self.db_params['user']} password={self.db_params['password']}"
            )
        self.connection = psycopg2.connect(dsn=conn_string)
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()

        # Perform database operations here
        self.cursor.execute("SELECT version();")
        db_version = self.cursor.fetchone()
        self.logger.info("Connected to %s", db_version)

    def disconnect(self):
        self.cursor.close()
        self.connection.close()
        self.connection = None
        self.cursor = None

    def create_database(self):
        self.connect()

        try:
            create_db_query = f"CREATE DATABASE {self.db_params['dbname']};"
            self.cursor.execute(create_db_query)
            self.connection.commit()
            self.logger.info(
                "Database '%s' created successfully.", self.db_params["dbname"]
            )
        except Exception:
            self.logger.info("Database '%s' already exists.", self.db_params["dbname"])

    def drop_database(self):
        self.connect()

        try:
            drop_db_query = f"DROP DATABASE {self.db_params['dbname']};"
            ## drop table
            drop_table_query = "DROP TABLE IF EXISTS option_data CASCADE;"
            self.cursor.execute(drop_table_query)
            drop_table_query = "DROP TABLE IF EXISTS strikes CASCADE;"
            self.cursor.execute(drop_table_query)
            self.cursor.execute(drop_db_query)
            self.connection.commit()
            self.logger.info(
                "Database '%s' dropped successfully.", self.db_params["dbname"]
            )
        except Exception:
            self.logger.info("Database '%s' does not exist.", self.db_params["dbname"])
        self.disconnect()

    def create_tables(self, db_name=None):
        self.connect(db_name)

        create_strikes_table = """
        CREATE TABLE IF NOT EXISTS strikes (
            strike_id SERIAL PRIMARY KEY,
            strike_name TEXT UNIQUE
        );
        """

        create_option_data_table = """
        CREATE TABLE IF NOT EXISTS option_data (
            record_id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            strike_id INT,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume NUMERIC,
            UNIQUE (timestamp, strike_id),  -- Unique constraint to prevent duplicate timestamps per strike
            FOREIGN KEY (strike_id) REFERENCES strikes (strike_id)
        );
        """

        self.cursor.execute(create_strikes_table)
        self.cursor.execute(create_option_data_table)
        self.connection.commit()
        self.logger.info("Tables created or already exist.")

    def insert_option_data_from_dataframe(self, option_dataframe, strike_name):
        self.connect()

        insert_strike_query = """
        INSERT INTO strikes (strike_name)
        VALUES (%s)
        RETURNING strike_id;
        """
        self.cursor.execute(insert_strike_query, (strike_name,))
        strike_id = self.cursor.fetchone()[0]

        if strike_id is None:
            self.logger.info("Invalid stock_symbol or strike_name.")
            self.disconnect()
            return

        option_data = []
        for _, row in option_dataframe.iterrows():
            timestamp = row["Datetime"]
            open_price = row["Open"]
            high_price = row["High"]
            low_price = row["Low"]
            close_price = row["Close"]
            volume = row["Volume"]

            option_data.append(
                (
                    timestamp,
                    strike_id,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                )
            )

        insert_query = """
        INSERT INTO option_data (timestamp, strike_id, open, high, low, close, volume)
        VALUES %s;
        """
        execute_values(
            self.cursor, insert_query, option_data, template=None, page_size=1000
        )
        self.connection.commit()
        self.logger.info("Inserted %d records.", len(option_data))
