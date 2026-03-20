-- =============================================================================
-- Portfolio Manager Agent — Initial Schema
-- Migration: 001_initial_schema.sql
-- Description: Creates all tables, indexes, and triggers for the portfolio
--              management data layer.
-- Safe to re-run: all statements use IF NOT EXISTS / CREATE OR REPLACE.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Table: portfolios
-- Purpose: One row per managed portfolio. Tracks cash balance, initial capital,
--          and a pointer to the filesystem report directory.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT          NOT NULL,
    cash           NUMERIC(18,4) NOT NULL CHECK (cash >= 0),
    initial_cash   NUMERIC(18,4) NOT NULL CHECK (initial_cash > 0),
    currency       CHAR(3)       NOT NULL DEFAULT 'USD',
    report_path    TEXT,                               -- relative FS path to daily report dir
    metadata       JSONB         NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE portfolios IS
    'One row per managed portfolio. Tracks cash balance and links to filesystem reports.';
COMMENT ON COLUMN portfolios.report_path IS
    'Relative path to the daily portfolio report directory, e.g. reports/daily/2026-03-20/portfolio';
COMMENT ON COLUMN portfolios.metadata IS
    'Free-form JSONB for agent notes, tags, or strategy parameters.';


-- ---------------------------------------------------------------------------
-- Table: holdings
-- Purpose: Current open positions. One row per (portfolio, ticker). Deleted
--          when shares reach zero — zero-share rows are never stored.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS holdings (
    holding_id    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id  UUID          NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    ticker        TEXT          NOT NULL,
    shares        NUMERIC(18,6) NOT NULL CHECK (shares > 0),
    avg_cost      NUMERIC(18,4) NOT NULL CHECK (avg_cost >= 0),
    sector        TEXT,
    industry      TEXT,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT holdings_portfolio_ticker_unique UNIQUE (portfolio_id, ticker)
);

COMMENT ON TABLE holdings IS
    'Open positions. Upserted on BUY (avg-cost update), deleted when fully sold.';
COMMENT ON COLUMN holdings.avg_cost IS
    'Weighted-average cost basis per share in portfolio currency.';


-- ---------------------------------------------------------------------------
-- Table: trades
-- Purpose: Immutable append-only log of every mock trade. Never modified.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trades (
    trade_id      UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id  UUID          NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    ticker        TEXT          NOT NULL,
    action        TEXT          NOT NULL,
    shares        NUMERIC(18,6) NOT NULL CHECK (shares > 0),
    price         NUMERIC(18,4) NOT NULL CHECK (price > 0),
    total_value   NUMERIC(18,4) NOT NULL CHECK (total_value > 0),
    trade_date    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    rationale     TEXT,                               -- PM agent rationale for this trade
    signal_source TEXT,                               -- 'scanner' | 'holding_review' | 'pm_agent'
    metadata      JSONB         NOT NULL DEFAULT '{}',

    CONSTRAINT trades_action_values CHECK (action IN ('BUY', 'SELL'))
);

COMMENT ON TABLE trades IS
    'Immutable trade log. Records every mock BUY/SELL with PM rationale.';
COMMENT ON COLUMN trades.rationale IS
    'Natural-language reason provided by the Portfolio Manager Agent.';
COMMENT ON COLUMN trades.signal_source IS
    'Which sub-system generated the trade signal: scanner, holding_review, or pm_agent.';


-- ---------------------------------------------------------------------------
-- Table: snapshots
-- Purpose: Immutable point-in-time portfolio state. Taken after each trade
--          execution session for performance tracking and time-series analysis.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id        UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id       UUID          NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    snapshot_date      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    total_value        NUMERIC(18,4) NOT NULL,
    cash               NUMERIC(18,4) NOT NULL,
    equity_value       NUMERIC(18,4) NOT NULL,
    num_positions      INTEGER       NOT NULL CHECK (num_positions >= 0),
    holdings_snapshot  JSONB         NOT NULL DEFAULT '[]',  -- serialised List[Holding.to_dict()]
    metadata           JSONB         NOT NULL DEFAULT '{}'
);

COMMENT ON TABLE snapshots IS
    'Immutable portfolio snapshots for performance tracking (NAV series).';
COMMENT ON COLUMN snapshots.holdings_snapshot IS
    'JSONB array of Holding.to_dict() objects at snapshot time.';


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- portfolios: lookup by name (uniqueness enforced at application level)
CREATE INDEX IF NOT EXISTS idx_portfolios_name
    ON portfolios (name);

-- holdings: list all holdings for a portfolio (most frequent query)
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_id
    ON holdings (portfolio_id);

-- holdings: fast (portfolio, ticker) point lookup for upserts
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_ticker
    ON holdings (portfolio_id, ticker);

-- trades: list recent trades for a portfolio, newest first
CREATE INDEX IF NOT EXISTS idx_trades_portfolio_id_date
    ON trades (portfolio_id, trade_date DESC);

-- trades: filter by ticker within a portfolio
CREATE INDEX IF NOT EXISTS idx_trades_portfolio_ticker
    ON trades (portfolio_id, ticker);

-- snapshots: get latest snapshot for a portfolio
CREATE INDEX IF NOT EXISTS idx_snapshots_portfolio_id_date
    ON snapshots (portfolio_id, snapshot_date DESC);


-- ---------------------------------------------------------------------------
-- updated_at trigger
-- Purpose: Automatically sets updated_at = NOW() on every UPDATE for mutable
--          tables (portfolios, holdings). Trades and snapshots are immutable.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to portfolios
CREATE OR REPLACE TRIGGER trg_portfolios_updated_at
    BEFORE UPDATE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Apply to holdings
CREATE OR REPLACE TRIGGER trg_holdings_updated_at
    BEFORE UPDATE ON holdings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
