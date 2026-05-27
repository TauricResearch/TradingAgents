-- IIC-FORGE F1 schema. Designed upfront per ADR-F4 (revised) so F2/F3/F5
-- additions are append-only (new tables, no column reshapes).
--
-- All TIMESTAMP columns are ISO-8601 strings (TEXT) for SQLite portability.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- F1 tables — populated from day one
-- ============================================================

CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,           -- UUID4 hex
    ticker          TEXT NOT NULL,
    persona_id      TEXT,                       -- nullable for legacy / non-persona runs
    started_ts      TEXT NOT NULL,
    ended_ts        TEXT,
    status          TEXT NOT NULL,              -- "running" | "complete" | "error"
    decision        TEXT,                       -- "BUY" | "HOLD" | "SELL" | NULL
    confidence      REAL,                       -- 0.0–1.0
    trigger_id      TEXT,                       -- nullable; FK to events.event_id when F3 ships
    artifact_dir    TEXT NOT NULL               -- relative path under iic_data_dir
);
CREATE INDEX IF NOT EXISTS idx_runs_ticker_ts ON runs(ticker, started_ts);
CREATE INDEX IF NOT EXISTS idx_runs_persona ON runs(persona_id);

CREATE TABLE IF NOT EXISTS costs (
    cost_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    in_tokens       INTEGER NOT NULL DEFAULT 0,
    out_tokens      INTEGER NOT NULL DEFAULT 0,
    usd_estimate    REAL                        -- nullable; we don't always know the price
);
CREATE INDEX IF NOT EXISTS idx_costs_run ON costs(run_id);

CREATE TABLE IF NOT EXISTS briefs (
    brief_id        TEXT PRIMARY KEY,           -- UUID4 hex
    mode            TEXT NOT NULL,              -- "deep_dive" | "morning_digest" | "event_alert"
    scope           TEXT NOT NULL,              -- single ticker or JSON list
    generated_ts    TEXT NOT NULL,
    content_path    TEXT NOT NULL,              -- relative path under iic_data_dir
    run_ids         TEXT NOT NULL,              -- JSON list of run_id
    delivery_ids    TEXT,                       -- JSON list of delivery_id (F5)
    parent_brief_id TEXT REFERENCES briefs(brief_id)   -- threading for refinement (§4, §10)
);
CREATE INDEX IF NOT EXISTS idx_briefs_parent ON briefs(parent_brief_id);

CREATE TABLE IF NOT EXISTS brief_actions (
    action_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id            TEXT NOT NULL REFERENCES briefs(brief_id) ON DELETE CASCADE,
    action_type         TEXT NOT NULL,          -- "run_backtest" | "refine_brief"
    action_params       TEXT NOT NULL,          -- JSON
    state               TEXT NOT NULL,          -- "pending" | "accepted" | "declined" | "expired"
    expires_at          TEXT NOT NULL,
    responded_at        TEXT,
    result_backtest_id  INTEGER,                -- FK to backtests.backtest_id (F2)
    result_brief_id     TEXT REFERENCES briefs(brief_id)
);
CREATE INDEX IF NOT EXISTS idx_brief_actions_brief ON brief_actions(brief_id);
CREATE INDEX IF NOT EXISTS idx_brief_actions_state ON brief_actions(state, expires_at);

CREATE TABLE IF NOT EXISTS suppression (
    key             TEXT PRIMARY KEY,           -- e.g. "AAPL:macro" or "AAPL:*"
    until_ts        TEXT NOT NULL,
    reason          TEXT,
    created_by      TEXT
);

