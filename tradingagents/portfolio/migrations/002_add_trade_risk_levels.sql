-- =============================================================================
-- Portfolio Manager Agent — Migration 002
-- Migration: 002_add_trade_risk_levels.sql
-- Description: Adds stop_loss and take_profit columns to the trades table so
--              that the PM agent can record risk-management price levels for
--              every BUY trade.
-- Safe to re-run: uses ADD COLUMN IF NOT EXISTS.
-- =============================================================================

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS stop_loss   NUMERIC(18,4) CHECK (stop_loss IS NULL OR stop_loss > 0),
    ADD COLUMN IF NOT EXISTS take_profit NUMERIC(18,4) CHECK (take_profit IS NULL OR take_profit > 0);

COMMENT ON COLUMN trades.stop_loss IS
    'Price level at which the position should be exited to limit downside loss.';
COMMENT ON COLUMN trades.take_profit IS
    'Price target at which the position should be sold to realise the expected profit.';
