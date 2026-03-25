# ADR 015 — MongoDB Report Store, Run-ID Namespacing, and Reflexion Memory

**Status**: accepted  
**Date**: 2026-03-24  
**Deciders**: @aguzererler  

## Context

Three problems with the existing filesystem report store:

1. **Same-day overwrites** — Re-running `scan`, `pipeline`, or `auto` on the
   same day silently overwrites earlier results because all reports land in
   the same flat directory (`reports/daily/{date}/…`).

2. **Read/write consistency** — If we simply add a `run_id` to filenames or
   paths, all existing code that reads from fixed paths (e.g.
   `load_scan(date)`, `load_analysis(date, ticker)`, the directory iteration
   in `run_portfolio`) breaks.

3. **No learning from past decisions** — Agent decisions are fire-and-forget.
   There is no mechanism for agents to *reflect* on the accuracy of previous
   calls and adjust accordingly.

## Decisions

### 1. Run-ID Namespacing (Filesystem)

All path helpers in `report_paths.py` accept an optional `run_id`. When set:

```
reports/daily/{date}/runs/{run_id}/market/…
reports/daily/{date}/runs/{run_id}/{TICKER}/…
reports/daily/{date}/runs/{run_id}/portfolio/…
```

A `latest.json` pointer at the date level is updated on every write:

```json
{"run_id": "abc12345", "updated_at": "2026-03-24T12:00:00Z"}
```

Load methods resolve through the pointer when no `run_id` is specified,
falling back to the legacy flat layout for backward compatibility.

### 2. MongoDB Report Store

`MongoReportStore` stores each report as a MongoDB document with `run_id`,
`date`, `report_type`, `ticker`, and `portfolio_id` as natural keys. Multiple
runs on the same day create separate documents — no overwrites by design.

Load methods return the most recent document (sorted by `created_at DESC`)
unless a specific `run_id` is requested.

### 3. Store Factory

`create_report_store(run_id=…)` returns:
- `MongoReportStore` when `TRADINGAGENTS_MONGO_URI` is set (or `mongo_uri` param)
- `ReportStore` (filesystem) otherwise

MongoDB failures fall back to filesystem with a warning log.

### 4. Reflexion Memory

`ReflexionMemory` stores decisions with rationale and later associates
outcomes. Backed by MongoDB when available, local JSON file otherwise.

Key methods:
- `record_decision(ticker, date, decision, rationale, confidence)`
- `record_outcome(ticker, decision_date, outcome)` — feedback loop
- `get_history(ticker, limit)` — recent decisions for a ticker
- `build_context(ticker, limit)` — formatted string for agent prompts

## Consequences & Constraints

### MUST

- **All report writes use a `run_id`** — engine methods generate one via
  `generate_run_id()` at the start of each run.
- **All report reads resolve through `latest.json`** — when no `run_id` is
  specified, the pointer file is consulted.
- **MongoDB is opt-in** — requires setting `TRADINGAGENTS_MONGO_URI`.
  Filesystem remains the default.
- **Factory failures degrade gracefully** — if MongoDB is unreachable, the
  filesystem store is used.

### MUST NOT

- **Never hard-code `ReportStore()` in engine run methods** — always use
  `create_report_store(run_id=…)`.
- **Never assume flat layout for reads** — the directory iteration in
  `run_portfolio` searches both `runs/*/` and the legacy flat layout.

### Actionable Rules

1. When writing a report, always use a store with `run_id` set.
2. When reading a report (for skip-if-exists checks or loading data),
   use a store *without* `run_id` — it will resolve to the latest.
3. The `daily_digest.md` is always at the date level (shared across runs).
4. `pymongo >= 4.12` is a required dependency (installed but optional at
   runtime — only loaded when MongoDB URI is configured).

## Alternatives Considered

- **S3/GCS object store** — Rejected: adds cloud dependency for a local-first
  tool. MongoDB is self-hostable.
- **SQLite for reports** — Rejected: lacks the flexible document model needed
  for heterogeneous report types.
- **Redis for report caching** — Already in use for data caching, but not
  suitable for persistent document storage.
