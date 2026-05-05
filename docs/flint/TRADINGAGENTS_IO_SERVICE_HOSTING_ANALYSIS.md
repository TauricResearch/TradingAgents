# TradingAgents IO, Service, Database, And Hosting Analysis

Date: 2026-04-30

This document evaluates the current TradingAgents Flint shadow repo as a
service candidate: what IO exists now, which database infrastructure would be
useful, how to expose it through an OpenAPI-conformant API, how it could run in
a hosted environment, and whether Cloudflare Workers are a good execution
target.

## Executive Read

TradingAgents is a good candidate for a service API, but not as a single
synchronous request/response function.

The right shape is:

```text
Flint
  -> POST /v1/shadow-runs
  -> queued TradingAgents job
  -> Python worker/container runs LangGraph pipeline
  -> artifacts stored durably
  -> Flint polls / receives callback / ingests normalized evidence
```

Recommended first production architecture:

- API: FastAPI or similar Python API with generated OpenAPI 3.0.
- Worker: Python container running the existing `TradingAgentsGraph` wrapper.
- DB: Postgres for run metadata, status, idempotency, audit trail, normalized
  outputs, and Flint linkage.
- Blob store: S3/R2-compatible storage for full state JSON, markdown reports,
  CSV caches, and raw artifact bundles.
- Queue: Redis/RQ, Celery, Postgres-backed job queue, Cloudflare Queues, or
  managed queue depending on hosting.
- Cloudflare: strong fit for edge API gateway, OpenAPI/API Shield validation,
  auth/WAF/rate limits, queue ingress, R2 artifacts, and possibly Workflows
  orchestration. Weak fit for executing the current Python LangGraph workload
  directly in a standard Worker.

## Current IO Inventory

### Inputs

| Input | Current source | Notes |
| --- | --- | --- |
| `ticker` | CLI arg | Must preserve exchange suffixes such as `.T`, `.HK`, `.TO`. |
| `trade_date` | CLI arg | `YYYY-MM-DD`. |
| `selected_analysts` | CLI arg | Subset of `market,social,news,fundamentals`. |
| provider/model config | `.env.flint-shadow`, CLI overrides | Current local default was `ollama`; model overrides may be required. |
| debate/risk depth | CLI args | `max_debate_rounds`, `max_risk_rounds`. |
| checkpoint flag | CLI arg | Enables per-ticker SQLite checkpoint DB. |
| prior memory | `output/memory/trading_memory.md` | Injected as `past_context` if resolved entries exist. |

### External reads

| Surface | Current implementation | Hosting concern |
| --- | --- | --- |
| LLM calls | `tradingagents/llm_clients/*` | Long latency, provider credentials, structured-output variance. |
| YFinance price/fundamental/news data | `tradingagents/dataflows/y_finance.py`, `yfinance_news.py`, `stockstats_utils.py` | Network latency, rate limits, provider terms, cache strategy. |
| Alpha Vantage | `tradingagents/dataflows/alpha_vantage*` | API key, rate limits, fallback behavior. |
| OpenRouter model listing | `cli/utils.py` only | Interactive CLI concern, not needed for service path. |
| Announcements | `cli/announcements.py` only | Interactive CLI concern, should be disabled in service path. |

### Local writes

| Write | Current path | Should become |
| --- | --- | --- |
| Full state JSON | `output/logs/<ticker>/TradingAgentsStrategy_logs/full_states_log_<date>.json` | Blob artifact plus DB pointer/hash. |
| Technical data cache | `output/cache/<symbol>-YFin-data-*.csv` | Blob artifact or cache table/object keyed by symbol/date range/vendor. |
| Memory log | `output/memory/trading_memory.md` | Structured DB rows plus optional markdown export. |
| Checkpoints | `output/cache/checkpoints/<TICKER>.db` when `--checkpoint` | Job checkpoint table or dedicated object; keep SQLite only for single-host local mode. |
| Interactive CLI reports | `reports/<ticker>_<timestamp>/**` | Service-generated artifact bundle, if needed. |

## What DB Infra Would Be Useful

### DB jobs

A database is useful here, but not because TradingAgents needs a live relational
DB to think. It is useful because Flint connectivity needs traceability,
idempotency, status, audit, and normalized artifact references.

The DB should own:

- Run registry and lifecycle status.
- Idempotency for `(ticker, trade_date, analyst_set, provider/model/config_hash)`.
- Flint linkage: source signal/report id, profile/scope id, requestor, review state.
- Provider/model metadata.
- Normalized final rating and decision fields.
- Artifact manifest with content hashes.
- Per-node timing, warnings, structured-output fallback events, and tool call counts.
- Memory/reflection records currently embedded in markdown.
- Optional checkpoint state metadata.

