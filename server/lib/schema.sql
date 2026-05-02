-- TradingAgents Portfolio Database Schema
-- See: playbooks/sqlite-playbook.md for connection protocol
-- All connections MUST use DatabaseFactory (enforces WAL, pragmas)

-- What you currently own
CREATE TABLE IF NOT EXISTS positions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    exchange   TEXT DEFAULT 'US',
    quantity   INTEGER NOT NULL,
    avg_cost   REAL NOT NULL,
    entry_date TEXT NOT NULL,
    thesis     TEXT,
    status     TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    notes      TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
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
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Signal history: what the AI said, when
CREATE TABLE IF NOT EXISTS signals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,
    signal     TEXT NOT NULL CHECK(signal IN ('Buy', 'Overweight', 'Hold', 'Underweight', 'Sell')),
    reasoning  TEXT,
    confidence TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Watchlist: prospects being tracked but not owned
CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    exchange    TEXT DEFAULT 'US',
    thesis      TEXT,
    priority    TEXT DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
    added_date  TEXT NOT NULL,
    last_signal TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Full analysis output (stored as JSON, rendered on demand)
CREATE TABLE IF NOT EXISTS analyses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,
    config     TEXT,
    raw_state  TEXT,
    decision   TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_analyses_ticker_date ON analyses(ticker, date);
CREATE INDEX IF NOT EXISTS idx_trades_position ON trades(position_id);
