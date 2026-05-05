# TradingAgents Shadow Service Runbook

This runbook defines local service commands for the Flint shadow sidecar and
the callback/poll contract expected by Flint-side ingestion.

## Local Dev Commands

```bash
cd /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow
uv venv .venv
uv pip install -e .
```

Start service stack (Postgres + API + worker):

```bash
docker compose --profile service up -d postgres
docker compose --profile service run --rm --entrypoint alembic api upgrade head
docker compose --profile service up --build postgres api worker
```

Stop service stack:

```bash
docker compose --profile service down
```

Run service-contract tests:

```bash
.venv/bin/python -m pytest tests/test_service_contract.py -q
```

## Flint Callback / Poll Contract

Flint should treat this service as advisory-only and use either callback or
polling to obtain run status.

### Create Run

- Method: `POST /v1/shadow-runs`
- Required body fields:
  - `ticker` (preserve suffixes such as `.T`, `.HK`)
  - `trade_date` (`YYYY-MM-DD`)
  - `selected_analysts` subset of `market,social,news,fundamentals`
- Optional header:
  - `Idempotency-Key` (stable key per logical run request)
- Expected response:
  - HTTP `202 Accepted`
  - JSON object including at least:
    - `run_id`
    - `status` (for example `queued`)

### Poll Run

- Method: `GET /v1/shadow-runs/{run_id}`
- Expected fields in run status payload:
  - `run_id`
  - `status` (`queued|running|completed|failed`)
  - `ticker`
  - `trade_date`
  - `result` (present on completion) with Flint-normalization fields:
    - `ticker`
    - `trade_date`
    - `final_rating`
    - `final_decision_markdown`
    - `state_log_dir`
    - `memory_log_path`
    - `provider_model_metadata`

### Callback (Optional)

If callback delivery is enabled for completed runs, callback payloads should
mirror the same run/result shape returned by polling, keyed by `run_id`.