### Suggested core schema

```sql
shadow_runs (
  id uuid primary key,
  flint_signal_id text null,
  ticker text not null,
  trade_date date not null,
  selected_analysts text[] not null,
  status text not null,
  provider text not null,
  deep_model text not null,
  quick_model text not null,
  config_hash text not null,
  idempotency_key text not null unique,
  requested_by text null,
  created_at timestamptz not null,
  started_at timestamptz null,
  completed_at timestamptz null,
  error_code text null,
  error_message text null
);

shadow_run_artifacts (
  id uuid primary key,
  run_id uuid not null references shadow_runs(id),
  kind text not null,
  uri text not null,
  sha256 text not null,
  bytes bigint not null,
  content_type text not null,
  created_at timestamptz not null
);

shadow_run_outputs (
  run_id uuid primary key references shadow_runs(id),
  final_rating text null,
  final_decision_markdown text null,
  state_log_artifact_id uuid null references shadow_run_artifacts(id),
  memory_artifact_id uuid null references shadow_run_artifacts(id),
  normalized_json jsonb null
);

shadow_run_events (
  id bigserial primary key,
  run_id uuid not null references shadow_runs(id),
  event_type text not null,
  node_name text null,
  payload jsonb not null,
  created_at timestamptz not null
);

shadow_memory_entries (
  id uuid primary key,
  ticker text not null,
  trade_date date not null,
  rating text not null,
  decision_markdown text not null,
  pending boolean not null,
  raw_return numeric null,
  alpha_return numeric null,
  holding_days integer null,
  reflection text null,
  source_run_id uuid null references shadow_runs(id),
  created_at timestamptz not null,
  resolved_at timestamptz null
);
```

### DB choice

| Option | Fit | Use when |
| --- | --- | --- |
| Postgres | Best general fit | You want Flint joins, audit, JSONB, migrations, analytical queries, and later multi-worker execution. |
| SQLite | Good local/dev fit | Single-host local mode, demo mode, or embedded job cache only. Not ideal for multi-instance hosted service. |
| Cloudflare D1 | Good metadata-at-edge fit | You keep metadata small, accept D1's SQLite-like model, and store large artifacts in R2. |
| Durable Objects | Good coordination primitive | You need per-run/per-ticker serialization, locks, or live progress fanout. Not the primary analytical DB. |
| R2 | Best artifact store | Store full state JSON, CSVs, markdown reports, raw logs, and normalized evidence bundles. |
| Vectorize | Later optional | Semantic search over research reports/reflections. Not necessary for first service cut. |

For Flint connectivity, Postgres is the most straightforward primary DB. If the
API edge lives on Cloudflare and the primary DB is external Postgres, use
Hyperdrive for Worker-side DB access. If the service runtime is a Python
container outside Cloudflare, it can connect to Postgres directly.

## API Shape

Make the API asynchronous. A full TradingAgents run can take minutes and has
multiple external dependencies, so `POST /shadow-runs` should return `202
Accepted`, not block until the final decision.

### Minimal endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/shadow-runs` | Create/enqueue a run. |
| `GET` | `/v1/shadow-runs/{run_id}` | Read status and summary. |
| `GET` | `/v1/shadow-runs/{run_id}/events` | Read progress/events. |
| `GET` | `/v1/shadow-runs/{run_id}/artifacts` | Read artifact manifest. |
| `GET` | `/v1/shadow-runs/{run_id}/decision` | Read normalized final decision. |
| `POST` | `/v1/shadow-runs/{run_id}/cancel` | Request cancellation. |
| `POST` | `/v1/shadow-runs/{run_id}/review` | Record Flint-side human review disposition. |
| `GET` | `/healthz` | Liveness. |
| `GET` | `/readyz` | Provider/data/DB/queue readiness. |

### Request example

```json
{
  "ticker": "NVDA",
  "trade_date": "2026-01-15",
  "selected_analysts": ["market", "news"],
  "provider": "ollama",
  "deep_model": "llama3.2:latest",
  "quick_model": "llama3.2:latest",
  "max_debate_rounds": 1,
  "max_risk_rounds": 1,
  "checkpoint": true,
  "flint_context": {
    "signal_id": "sig_...",
    "profile_id": "profile_...",
    "scope": "advisory_shadow"
  },
  "callback_url": "https://flint.example.com/api/shadow-callbacks/tradingagents"
}
```

### Response example

```json
{
  "run_id": "b98bda2f-7b63-4ff0-8571-4b9fc70c05d30",
  "status": "queued",
  "idempotency_key": "sha256:...",
  "links": {
    "self": "/v1/shadow-runs/b98bda2f-7b63-4ff0-8571-4b9fc70c05d30",
    "events": "/v1/shadow-runs/b98bda2f-7b63-4ff0-8571-4b9fc70c05d30/events",
    "decision": "/v1/shadow-runs/b98bda2f-7b63-4ff0-8571-4b9fc70c05d30/decision"
  }
}
```

