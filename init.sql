-- Database initialization script for Autonomous Trading System
-- Creates necessary extensions and initial setup

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable crypto functions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create schema
CREATE SCHEMA IF NOT EXISTS trading;

-- Set default search path
SET search_path TO trading, public;

-- Create custom types
CREATE TYPE order_status AS ENUM (
    'pending',
    'submitted',
    'partially_filled',
    'filled',
    'cancelled',
    'rejected',
    'failed'
);

CREATE TYPE order_side AS ENUM ('BUY', 'SELL');
CREATE TYPE order_type AS ENUM ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT', 'BRACKET');
CREATE TYPE risk_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');

-- Grant permissions to user
GRANT ALL PRIVILEGES ON SCHEMA trading TO trader;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA trading TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA trading TO trader;

-- Create indexes for better performance
-- These will be created after tables are created by SQLAlchemy
-- Just documenting the important ones here

COMMENT ON SCHEMA trading IS 'Autonomous Trading System Schema';

-- Function to update last_updated timestamps
CREATE OR REPLACE FUNCTION update_last_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate portfolio metrics
CREATE OR REPLACE FUNCTION calculate_portfolio_metrics()
RETURNS TABLE(
    total_value DECIMAL,
    total_pnl DECIMAL,
    position_count INTEGER,
    avg_position_size DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        SUM(market_value) as total_value,
        SUM(unrealized_pnl + realized_pnl) as total_pnl,
        COUNT(*) as position_count,
        AVG(market_value) as avg_position_size
    FROM positions
    WHERE shares > 0;
END;
$$ LANGUAGE plpgsql;

-- Function to get recent trades
CREATE OR REPLACE FUNCTION get_recent_trades(hours INTEGER DEFAULT 24)
RETURNS TABLE(
    ticker VARCHAR,
    action VARCHAR,
    quantity INTEGER,
    price DECIMAL,
    executed_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.ticker,
        t.action,
        t.quantity,
        t.price,
        t.executed_at
    FROM trades t
    WHERE t.executed_at >= NOW() - INTERVAL '1 hour' * hours
    ORDER BY t.executed_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Create materialized view for performance metrics (updated hourly)
-- This will be created after the tables exist

-- Set up row-level security (RLS) for multi-tenant support
-- ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Create audit log table for compliance
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL,
    user_name VARCHAR(50),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    old_data JSONB,
    new_data JSONB
);

-- Audit trigger function
CREATE OR REPLACE FUNCTION audit_trigger_function()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log(table_name, operation, user_name, new_data)
        VALUES (TG_TABLE_NAME, TG_OP, current_user, row_to_json(NEW));
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log(table_name, operation, user_name, old_data, new_data)
        VALUES (TG_TABLE_NAME, TG_OP, current_user, row_to_json(OLD), row_to_json(NEW));
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log(table_name, operation, user_name, old_data)
        VALUES (TG_TABLE_NAME, TG_OP, current_user, row_to_json(OLD));
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Performance settings
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;

-- Reload configuration
SELECT pg_reload_conf();

-- Create initial admin notification
DO $$
BEGIN
    RAISE NOTICE 'Database initialization complete for Autonomous Trading System';
    RAISE NOTICE 'TimescaleDB enabled for time-series optimization';
    RAISE NOTICE 'Audit logging configured for compliance';
END $$;