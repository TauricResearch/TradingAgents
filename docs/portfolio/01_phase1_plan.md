# Phase 1 Implementation Plan — Data Foundation

<!-- Last verified: 2026-03-20 -->

## Goal

Build the data foundation layer for the Portfolio Manager feature.

After Phase 1 you should be able to:
- Create and retrieve portfolios
- Manage holdings (add, update, remove) with correct avg-cost-basis accounting
- Record mock trades
- Take immutable portfolio snapshots
- Save and load all report types (scans, analysis, holding reviews, risk, PM decisions)
- Pass a 90 %+ test coverage gate on all new modules

---

## File Structure

```
tradingagents/portfolio/
├── __init__.py               ← public exports
├── models.py                 ← Portfolio, Holding, Trade, PortfolioSnapshot dataclasses
├── config.py                 ← PORTFOLIO_CONFIG dict + helpers
├── exceptions.py             ← domain exception hierarchy
├── supabase_client.py        ← Supabase CRUD wrapper
├── report_store.py           ← Filesystem document storage
├── repository.py             ← Unified data-access façade (Supabase + filesystem)
└── migrations/
    └── 001_initial_schema.sql

tests/portfolio/
├── __init__.py
├── conftest.py               ← shared fixtures
├── test_models.py
├── test_report_store.py
└── test_repository.py
```

---

## Task 1 — Data Models (`models.py`)

**Estimated effort:** 2–3 h

### Deliverables

Four dataclasses fully type-annotated:

- `Portfolio`
- `Holding`
- `Trade`
- `PortfolioSnapshot`

Each class must implement:
- `to_dict() -> dict` — serialise for DB / JSON
- `from_dict(data: dict) -> Self` — deserialise from DB / JSON
- `enrich(**kwargs)` — attach runtime-computed fields (prices, weights, P&L)

### Field Specifications

See `docs/portfolio/02_data_models.md` for full field tables.

### Acceptance Criteria

- All fields have explicit Python type annotations
- `to_dict()` → `from_dict()` round-trip is lossless for all fields
- `enrich()` correctly computes `current_value`, `unrealized_pnl`, `unrealized_pnl_pct`, `weight`
- 100 % line coverage in `test_models.py`

---

## Task 2 — Portfolio Config (`config.py`)

**Estimated effort:** 1 h

### Deliverables

```python
PORTFOLIO_CONFIG: dict           # all tunable parameters
get_portfolio_config() -> dict   # returns merged config (defaults + env overrides)
validate_config(cfg: dict)       # raises ValueError on invalid values
```

### Environment Variables

All are optional and default to the values shown:

| Env Var | Default | Description |
|---------|---------|-------------|
| `SUPABASE_URL` | `""` | Supabase project URL |
| `SUPABASE_KEY` | `""` | Supabase anon/service key |
| `PORTFOLIO_DATA_DIR` | `"reports"` | Root dir for filesystem reports |
| `PM_MAX_POSITIONS` | `15` | Max number of open positions |
| `PM_MAX_POSITION_PCT` | `0.15` | Max single-position weight |
| `PM_MAX_SECTOR_PCT` | `0.35` | Max sector weight |
| `PM_MIN_CASH_PCT` | `0.05` | Minimum cash reserve |
| `PM_DEFAULT_BUDGET` | `100000.0` | Default starting cash (USD) |

### Acceptance Criteria

- All env vars read with `os.getenv`, defaulting gracefully when unset
- `validate_config` raises `ValueError` for `max_position_pct > 1.0`,
  `min_cash_pct < 0`, `max_positions < 1`, etc.

---

## Task 3 — Supabase Migration (`migrations/001_initial_schema.sql`)

**Estimated effort:** 1–2 h

### Deliverables

A single idempotent SQL file (`CREATE TABLE IF NOT EXISTS`) that creates:

- `portfolios` table
- `holdings` table
- `trades` table
- `snapshots` table
- All CHECK constraints
- All FOREIGN KEY constraints
- All indexes (PK + query-path indexes)
- `updated_at` trigger function + triggers on portfolios, holdings