### OpenAPI concerns

- Publish OpenAPI 3.0, not 3.1, if Cloudflare API Shield schema validation is
  in the path.
- Keep request bodies JSON and reasonably small.
- Avoid exotic schema features in public request validation: external `$ref`,
  unique items, non-basic path templating, and complex parameter objects are
  not good API Shield candidates.
- Model long output artifacts as URLs/manifests rather than giant inline
  response bodies.

## Service Implementation Plan

### Phase 1: Internal service wrapper

- Extract the wrapper body into a function:
  - input: typed `ShadowRunRequest`
  - output: typed `ShadowRunResult`
- Keep CLI as a thin adapter around that function.
- Add a run directory layout keyed by `run_id`, not only ticker/date.
- Write a manifest JSON with every artifact path, hash, and byte count.
- Add DB writes for run status and final normalized output.

### Phase 2: API and queue

- Add FastAPI:
  - `POST /v1/shadow-runs` validates and inserts queued run.
  - Worker process claims queued runs and calls `TradingAgentsGraph`.
  - API serves status and artifact manifests.
- Add OpenAPI generation as a build artifact.
- Add idempotency and duplicate-run behavior.
- Add callback delivery with retry and signed payloads for Flint.

### Phase 3: Hosted production hardening

- Container image with the same Python runtime as local.
- Secrets manager for provider keys.
- Postgres migrations.
- R2/S3 artifact storage.
- Structured JSON logs and per-node metrics.
- Queue retry policy and dead-letter handling.
- Per-provider concurrency limits.
- Human-review state before any Flint-side promotion.

## Hosted Environment Options

### Conventional container host

Best first target.

Examples: Fly.io, Render, Railway, ECS/Fargate, GCP Cloud Run, Azure Container
Apps, Kubernetes if already available.

Why it fits:

- Current code is Python with pandas/yfinance/LangGraph/LLM clients.
- Runs can be long.
- Filesystem assumptions can be replaced gradually.
- Native Postgres/Redis/R2/S3 integration is simple.
- You can run separate API and worker processes from the same image.

Recommended topology:

```text
FastAPI web container
  -> Postgres
  -> Queue
  -> Python worker container(s)
  -> R2/S3 artifact store
  -> Flint callback
```

### Cloudflare edge plus external worker

Strong production shape if Flint already sits behind Cloudflare.

```text
Cloudflare Worker API edge
  -> auth / rate limit / OpenAPI validation / request normalization
  -> Cloudflare Queues
  -> external Python worker via pull consumer or webhook
  -> Postgres + R2
```

Why it fits:

- Cloudflare handles API ingress, WAF, OpenAPI schema validation, and rate
  controls close to the client.
- The expensive Python workload runs where Python containers are normal.
- R2 can store artifacts without egress cost pressure.
- D1 can hold lightweight edge metadata if needed, but Postgres remains the
  better Flint-grade source of truth.

### Cloudflare Worker only

Not recommended for the current code.

Reasons:

- Standard Workers have 128 MB memory per isolate.
- The current workload uses Python, pandas, yfinance, LangGraph, model clients,
  CSV caching, optional SQLite, and long multi-step LLM orchestration.
- Worker CPU limits are request/invocation oriented. Network wait time is not
  CPU, but data parsing, pandas, CSV handling, schema parsing, and graph state
  handling still consume CPU/memory.
- The current code expects a normal filesystem for logs/cache/memory/checkpoints.
- Long HTTP requests are operationally fragile because client disconnects cancel
  request-associated work unless moved to queues/workflows/background paths.

### Cloudflare Workflows

Potentially useful as orchestration, not as the full Python executor.

Good use:

- Create run.
- Persist step metadata.
- Retry callback delivery.
- Coordinate waiting states.
- Trigger external worker steps.
- Store small step results.

Limits to design around:

- Step persisted results are size-limited.
- Large reports and state logs should go to R2/Postgres, with references in
  workflow state.
- Heavy Python execution still belongs in a container or external worker.

### Cloudflare Containers

Promising but should be treated as an experimental/second-phase option because
the product is currently beta.

It is conceptually a better Cloudflare execution target than a plain Worker for
this repo because it can run existing containerized Python code with a normal
runtime. The practical question is whether its beta status, placement behavior,
resource profile, and operational tooling are mature enough for Flint’s
governance needs.

If evaluating it:

- Keep the same OpenAPI edge Worker in front.
- Run TradingAgents inside a Cloudflare Container.
- Store metadata in D1/Postgres and artifacts in R2.
- Do not make Flint depend on this path until reliability and observability are
  proven with repeated checkpointed runs.

## Cloudflare Product Fit

| Product | Fit | Role |
| --- | --- | --- |
| Workers | Strong edge/API fit, weak current executor fit | Auth, OpenAPI validation, request normalization, status endpoints, signed callbacks. |
| Queues | Strong fit | Decouple `POST /shadow-runs` from long execution; retry/dead-letter. |
| Workflows | Medium/strong orchestration fit | Durable orchestration and retries if step payloads stay small. |
| D1 | Medium fit | Edge metadata for small/medium service state. Less ideal than Postgres for Flint-grade query/audit depth. |
| R2 | Strong fit | Artifact store for JSON, markdown, CSV, logs, bundles. |
| Durable Objects | Medium fit | Per-ticker/per-run locking, live progress subscriptions, serialized coordination. |
| Hyperdrive | Strong if using external Postgres from Workers | Accelerated Worker-to-Postgres access. |
| API Shield | Strong fit | Validate OpenAPI 3.0 request schemas at the edge. |
| Vectorize | Later optional | Semantic retrieval over historical reports/reflections. |
| Containers | Promising but beta | Possible all-Cloudflare Python executor after validation. |

## Flint Connectivity Model

Flint should not call TradingAgents as a blocking library. It should treat
TradingAgents as an external advisory evidence generator.

Recommended contract:

1. Flint creates a shadow run with signal/profile/scope context.
2. TradingAgents service records a queued run and returns `run_id`.
3. Worker executes the graph.
4. Service writes artifacts and normalized output.
5. Service sends a signed callback to Flint, or Flint polls status.
6. Flint ingests only normalized advisory evidence and artifact hashes.
7. Flint applies its own governance: traceability, receipts, scope, and human
   review.

The callback payload should include:

- `run_id`
- `flint_signal_id`
- `ticker`
- `trade_date`
- `status`
- `final_rating`
- `final_decision_markdown`
- `artifact_manifest_uri`
- `artifact_hashes`
- `provider/model metadata`
- `warnings` such as structured-output fallback events

## Risk Areas

- LLM nondeterminism and schema fallback: preserve warnings in DB events.
- Provider model mismatch: validate model chat/structured-output capability
  before enqueue or before execution.
- Market-data vendor rate limits: add provider-level throttles and cache reuse.
- Idempotency: avoid duplicate runs for identical signal/config unless explicitly
  forced.
- Artifact integrity: hash every artifact and store immutable object keys.
- Long-running execution: never rely on a single client-connected HTTP request.
- Memory migration: convert markdown memory log into structured rows, but keep a
  markdown export for compatibility.
- Checkpoint semantics: SQLite checkpoints are good locally; hosted mode should
  either use per-job durable checkpoint objects or keep checkpoints inside the
  worker’s run sandbox and upload on failure.

## Recommendation

Build a service, but keep the first hosted version boring:

```text
FastAPI + Postgres + queue + Python worker container + R2/S3 artifacts
```

Put Cloudflare in front as:

```text
Cloudflare Access/WAF/API Shield/Worker edge
  -> enqueue run
  -> expose status
  -> serve signed artifact URLs
```

Do not port the current TradingAgents pipeline directly into a standard
Cloudflare Worker. Use Workers as the control plane and API edge. Consider
Cloudflare Workflows/Queues for orchestration and Cloudflare Containers only as
a deliberate later experiment.

## Source Notes

Repo evidence:

- `scripts/flint/run_shadow_analysis.py`: current wrapper inputs and repo-local output path overrides.
- `tradingagents/graph/trading_graph.py`: graph execution, memory resolution, state logging, memory append, and rating parsing.
- `tradingagents/graph/checkpointer.py`: per-ticker SQLite checkpoint files.
- `tradingagents/agents/utils/memory.py`: append-only markdown memory log.
- `tradingagents/dataflows/*`: vendor data calls and CSV cache.
- `docker-compose.yml`: app container and optional Ollama container only; no DB service.

Cloudflare docs checked on 2026-04-30:

- Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Workflows limits: https://developers.cloudflare.com/workflows/reference/limits/
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- R2 limits: https://developers.cloudflare.com/r2/platform/limits/
- Queues overview: https://developers.cloudflare.com/queues/
- Hyperdrive overview: https://developers.cloudflare.com/hyperdrive/
- Python Workers: https://developers.cloudflare.com/workers/languages/python/
- API Shield schema validation: https://developers.cloudflare.com/api-shield/security/schema-validation/
- Cloudflare Containers overview: https://developers.cloudflare.com/containers/
