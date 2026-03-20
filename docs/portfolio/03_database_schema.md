# Database & Filesystem Schema

<!-- Last verified: 2026-03-20 -->

## Supabase (PostgreSQL) Schema

All tables are created in the `public` schema (Supabase default).

---

### `portfolios`

Stores one row per managed portfolio.

```sql
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT         NOT NULL,
    cash           NUMERIC(18,4) NOT NULL CHECK (cash >= 0),
    initial_cash   NUMERIC(18,4) NOT NULL CHECK (initial_cash > 0),
    currency       CHAR(3)      NOT NULL DEFAULT 'USD',
    report_path    TEXT,
    metadata       JSONB        NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

**Constraints:**
- `cash >= 0` — portfolio can be fully invested but never negative
- `initial_cash > 0` — must start with positive capital
- `currency` is 3-char ISO 4217 code

---

### `holdings`

Stores one row per open position per portfolio. Row is deleted when shares reach 0.

```sql
CREATE TABLE IF NOT EXISTS holdings (
    holding_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id   UUID         NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    ticker         TEXT         NOT NULL,
    shares         NUMERIC(18,6) NOT NULL CHECK (shares > 0),
    avg_cost       NUMERIC(18,4) NOT NULL CHECK (avg_cost >= 0),
    sector         TEXT,
    industry       TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT holdings_portfolio_ticker_unique UNIQUE (portfolio_id, ticker)
);
```

**Constraints:**
- `shares > 0` — zero-share positions are deleted, not stored
- `avg_cost >= 0` — cost basis is non-negative
- `UNIQUE (portfolio_id, ticker)` — one row per ticker per portfolio (upsert pattern)

---

### `trades`

Immutable append-only log of every mock trade execution.

```sql
CREATE TABLE IF NOT EXISTS trades (
    trade_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id   UUID         NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    ticker         TEXT         NOT NULL,
    action         TEXT         NOT NULL CHECK (action IN ('BUY', 'SELL')),
    shares         NUMERIC(18,6) NOT NULL CHECK (shares > 0),
    price          NUMERIC(18,4) NOT NULL CHECK (price > 0),
    total_value    NUMERIC(18,4) NOT NULL CHECK (total_value > 0),
    trade_date     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    rationale      TEXT,
    signal_source  TEXT,
    metadata       JSONB        NOT NULL DEFAULT '{}',

    CONSTRAINT trades_action_values CHECK (action IN ('BUY', 'SELL'))
);
```

**Constraints:**
- `action IN ('BUY', 'SELL')` — only two valid actions
- `shares > 0`, `price > 0` — all quantities positive
- No `updated_at` — trades are immutable

---

### `snapshots`

Point-in-time portfolio state snapshots taken after each trade session.

```sql
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id       UUID         NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    snapshot_date      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    total_value        NUMERIC(18,4) NOT NULL,
    cash               NUMERIC(18,4) NOT NULL,
    equity_value       NUMERIC(18,4) NOT NULL,
    num_positions      INTEGER      NOT NULL CHECK (num_positions >= 0),
    holdings_snapshot  JSONB        NOT NULL DEFAULT '[]',
    metadata           JSONB        NOT NULL DEFAULT '{}'
);
```

**Constraints:**
- `num_positions >= 0` — can have 0 positions (fully in cash)
- `holdings_snapshot` is a JSONB array of serialised `Holding.to_dict()` objects
- No `updated_at` — snapshots are immutable

---

## Indexes

```sql
-- portfolios: fast lookup by name
CREATE INDEX IF NOT EXISTS idx_portfolios_name
    ON portfolios (name);

-- holdings: list all holdings for a portfolio (most common query)
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_id
    ON holdings (portfolio_id);

-- holdings: fast ticker lookup within a portfolio
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
```

---

## `updated_at` Trigger

Automatically updates `updated_at` on every row modification for `portfolios`
and `holdings` (trades and snapshots are immutable).

```sql
-- Trigger function (shared across tables)
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
```

---

## Example Queries

### Get active portfolio with cash balance

```sql
SELECT portfolio_id, name, cash, initial_cash, currency
FROM portfolios
WHERE portfolio_id = $1;
```

### Get all holdings with sector summary

```sql
SELECT
    ticker,
    shares,
    avg_cost,
    shares * avg_cost AS cost_basis,
    sector
FROM holdings
WHERE portfolio_id = $1
ORDER BY shares * avg_cost DESC;
```

### Sector concentration (cost-basis weighted)

```sql
SELECT
    COALESCE(sector, 'Unknown') AS sector,
    SUM(shares * avg_cost) AS sector_cost_basis
FROM holdings
WHERE portfolio_id = $1
GROUP BY sector
ORDER BY sector_cost_basis DESC;
```

### Recent 20 trades for a portfolio

```sql
SELECT ticker, action, shares, price, total_value, trade_date, rationale
FROM trades
WHERE portfolio_id = $1
ORDER BY trade_date DESC
LIMIT 20;
```

### Latest portfolio snapshot

```sql
SELECT *
FROM snapshots
WHERE portfolio_id = $1
ORDER BY snapshot_date DESC
LIMIT 1;
```

### Portfolio performance over time (snapshot series)

```sql
SELECT snapshot_date, total_value, cash, equity_value, num_positions
FROM snapshots
WHERE portfolio_id = $1
ORDER BY snapshot_date ASC;
```

---

## Filesystem Directory Structure

Reports and documents are stored under the project's `reports/` directory using
the existing convention from `tradingagents/report_paths.py`.

```
reports/
└── daily/
    └── {YYYY-MM-DD}/
        ├── market/
        │   ├── geopolitical_report.md
        │   ├── market_movers_report.md
        │   ├── sector_report.md
        │   ├── industry_deep_dive_report.md
        │   ├── macro_synthesis_report.md
        │   └── macro_scan_summary.json     ← ReportStore.save_scan / load_scan
        │
        ├── {TICKER}/                       ← one dir per analysed ticker
        │   ├── 1_analysts/
        │   ├── 2_research/
        │   ├── 3_trader/
        │   ├── 4_risk/
        │   ├── complete_report.md          ← ReportStore.save_analysis / load_analysis
        │   └── eval/
        │       └── full_states_log.json
        │
        ├── daily_digest.md
        │
        └── portfolio/                      ← NEW: portfolio manager artifacts
            ├── {TICKER}_holding_review.json    ← ReportStore.save_holding_review
            ├── {portfolio_id}_risk_metrics.json
            ├── {portfolio_id}_pm_decision.json
            └── {portfolio_id}_pm_decision.md   (human-readable)
```

---

## Supabase ↔ Filesystem Link

The `portfolios.report_path` column stores the **absolute or relative path** to the
daily portfolio subdirectory:

```
report_path = "reports/daily/2026-03-20/portfolio"
```

This allows the Repository layer to load the PM decision, risk metrics, and holding
reviews by constructing:

```python
Path(portfolio.report_path) / f"{portfolio_id}_pm_decision.json"
```

The path is set by the Repository after the first write on each run day.

---

## Schema Version Notes

- Migration file: `tradingagents/portfolio/migrations/001_initial_schema.sql`
- All `CREATE TABLE` and `CREATE INDEX` use `IF NOT EXISTS` — safe to re-run
- `CREATE OR REPLACE TRIGGER` / `CREATE OR REPLACE FUNCTION` — idempotent
- Supabase project dashboard: run via SQL Editor or the Supabase CLI
  (`supabase db push`)
