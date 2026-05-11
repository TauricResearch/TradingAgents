-- TradingAgents Portfolio Database Schema
-- See: playbooks/sqlite-playbook.md for connection protocol
-- All connections MUST use DatabaseFactory (enforces WAL, pragmas)

-- Accounts (delivery mechanisms — tax wrappers and platforms)
-- Balance is tracked via hledger for most accounts; manual for legacy/savings.
CREATE TABLE IF NOT EXISTS accounts (
    id          TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK(account_type IN ('isa','shares','sipp','spreadbet','savings','cash')),
    name        TEXT,
    balance     REAL DEFAULT 0,
    currency    TEXT DEFAULT 'GBP',
    notes       TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- What you currently own (linked to accounts)
CREATE TABLE IF NOT EXISTS positions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    exchange   TEXT DEFAULT 'US',
    platform   TEXT DEFAULT 'unknown',
    account_id TEXT REFERENCES accounts(id),
    quantity   INTEGER NOT NULL,
    avg_cost   REAL NOT NULL,
    entry_date TEXT NOT NULL,
    thesis     TEXT,
    status     TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    notes      TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Spread bet positions (separate P&L bucket — not mixed with delivery positions)
CREATE TABLE IF NOT EXISTS spreadbet_positions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    ticker         TEXT NOT NULL,
    direction      TEXT NOT NULL CHECK(direction IN ('long','short')),
    stake_per_point REAL NOT NULL,
    entry_price    REAL NOT NULL,
    entry_date     TEXT NOT NULL,
    stop_price     REAL,
    target_price   REAL,
    current_price  REAL,
    pnl_gbp        REAL,
    notes          TEXT,
    status         TEXT DEFAULT 'open' CHECK(status IN ('open','closed')),
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now'))
);

-- Account balance history (for manual/savings accounts tracked outside hledger)
CREATE TABLE IF NOT EXISTS account_balances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL REFERENCES accounts(id),
    balance     REAL NOT NULL,
    date        TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Trade log (buy/sell actions)
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER REFERENCES positions(id),
    ticker      TEXT NOT NULL,
    action      TEXT NOT NULL CHECK(action IN ('buy', 'sell')),
    quantity    INTEGER NOT NULL,
    price       REAL NOT NULL,
    date        TEXT NOT NULL,
    reason      TEXT,
    fees        REAL DEFAULT 0,
    analysis_id TEXT,                             -- links to analysis UUID
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Signal history: what the AI said, when
CREATE TABLE IF NOT EXISTS signals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    platform   TEXT DEFAULT 'unknown',
    date       TEXT NOT NULL,
    signal     TEXT NOT NULL CHECK(signal IN ('buy', 'overweight', 'hold', 'underweight', 'sell')),
    reasoning  TEXT,
    confidence TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Watchlist: prospects being tracked but not owned
CREATE TABLE IF NOT EXISTS watchlist (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    platform         TEXT DEFAULT 'unknown',
    exchange         TEXT DEFAULT 'US',
    thesis           TEXT,
    priority         TEXT DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
    stage            TEXT DEFAULT 'researching' CHECK(stage IN ('researching', 'analyzed', 'candidate', 'approved', 'acquired')),
    added_date       TEXT NOT NULL,
    last_signal      TEXT,
    fair_value       REAL,              -- target buy price in GBP
    max_position_gbp REAL,              -- max position size in GBP
    created_at       TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, exchange)
);

-- Full analysis output (stored as JSON, rendered on demand)
CREATE TABLE IF NOT EXISTS analyses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    platform   TEXT DEFAULT 'unknown',
    date       TEXT NOT NULL,
    config     TEXT,
    raw_state  TEXT,
    decision   TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Daily OHLCV price records per ticker
-- Source: Yahoo Finance API via scripts/get_price.ts
-- Backfill on position open; catch-up via scripts/sync-prices.ts
CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT    NOT NULL,
    date      TEXT    NOT NULL,  -- YYYY-MM-DD
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL    NOT NULL,
    volume    INTEGER,
    currency  TEXT    DEFAULT 'GBP',
    gbp_rate  REAL,              -- GBP per unit of native currency (e.g. 0.79 for USD)
    PRIMARY KEY (ticker, date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_signals_platform ON signals(platform);
CREATE INDEX IF NOT EXISTS idx_positions_platform ON positions(platform);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_analyses_ticker_date ON analyses(ticker, date);
CREATE INDEX IF NOT EXISTS idx_trades_position ON trades(position_id);
CREATE INDEX IF NOT EXISTS idx_sb_account ON spreadbet_positions(account_id);
CREATE INDEX IF NOT EXISTS idx_sb_status ON spreadbet_positions(status);
CREATE INDEX IF NOT EXISTS idx_ab_account ON account_balances(account_id);

-- Alert rules (user-defined custom alerts)
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    ticker          TEXT,                              -- NULL = cross-ticker / portfolio-level
    condition       TEXT NOT NULL,                     -- JSON: {type, threshold, direction?}
    platform        TEXT DEFAULT 'all',                -- 'all' or specific platform
    severity        TEXT DEFAULT 'warning'
                     CHECK(severity IN ('critical','warning','info')),
    message         TEXT,                              -- custom message template
    channel         TEXT DEFAULT 'telegram'
                     CHECK(channel IN ('telegram','email','webhook','none')),
    enabled         INTEGER DEFAULT 1,
    last_checked    TEXT,
    last_triggered  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(name)
);

CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_enabled ON alerts(enabled);
