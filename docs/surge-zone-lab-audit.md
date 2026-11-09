# Surge Zone Lab: audit and incremental plan

Follow-up: both reference cards were supplied and reviewed after this initial audit.
See [the verified rule mapping](surge-reference-rules.md) for implemented boundary
formulas, scoring bands, and remaining automation gaps. The initial findings below
record what was available before the first implementation.

Audit date: 2026-11-08. Starting branch: `main`; working tree clean. No AGENTS.md,
Surge prototype, reference cards, or Trade Tracker spreadsheet found in the repository
or its parent project directory. No credentials were inspected. Repository license:
Apache-2.0; preserve attribution and license. EODHD data rights and entitlements are
separate from the code license; no bundled/downloaded market data will be committed.

## Existing architecture and reuse

- `dataflows/router.py` selects explicitly configured vendor chains; Yahoo and Alpha
  Vantage serve price tools. Keep their routing and defaults unchanged in this slice.
- `dataflows/net.py` scrubs query-token HTTP errors. `dataflows/files.py` provides
  cross-process cache locking and atomic replacement; reuse both.
- `graph/setup.py` fans out isolated analyst subgraphs, joins reports for Bull/Bear,
  then runs Trader, risk debate, and Portfolio Manager. `agents/state.py`,
  `agents/tools.py`, and `agents/analysts/market_analyst.py` are later opt-in adapter
  points for a structured, dated Surge report. No graph changes in the first slice.
- `vendors/yahoo/snapshot.py` already grounds exact market numbers. Surge should
  follow that contract, with Python-owned values and explicit rule provenance.
- `memory/` stores and settles agent decisions; SQLite graph checkpoints support
  recovery. Neither is a trade ledger. Do not mix experimental zones into that log.
- `backtest.py` evaluates agent ratings over a date grid, not fills or portfolios.
  Zone event replay and OHLC ambiguity need a separate engine.
- `portfolio.py`, structured schemas, and reporting can later consume a verified
  Surge adapter. CLI remains available unchanged. Tests use pytest with network
  blocked by default; Ruff is configured; CI spans Python 3.11–3.14.
- Core uses pandas, requests, LangGraph and several LLM SDKs. There is no dashboard,
  EODHD integration, zone engine, supervised ML, or SQLite trade journal.

## First reviewable slice and expected files

1. Optional `surge` extra: Streamlit, Plotly, exchange-calendars for US sessions.
2. `dataflows/vendors/eodhd.py`: daily US OHLCV, strict normalization, completed
   session filtering, provenance, raw prices, local snapshot cache, explicit refresh.
3. `surge/engine.py`: configurable causal RBR/DBR/RBD/DBD detection and measurements;
   experimental body-to-wick boundaries shared across patterns, no official score.
4. `surge/chart.py`, `surge/app.py`: candlesticks, base/leg highlights, confirmation
   markers, provenance, replay cutoff, CSV export. No order execution or trade button
   until an editable/persistent journal exists.
5. `tests/test_surge_*.py`, an optional-extra CI job, documentation, `.env.example`, README link.

## Data and rule constraints

Reference Card 1 is required for exact pattern-specific proximal/distal rules.
Reference Card 2 is required for all six scoring bands, freshness/penetration rules,
HTF curve, ITF trend, controlling swings and breakout segments. The supplied maxima
(2,1,2,2,1,2) do not specify scoring rules. Official score is unavailable (zero
criteria implemented), never 0/10 or an invented partial ranking. Scores are not
probabilities. Candle displacement and volume are measurements, not evidence of
institutional activity.

EODHD daily adjusted_close includes retrospective adjustments. Use raw OHLCV for
the initial chart/detector, retain adjusted_close, flag changes in adjustment factor,
and reject detections spanning those discontinuities. This does not reconstruct
point-in-time corporate actions. Current revised history cannot support leakage-free
ML or certified historical performance. Record retrieval time and cache semantics.
Do not synthesize missing sessions. Respect actual XNYS sessions, DST and early closes.

## Follow-up increments

1. Intraday 1m/5m/1h with entitlement-aware chunking and budgets; session-anchored
   15m/4h resampling, partial-session policy, gaps and split handling. Full corporate
   action revision strategy before merging incremental raw histories.
2. Transcribe/verify cards with golden fixtures; version official boundaries and
   scoring, implement multi-timeframe controlling swings/curve/trend.
3. Event-sourced revisits/invalidation, next-bar entries, stops, independent 1R/2R/3R
   outcomes, ambiguous OHLC policies, MFE/MAE, costs and reproducible replay tests.
4. SQLite migrations for immutable opportunities/predictions and separately editable
   trades/fills/exits/fees; all opportunities retained; CSV and optional Excel export.
5. Transparent baselines, purged chronological/walk-forward splits with late-label
   embargo, preprocessing fit only on training, calibration/Brier, expectancy/drawdown
   and regime/sample-size reporting; versioned controlled retraining.
6. Eight dashboard pages and opt-in deterministic tool/node adapter. Agents interpret
   dated immutable numeric reports without inventing levels/scores/statistics.

No main merge, live brokerage orders, production behavior changes, or automatic
model retraining. Each increment needs independent tests and a reviewable diff.