See `docs/portfolio/03_database_schema.md` for full schema.

### Acceptance Criteria

- File runs without error on a fresh Supabase PostgreSQL database
- All tables created with correct column types and constraints
- `updated_at` auto-updates on every row modification

---

## Task 4 — Supabase Client (`supabase_client.py`)

**Estimated effort:** 3–4 h

### Deliverables

`SupabaseClient` class (singleton pattern) with:

**Portfolio CRUD**
- `create_portfolio(portfolio: Portfolio) -> Portfolio`
- `get_portfolio(portfolio_id: str) -> Portfolio`
- `list_portfolios() -> list[Portfolio]`
- `update_portfolio(portfolio: Portfolio) -> Portfolio`
- `delete_portfolio(portfolio_id: str) -> None`

**Holdings CRUD**
- `upsert_holding(holding: Holding) -> Holding`
- `get_holding(portfolio_id: str, ticker: str) -> Holding | None`
- `list_holdings(portfolio_id: str) -> list[Holding]`
- `delete_holding(portfolio_id: str, ticker: str) -> None`

**Trades**
- `record_trade(trade: Trade) -> Trade`
- `list_trades(portfolio_id: str, limit: int = 100) -> list[Trade]`

**Snapshots**
- `save_snapshot(snapshot: PortfolioSnapshot) -> PortfolioSnapshot`
- `get_latest_snapshot(portfolio_id: str) -> PortfolioSnapshot | None`
- `list_snapshots(portfolio_id: str, limit: int = 30) -> list[PortfolioSnapshot]`

### Error Handling

All methods translate Supabase/HTTP errors into domain exceptions (see Task below).
Methods that query a single row raise `PortfolioNotFoundError` when no row is found.

### Acceptance Criteria

- Singleton — only one Supabase connection per process
- All public methods fully type-annotated
- Supabase integration tests auto-skip when `SUPABASE_URL` is unset

---

## Task 5 — Report Store (`report_store.py`)

**Estimated effort:** 3–4 h

### Deliverables

`ReportStore` class with typed save/load methods for each report type:

| Method | Description |
|--------|-------------|
| `save_scan(date, data)` | Save macro scan JSON |
| `load_scan(date)` | Load macro scan JSON |
| `save_analysis(date, ticker, data)` | Save per-ticker analysis report |
| `load_analysis(date, ticker)` | Load per-ticker analysis report |
| `save_holding_review(date, ticker, data)` | Save holding reviewer output |
| `load_holding_review(date, ticker)` | Load holding reviewer output |
| `save_risk_metrics(date, portfolio_id, data)` | Save risk computation output |
| `load_risk_metrics(date, portfolio_id)` | Load risk computation output |
| `save_pm_decision(date, portfolio_id, data)` | Save PM agent decision JSON + MD |
| `load_pm_decision(date, portfolio_id)` | Load PM agent decision JSON |
| `list_pm_decisions(portfolio_id)` | List all saved PM decision paths |

### Directory Convention

```
reports/daily/{date}/
├── market/
│   └── macro_scan_summary.json        ← save_scan / load_scan
├── {TICKER}/
│   └── complete_report.md             ← save_analysis / load_analysis (existing)
└── portfolio/
    ├── {TICKER}_holding_review.json   ← save_holding_review / load_holding_review
    ├── {portfolio_id}_risk_metrics.json
    ├── {portfolio_id}_pm_decision.json
    └── {portfolio_id}_pm_decision.md  (human-readable version)
```

### Acceptance Criteria

- Directories created automatically on first write
- `load_*` returns `None` when the file doesn't exist (no exception)
- JSON serialisation uses `json.dumps(indent=2)`

---

## Task 6 — Repository (`repository.py`)

**Estimated effort:** 4–5 h

### Deliverables

`PortfolioRepository` class — unified façade over `SupabaseClient` + `ReportStore`.

**Key business logic:**

