-- TimescaleDB initialization script for TradingAgents
-- This script sets up the main database and test database with required extensions

-- First, create extensions in the default postgres database
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create test database (main database 'tradingagents' is created by POSTGRES_DB env var)
CREATE DATABASE tradingagents_test;

-- Setup extensions in main database
\c tradingagents

-- Install extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify extensions are installed
SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vector', 'vectorscale', 'uuid-ossp');

-- Setup extensions in test database
\c tradingagents_test

-- Same extensions in test database
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify extensions are installed in test database
SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vector', 'vectorscale', 'uuid-ossp');

-- Output confirmation message
\c tradingagents
SELECT 'TradingAgents TimescaleDB setup complete with vectorscale, TimescaleDB, and test database' AS status;
