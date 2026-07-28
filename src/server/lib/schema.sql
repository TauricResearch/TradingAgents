-- TradingAgents Portfolio Database Schema
-- See: playbooks/sqlite-playbook.md for connection protocol
-- All connections MUST use DatabaseFactory (enforces WAL, pragmas)
--
-- Screening schema additions (screening_rules, watchlist_enrichment,
-- watchlist_news_sentiment, watchlist_screenings) authorized via
-- brief-epic-w WATCH-001: screen engine, CLI, data layer — #17 merged

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
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker               TEXT NOT NULL,
    platform             TEXT DEFAULT 'unknown',
    exchange             TEXT DEFAULT 'US',
    thesis               TEXT,
    priority             TEXT DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
    stage                TEXT DEFAULT 'researching' CHECK(stage IN ('researching', 'analyzed', 'candidate', 'approved', 'acquired')),
    added_date           TEXT NOT NULL,
    last_signal          TEXT,
    fair_value           REAL,              -- target buy price in GBP
    max_position_gbp     REAL,              -- max position size in GBP
    research_doc         TEXT,              -- links to docs/research-registry.md id (e.g. hormuz-2026-05-14)
    last_research_update TEXT,              -- YYYY-MM-DD of last research refresh
    created_at           TEXT DEFAULT (datetime('now')),
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

-- Screening rules for watchlist curation
CREATE TABLE IF NOT EXISTS screening_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    enabled     INTEGER DEFAULT 1,
    conditions  TEXT NOT NULL,  -- JSON array of ScreenCondition objects
    priority    INTEGER DEFAULT 0,  -- higher = evaluated first
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_screening_rules_enabled ON screening_rules(enabled);

-- Fundamental enrichment data per ticker (one row per fetch)
CREATE TABLE IF NOT EXISTS watchlist_enrichment (
    ticker           TEXT NOT NULL,
    fetch_date       TEXT NOT NULL,  -- YYYY-MM-DD
    pe_forward       REAL,
    eps_growth_1y    REAL,
    operating_margin REAL,
    beta_1y          REAL,
    price_to_sales   REAL,
    sector           TEXT,
    region           TEXT,
    source           TEXT DEFAULT 'yahoo_finance',
    -- Pattern features (STL decomposition, TIME benchmark paper)
    trend_strength       REAL,
    trend_linearity      REAL,
    seasonality_strength REAL,
    seasonality_stability REAL,
    residual_acf1        REAL,
    spectral_entropy     REAL,
    is_stationary        INTEGER,
    created_at       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, fetch_date)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_ticker ON watchlist_enrichment(ticker);
CREATE INDEX IF NOT EXISTS idx_enrichment_fetch ON watchlist_enrichment(fetch_date);

-- News sentiment headlines (one row per headline, FK to enrichment)
CREATE TABLE IF NOT EXISTS watchlist_news_sentiment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    published_date  TEXT NOT NULL,  -- YYYY-MM-DD
    headline_text   TEXT NOT NULL,
    summary         TEXT,
    sentiment_score REAL,           -- -1 (bearish) to 1 (bullish)
    source          TEXT,
    enrichment_id   TEXT,           -- "ticker:fetch_date" FK to watchlist_enrichment
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(enrichment_id) REFERENCES watchlist_enrichment(ticker)
);

CREATE INDEX IF NOT EXISTS idx_sentiment_ticker ON watchlist_news_sentiment(ticker);
CREATE INDEX IF NOT EXISTS idx_sentiment_date ON watchlist_news_sentiment(published_date);
CREATE INDEX IF NOT EXISTS idx_sentiment_enrichment ON watchlist_news_sentiment(enrichment_id);

-- Screening run history (persisted via R05.3)
CREATE TABLE IF NOT EXISTS watchlist_screenings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT NOT NULL,       -- YYYY-MM-DD
    tickers_matched TEXT NOT NULL,   -- JSON array
    rule_count  INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_screenings_date ON watchlist_screenings(run_date);

-- Markov Regime Detection (brief: 2026-05-20-brief-markov-regime.md)
-- Stores daily state classifications and transition matrices per ticker