-- Hybrid memory: per-(persona, component) partitioned
CREATE TABLE IF NOT EXISTS memories (
    memory_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id      TEXT NOT NULL,              -- NEVER allow "" or "*"; isolation depends on this
    component       TEXT NOT NULL,              -- e.g. "decision_log", future: "bull", "bear", ...
    situation_md    TEXT NOT NULL,
    outcome         TEXT,
    vec_id          INTEGER,                        -- FK to vec_index.rowid; enforced in app layer (virtual tables cannot be FK targets in SQLite)
    created_ts      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_partition ON memories(persona_id, component);

-- Shared cross-persona outcome pool
CREATE TABLE IF NOT EXISTS outcome_log (
    outcome_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    decision        TEXT NOT NULL,
    outcome_md      TEXT NOT NULL,
    pnl_proxy       REAL,                       -- set by F2 reflection loop
    vec_id          INTEGER,                        -- FK to vec_index.rowid; enforced in app layer (virtual tables cannot be FK targets in SQLite)
    tags            TEXT,                       -- JSON
    created_ts      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcome_log_ticker ON outcome_log(ticker);

-- sqlite-vec virtual table (created at runtime by db.py after loading the extension)
-- The placeholder below documents the shape; the actual CREATE VIRTUAL TABLE
-- statement runs after sqlite_vec.load(conn).
-- CREATE VIRTUAL TABLE vec_index USING vec0(embedding float[384]);

-- ============================================================
-- F2 tables — defined upfront, populated when F2 ships
-- ============================================================

CREATE TABLE IF NOT EXISTS backtests (
    backtest_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_by_brief_id   TEXT REFERENCES briefs(brief_id),   -- set for brief-scoped (F5 flow)
    universe                TEXT NOT NULL,                       -- JSON list of tickers
    start_date              TEXT NOT NULL,
    end_date                TEXT NOT NULL,
    status                  TEXT NOT NULL,
    report_path             TEXT,                                -- relative path under iic_data_dir
    created_ts              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    btr_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id     INTEGER NOT NULL REFERENCES backtests(backtest_id) ON DELETE CASCADE,
    persona_id      TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    metrics         TEXT NOT NULL                                -- JSON: sharpe, total_return, win_rate, ...
);

-- ============================================================
-- F3 tables — defined upfront, populated when F3 ships
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    ingested_ts     TEXT NOT NULL,
    salience        REAL,
    raw_path        TEXT,
    deduped_of      TEXT REFERENCES events(event_id),
    status          TEXT NOT NULL                                -- "new" | "triaged" | "discarded" | "duplicate"
);

CREATE TABLE IF NOT EXISTS event_ticker (
    event_id        TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    confidence      REAL,
    PRIMARY KEY (event_id, ticker)
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker          TEXT PRIMARY KEY,
    added_ts        TEXT NOT NULL,
    last_briefed    TEXT,
    ttl_until       TEXT,
    tags            TEXT                                         -- JSON
);

-- ============================================================
-- F4 / F5 tables — defined upfront, populated later
-- ============================================================

CREATE TABLE IF NOT EXISTS queue_jobs (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type        TEXT NOT NULL,
    payload         TEXT NOT NULL,                               -- JSON
    state           TEXT NOT NULL,                               -- "queued" | "running" | "done" | "error"
    enqueued_ts     TEXT NOT NULL,
    started_ts      TEXT,
    finished_ts     TEXT
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id        TEXT NOT NULL REFERENCES briefs(brief_id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,                               -- "telegram" | "email" | "cli"
    status          TEXT NOT NULL,                               -- "sent" | "failed" | "skipped"
    sent_ts         TEXT
);

-- ============================================================
-- F3 sensing/triage append-only tables (added by IIC-FORGE-06)
-- ============================================================

CREATE TABLE IF NOT EXISTS ingest_cursor (
    source     TEXT PRIMARY KEY,           -- e.g., "polygon_news"
    cursor     TEXT NOT NULL,              -- adapter-specific opaque payload
    updated_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickers (
    ticker     TEXT PRIMARY KEY,           -- "AAPL", "BTC-USD"
    exchange   TEXT NOT NULL,              -- "NASDAQ" | "NYSE" | "ARCA" | "CRYPTO"
    name       TEXT NOT NULL,
    aliases    TEXT,                       -- JSON array: ["Apple", "Apple Computer"]
    active     INTEGER NOT NULL DEFAULT 1, -- 0 = delisted (filtered)
    updated_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickers_active ON tickers(active);

CREATE TABLE IF NOT EXISTS event_fingerprints (
    fingerprint TEXT NOT NULL,             -- external_id or sha256 hex
    kind        TEXT NOT NULL,             -- 'external_id' | 'sha256'
    event_id    TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    created_ts  TEXT NOT NULL,
    PRIMARY KEY (fingerprint, kind)
);
CREATE INDEX IF NOT EXISTS idx_event_fingerprints_event ON event_fingerprints(event_id);

CREATE TABLE IF NOT EXISTS event_embeddings (
    event_id   TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    vec_id     INTEGER NOT NULL,           -- app-layer FK to vec_index.rowid
    created_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_embeddings_vec ON event_embeddings(vec_id);

-- ============================================================
-- F4 orchestrator append-only columns (added by IIC-FORGE-07)
-- ============================================================
-- NOTE: ALTER TABLE ADD COLUMN is NOT idempotent in SQLite. The db.py
-- migration layer wraps these statements to swallow "duplicate column
-- name" errors, allowing connect() to be called repeatedly. Do NOT add
-- IF NOT EXISTS — sqlite does not support it on ALTER TABLE.

ALTER TABLE queue_jobs ADD COLUMN trigger_event_id  TEXT REFERENCES events(event_id);
ALTER TABLE queue_jobs ADD COLUMN run_ids           TEXT;
ALTER TABLE queue_jobs ADD COLUMN brief_id          TEXT REFERENCES briefs(brief_id);
ALTER TABLE queue_jobs ADD COLUMN cost_usd          REAL;
ALTER TABLE queue_jobs ADD COLUMN error             TEXT;

ALTER TABLE briefs     ADD COLUMN trigger_event_id  TEXT REFERENCES events(event_id);

ALTER TABLE runs       ADD COLUMN queue_job_id      INTEGER REFERENCES queue_jobs(job_id);

CREATE INDEX IF NOT EXISTS idx_queue_jobs_trigger_event
    ON queue_jobs(trigger_event_id);
CREATE INDEX IF NOT EXISTS idx_queue_jobs_state_enqueued
    ON queue_jobs(state, enqueued_ts);
