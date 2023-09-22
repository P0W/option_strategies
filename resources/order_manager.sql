-- create database order_manager;
-- \c order_manager

-- Define ENUM types
CREATE TYPE order_status AS ENUM (
    'Placed', 'Executed', 'Cancelled', 'Rejected', 'Partially Executed'
);

CREATE TYPE exchange_type AS ENUM (
    'NSE', 'BSE'
);

CREATE TYPE exchange_segment_type AS ENUM (
   'Derivative', 'Equity', 'Currency'
);

-- Table for Order data
CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    remote_order_id TEXT,
    exchange_order_id TEXT,
    script_code INTEGER,
    quantity INTEGER,
    buy_sell CHAR(1) CHECK (buy_sell IN ('B', 'S')),
    avg_price NUMERIC,
    status order_status,
    order_type TEXT CHECK (order_type IN ('SL', 'R')),
    comment TEXT
);

-- Table for Scrip data
CREATE TABLE IF NOT EXISTS scrips (
    script_code INTEGER PRIMARY KEY,
    script_name TEXT,
    exchange exchange_type,
    exchange_segment exchange_segment_type
);

-- Table for Live Scrip data
CREATE TABLE IF NOT EXISTS live_scrips (
    live_scrip_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    open_price NUMERIC,
    high_price NUMERIC,
    low_price NUMERIC,
    close_price NUMERIC,
    quantity BIGINT,
    time TIMESTAMP,
    pnl NUMERIC,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Add foreign key constraint in orders table
ALTER TABLE orders
ADD FOREIGN KEY (script_code) REFERENCES scrips(script_code);


-- Trigger function to handle order status changes
CREATE OR REPLACE FUNCTION handle_order_status_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Create scrip entry when order status is "Placed"
    -- IF NEW.status = 'Placed' THEN
    --     INSERT INTO scrips (script_code, script_name, exchange, exchange_segment)
    --     VALUES (NEW.script_code, 'Placeholder Name', 'NSE', 'Equity');
    -- END IF;

    -- Insert into live_scrips when order status is "Executed"
    IF NEW.status = 'Executed' THEN
        INSERT INTO live_scrips (order_id, open_price, high_price, low_price, close_price, quantity, time, pnl)
        VALUES (NEW.order_id, 0, 0, 0, 0, NEW.quantity, NOW(), 0);
    END IF;

    -- Delete from live_scrips and scrips when status is 'Cancelled' or 'Rejected'
    IF NEW.status IN ('Cancelled', 'Rejected') THEN
        DELETE FROM live_scrips WHERE order_id = NEW.order_id;
        DELETE FROM scrips WHERE script_code = NEW.script_code;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger to the orders table
CREATE TRIGGER order_status_change_trigger
AFTER INSERT OR UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION handle_order_status_change();
