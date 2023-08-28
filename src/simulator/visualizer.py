import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import psycopg2
from mplfinance.original_flavor import candlestick_ohlc


def plot_candlestick(strike_id, start_time, end_time, interval):
    # Connect to your PostgreSQL database
    conn = psycopg2.connect(
        dbname="option_db",
        user="admin",
        password="admin",
        host="localhost",
        port="5432",
    )

    # Define the SQL query to retrieve the candlestick data
    query = f"""
        WITH candlestick_data AS (
    SELECT
        time_bucket('{interval}', timestamp) AS candle_time,
        MIN(open) AS open,
        MAX(high) AS high,
        MIN(low) AS low,
        SUM(volume) AS volume,
        LAST(close, timestamp) AS close
    FROM option_data
    WHERE strike_id = {strike_id}
        AND timestamp >= '{start_time}'
        AND timestamp <= '{end_time}'
    GROUP BY candle_time
        )
    SELECT
        candle_time,
        open,
        high,
        low,
        close,
        volume
    FROM candlestick_data
    ORDER BY candle_time
    """

    # Fetch the data using pandas and read it into a DataFrame
    data = pd.read_sql(query, conn, parse_dates=["timestamp"])

    print(data)
    # Convert candle_time to Matplotlib date format
    data["candle_time"] = data["candle_time"].apply(mdates.date2num)

    # Plot the candlestick chart

    _, axis = plt.subplots()
    ohlc_data = data[["candle_time", "open", "high", "low", "close", "volume"]].values

    # Plot the candlestick chart
    candlestick_ohlc(
        axis,
        ohlc_data,
        width=0.05,
        colorup="g",
        colordown="r",
    )

    # Format x-axis dates
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))

    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45)

    # Set labels and title
    axis.set_xlabel("Date")
    axis.set_ylabel("Price")
    plt.title("Candlestick Chart")

    # Display the chart
    plt.tight_layout()
    plt.show()

    # Close the database connection
    conn.close()


# Example usage
plot_candlestick(
    strike_id=19,
    start_time="2023-08-18 09:00:00",
    end_time="2023-08-24 15:30:00",
    interval="1 hour",
)  # 5 minutes interval
