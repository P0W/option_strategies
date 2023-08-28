-- Created Database option_db
CREATE DATABASE IF NOT EXISTS option_db;

-- Created Table strikes
CREATE TABLE IF NOT EXISTS strikes (
                        strike_id SERIAL PRIMARY KEY,
                        strike_name TEXT UNIQUE
                    );
-- Created Table option_data     
CREATE TABLE IF NOT EXISTS option_data (
            timestamp TIMESTAMPTZ NOT NULL,
            strike_id INT,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume bigint,
            PRIMARY KEY (strike_id, timestamp),
            FOREIGN KEY (strike_id) REFERENCES strikes (strike_id)
        );

-- Created hypertable for option_data
SELECT create_hypertable('option_data', 'timestamp', 
    chunk_time_interval => interval '1 minute',
    if_not_exists => TRUE);

-- 15 minute view
CREATE OR REPLACE VIEW range_view AS
SELECT time_bucket('15 minutes', timestamp) AS bucket,
       strike_id,
       first(open, timestamp) AS open,
       max(high) AS high,
       min(low) AS low,
       last(close, timestamp) AS close,
       sum(volume) AS volume
FROM option_data
GROUP BY bucket, strike_id
ORDER BY strike_id, bucket;

-- Created Table backfilled_option_data , backfill 5 minutes candle on 2023-08-22 09:15 to 2023-08-25 15:30
CREATE OR REPLACE VIEW backfilled_option_data AS
WITH date_range AS (
    SELECT generate_series(
               date_trunc('day', '2023-08-22'::timestamp) + '09:15'::time,
               date_trunc('day', '2023-08-25'::timestamp) + '15:30'::time,
               interval '5 minute'
           ) AS minute
)
SELECT
    dr.minute AS timestamp,
    s.strike_id,
    COALESCE(od.open, previous_od.close) AS open,
    COALESCE(od.high, previous_od.close) AS high,
    COALESCE(od.low, previous_od.close) AS low,
    COALESCE(od.close, previous_od.close) AS close,
    COALESCE(od.volume, 0) AS volume
FROM
    date_range dr
CROSS JOIN
    strikes s
LEFT JOIN LATERAL (
    SELECT
        timestamp,
        open,
        high,
        low,
        close,
        volume
    FROM
        option_data
    WHERE
        strike_id = s.strike_id
        AND timestamp = dr.minute
) od ON true
LEFT JOIN LATERAL (
    SELECT
        timestamp,
        close
    FROM
        option_data
    WHERE
        strike_id = s.strike_id
        AND timestamp < dr.minute
    ORDER BY
        timestamp DESC
    LIMIT 1
) previous_od ON true
ORDER BY
    dr.minute, s.strike_id;

-- Sample query
SELECT timestamp, close
FROM backfilled_option_data
WHERE (
    EXTRACT(HOUR FROM timestamp) = 9 AND EXTRACT(MINUTE FROM timestamp) >= 15
    OR EXTRACT(HOUR FROM timestamp) > 9
)
AND (
    EXTRACT(HOUR FROM timestamp) = 15 AND EXTRACT(MINUTE FROM timestamp) <= 30
    OR EXTRACT(HOUR FROM timestamp) < 15
)
AND strike_id = 1
ORDER BY timestamp, strike_id;

