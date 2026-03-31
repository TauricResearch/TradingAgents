<!-- Last verified: 2026-03-31 -->

# Repository Layer API

This document summarizes the current portfolio data-access surface.

## Layers

### `SupabaseClient`

Location: `tradingagents/portfolio/supabase_client.py`

Current implementation:

- direct PostgreSQL access through `psycopg2`
- connection string from `SUPABASE_CONNECTION_STRING`
- singleton lifecycle via `SupabaseClient.get_instance()`
- typed model conversion for rows returned from SQL
- database exceptions translated into portfolio-domain exceptions

This is not a `supabase-py` or PostgREST wrapper in the current codebase.

### `PortfolioRepository`

Location: `tradingagents/portfolio/repository.py`

`PortfolioRepository` is the main business-logic facade. It composes:

- `SupabaseClient` for transactional portfolio state
- `ReportStore` for non-transactional documents and artifacts

Responsibilities:

- portfolio creation and retrieval
- holding lifecycle and average-cost updates
- cash deduction/credit during trades
- trade recording and snapshot persistence
- enriched reads combining holdings with live prices

### `ReportStore`

Location: `tradingagents/portfolio/report_store.py`

`ReportStore` persists run-scoped scan, analysis, portfolio, checkpoint, and event artifacts under:

```text
reports/daily/{date}/{run_id}/
  market/report/
  {TICKER}/report/
  portfolio/report/
  run_meta.json
  run_events.jsonl
```

Key rules:

- writes require `run_id`
- load methods can search within the configured run or across runs for the date
- timestamp-prefixed artifacts allow multiple rewrites inside one run

Use `create_report_store(run_id=...)` from `tradingagents/portfolio/store_factory.py` for engine/runtime code.

## Exception Hierarchy

Defined in `tradingagents/portfolio/exceptions.py`.

```text
PortfolioError
├── PortfolioNotFoundError
├── HoldingNotFoundError
├── DuplicatePortfolioError
├── InsufficientCashError
├── InsufficientSharesError
├── ConstraintViolationError
└── ReportStoreError
```

## Frequently Used APIs

### `SupabaseClient`

```python
client = SupabaseClient.get_instance()
portfolio = client.get_portfolio(portfolio_id)
holdings = client.list_holdings(portfolio_id)
client.record_trade(trade)
client.save_snapshot(snapshot)
```

Important methods:

- `create_portfolio()`
- `get_portfolio()`
- `list_portfolios()`
- `update_portfolio()`
- `delete_portfolio()`
- `upsert_holding()`
- `get_holding()`
- `list_holdings()`
- `delete_holding()`
- `record_trade()`
- `list_trades()`
- `save_snapshot()`
- `get_latest_snapshot()`
- `list_snapshots()`

### `PortfolioRepository`

```python
repo = PortfolioRepository()
portfolio, holdings = repo.get_portfolio_with_holdings(portfolio_id, prices)
repo.add_holding(portfolio_id, "AAPL", shares=10, price=195.5)
repo.remove_holding(portfolio_id, "AAPL", shares=5, price=210.0)
```

Important methods:

- `create_portfolio()`
- `get_portfolio()`
- `get_portfolio_with_holdings()`
- `add_holding()`
- `remove_holding()`
- `list_holdings()`
- `list_trades()`
- `save_snapshot()`
- `get_latest_snapshot()`

### `ReportStore`

```python
store = create_report_store(run_id=run_id)
store.save_scan(date, scan_summary)
store.save_analysis(date, ticker, analysis)
store.save_pm_decision(date, portfolio_id, decision, markdown=rendered_md)
store.save_execution_result(date, portfolio_id, result)
store.save_run_meta(date, meta)
store.save_run_events(date, events)
```

Important methods:

- `save_scan()` / `load_scan()`
- `save_analysis()` / `load_analysis()`
- `save_holding_review()` / `load_holding_review()`
- `save_risk_metrics()` / `load_risk_metrics()`
- `save_pm_decision()` / `load_pm_decision()`
- `save_execution_result()` / `load_execution_result()`
- `save_run_meta()` / `load_run_meta()`
- `save_run_events()` / `load_run_events()`
- `save_analysts_checkpoint()` / `load_analysts_checkpoint()`
- `save_trader_checkpoint()` / `load_trader_checkpoint()`
- `list_run_metas()`

## Storage Contract Notes

- Root run identity is always `run_id`.
- Checkpoints for reruns are loaded from the original root run.
- `save_*` methods fail fast if no `run_id` is configured.
- In runtime code, do not instantiate `ReportStore()` directly when `create_report_store()` already owns the environment-specific selection logic.

## Related Files

- `tradingagents/portfolio/supabase_client.py`
- `tradingagents/portfolio/repository.py`
- `tradingagents/portfolio/report_store.py`
- `tradingagents/portfolio/store_factory.py`
- `tradingagents/portfolio/models.py`
- `tradingagents/portfolio/exceptions.py`