CREATE TABLE IF NOT EXISTS regime_states (
    ticker           TEXT NOT NULL,
    date             TEXT NOT NULL,  -- YYYY-MM-DD
    state            TEXT NOT NULL CHECK(state IN ('bull', 'bear', 'sideways')),
    cumulative_return REAL NOT NULL,  -- 20-bar return as decimal
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_regime_states_ticker ON regime_states(ticker);
CREATE INDEX IF NOT EXISTS idx_regime_states_date ON regime_states(date);

CREATE TABLE IF NOT EXISTS regime_matrices (
    ticker           TEXT NOT NULL,
    as_of_date       TEXT NOT NULL,  -- YYYY-MM-DD — computed using data up to this date
    bull_to_bull     REAL NOT NULL,
    bull_to_sideways REAL NOT NULL,
    bull_to_bear     REAL NOT NULL,
    sideways_to_bull REAL NOT NULL,
    sideways_to_sideways REAL NOT NULL,
    sideways_to_bear REAL NOT NULL,
    bear_to_bull     REAL NOT NULL,
    bear_to_sideways REAL NOT NULL,
    bear_to_bear     REAL NOT NULL,
    PRIMARY KEY (ticker, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_regime_matrices_ticker ON regime_matrices(ticker);
CREATE INDEX IF NOT EXISTS idx_regime_matrices_date ON regime_matrices(as_of_date);

-- Walk-forward backtest results (MARKOV-002-S02)
-- One row per backtest run; persisted when `trading regime <t> --backtest --store`
CREATE TABLE IF NOT EXISTS regime_backtests (
    ticker           TEXT NOT NULL,
    run_date         TEXT NOT NULL DEFAULT (datetime('now')),
    lookback_window  INTEGER NOT NULL,
    sharpe           REAL NOT NULL,
    max_drawdown     REAL NOT NULL,
    annual_return    REAL NOT NULL,
    buy_and_hold     REAL NOT NULL,
    trade_count      INTEGER NOT NULL,
    win_rate         REAL NOT NULL,
    bull_pct         REAL NOT NULL,
    sideways_pct     REAL NOT NULL,
    bear_pct         REAL NOT NULL,
    total_days       INTEGER NOT NULL,
    PRIMARY KEY (ticker, run_date)
);

CREATE INDEX IF NOT EXISTS idx_regime_backtests_ticker ON regime_backtests(ticker);

-- HMM fitted models (MARKOV-002-S03)
-- One row per HMM fit; persisted when `trading regime <t> --hmm --store`
CREATE TABLE IF NOT EXISTS regime_hmm_models (
    ticker               TEXT NOT NULL,
    fit_date             TEXT NOT NULL DEFAULT (datetime('now')),
    n_states             INTEGER NOT NULL DEFAULT 3,
    log_likelihood       REAL NOT NULL,
    converged            INTEGER NOT NULL DEFAULT 0,
    bull_mean            REAL NOT NULL,
    bull_vol             REAL NOT NULL,
    sideways_mean        REAL NOT NULL,
    sideways_vol         REAL NOT NULL,
    bear_mean            REAL NOT NULL,
    bear_vol             REAL NOT NULL,
    transition_matrix_json TEXT NOT NULL,  -- JSON array of arrays (3×3)
    PRIMARY KEY (ticker, fit_date)
);

CREATE INDEX IF NOT EXISTS idx_regime_hmm_models_ticker ON regime_hmm_models(ticker);

-- Technical indicator readings per ticker per date (SCAN-001)
-- Wide format: one row per ticker-date, all indicator values as columns
-- Produced by computeSnapshot() from src/server/lib/indicators.ts
CREATE TABLE IF NOT EXISTS indicator_readings (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,          -- YYYY-MM-DD
    price          REAL NOT NULL,
    rsi_14         REAL,
    bb_lower       REAL,
    bb_middle      REAL,
    bb_upper       REAL,
    ma_20          REAL,
    ma_150         REAL,
    adx_14         REAL,
    macd_line      REAL,
    macd_signal    REAL,
    macd_histogram REAL,
    volume         INTEGER,
    volume_20avg   REAL,
    created_at     TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_indicator_readings_ticker ON indicator_readings(ticker);

-- Scan history per ticker (SCAN-001)
-- Records result of each scan run per ticker
CREATE TABLE IF NOT EXISTS scan_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    date          TEXT NOT NULL,          -- YYYY-MM-DD
    gates_passed  INTEGER NOT NULL,
    gates_total   INTEGER NOT NULL,
    signal        TEXT NOT NULL CHECK(signal IN ('buy','no_buy','sell')),
    exit_trigger  TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scan_history_date ON scan_history(date);
CREATE INDEX IF NOT EXISTS idx_scan_history_ticker ON scan_history(ticker);