```
add_holding(portfolio_id, ticker, shares, price):
    existing = client.get_holding(portfolio_id, ticker)
    if existing:
        new_avg_cost = (existing.avg_cost * existing.shares + price * shares)
                       / (existing.shares + shares)
        holding.shares += shares
        holding.avg_cost = new_avg_cost
    else:
        holding = Holding(ticker=ticker, shares=shares, avg_cost=price, ...)
    portfolio.cash -= shares * price   # deduct cash
    client.upsert_holding(holding)
    client.update_portfolio(portfolio)   # persist cash change

remove_holding(portfolio_id, ticker, shares, price):
    existing = client.get_holding(portfolio_id, ticker)
    if existing.shares < shares:
        raise InsufficientSharesError(...)
    if shares == existing.shares:
        client.delete_holding(portfolio_id, ticker)
    else:
        existing.shares -= shares
        client.upsert_holding(existing)
    portfolio.cash += shares * price   # credit proceeds
    client.update_portfolio(portfolio)
```

All DB operations execute as a logical unit (best-effort; full Supabase transactions
require PG functions — deferred to Phase 3+).

### Acceptance Criteria

- `add_holding` correctly updates avg cost basis on repeated buys
- `remove_holding` raises `InsufficientSharesError` when shares would go negative
- `add_holding` raises `InsufficientCashError` when cash < `shares * price`
- Repository integration tests auto-skip when `SUPABASE_URL` is unset

---

## Task 7 — Package Setup

**Estimated effort:** 1 h

### Deliverables

1. `tradingagents/portfolio/__init__.py` — export public symbols
2. `pyproject.toml` — add `supabase>=2.0.0` to dependencies
3. `.env.example` — add new env vars (`SUPABASE_URL`, `SUPABASE_KEY`, `PM_*`)
4. `tradingagents/default_config.py` — merge `PORTFOLIO_CONFIG` into `DEFAULT_CONFIG`
   under a `"portfolio"` key (non-breaking addition)

### Acceptance Criteria

- `from tradingagents.portfolio import PortfolioRepository` works after install
- `pip install -e ".[dev]"` succeeds with the new dependency

---

## Task 8 — Tests

**Estimated effort:** 3–4 h

### Test List

**`test_models.py`**
- `test_portfolio_to_dict_round_trip`
- `test_holding_to_dict_round_trip`
- `test_trade_to_dict_round_trip`
- `test_snapshot_to_dict_round_trip`
- `test_holding_enrich_computes_current_value`
- `test_holding_enrich_computes_unrealized_pnl`
- `test_holding_enrich_computes_weight`
- `test_holding_enrich_handles_zero_cost`

**`test_report_store.py`**
- `test_save_and_load_scan`
- `test_save_and_load_analysis`
- `test_save_and_load_holding_review`
- `test_save_and_load_risk_metrics`
- `test_save_and_load_pm_decision_json`
- `test_load_returns_none_for_missing_file`
- `test_list_pm_decisions`
- `test_directories_created_on_write`

**`test_repository.py`** (Supabase tests skip when `SUPABASE_URL` unset)
- `test_add_holding_new_position`
- `test_add_holding_updates_avg_cost`
- `test_remove_holding_full_position`
- `test_remove_holding_partial_position`
- `test_remove_holding_raises_insufficient_shares`
- `test_add_holding_raises_insufficient_cash`
- `test_record_and_list_trades`
- `test_save_and_load_snapshot`

### Coverage Target

90 %+ for `models.py` and `report_store.py`.
Integration tests (`test_repository.py`) auto-skip when Supabase is unavailable.

---

## Execution Order

```
Day 1  (parallel tracks)
  Track A: Task 1 (models) → Task 3 (SQL migration)
  Track B: Task 2 (config) → Task 7 (package setup partial)

Day 2  (parallel tracks)
  Track A: Task 4 (SupabaseClient)
  Track B: Task 5 (ReportStore)

Day 3
  Task 6 (Repository)
  Task 8 (Tests)
  Task 7 (package setup final — pyproject.toml, .env.example)
```

**Total estimate: ~18–24 hours**
