# TradingAgents Flint Shadow: Work Performed, I/O Analysis, and Interpretation

Date: 2026-05-01 (Australia/Sydney)  
Repo: `/Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow`

## 1) Executive Summary

This report documents the service build-out completed in this repo, the
operational I/O path now running end-to-end, and interpretation of observed
runtime behavior from a real run.

Current state:

- Async service pattern is operational (`POST -> 202 -> worker -> persisted outputs`).
- Operator UI is operational at `http://localhost:8000/`.
- Real run succeeded with Ollama-backed models and produced decision +
  artifact manifests with hashes.
- Evidence and receipts are persisted in API, Postgres, and artifact manifests.

Primary evidence run:

- `run_id`: `f4edc7b4-95f8-448b-90dc-d9e0f98919e7`
- `ticker`: `NVDA`
- `trade_date`: `2026-01-21`
- final status: `succeeded`
- final rating: `Hold`
- provider/models: `ollama`, `llama3.2:latest`

## 2) Work Performed

### 2.1 Service architecture and API surface

Implemented a hosted-style async service layer around TradingAgents with:

- FastAPI app bootstrap and router composition.
- OpenAPI-backed REST endpoints for:
  - run creation (`POST /v1/shadow-runs`)
  - run retrieval/listing
  - events
  - artifacts
  - decision
  - handoff payload
  - health/readiness

### 2.2 Durable state and queue semantics

Implemented Postgres-backed control plane:

- Schema entities include:
  - `shadow_runs`
  - `shadow_run_events`
  - `shadow_run_artifacts`
  - `shadow_run_outputs`
  - `shadow_memory_entries`
- Idempotency key handling for run creation.
- Queue claim semantics with lock-safe worker claiming.
- State transitions persisted with event timeline.

### 2.3 Worker execution and runner reuse

Implemented async worker loop that:

- claims queued jobs,
- runs extracted `run_shadow_job` path,
- writes success/failure status and outputs,
- emits structured lifecycle events.

### 2.4 Userland operator console

Implemented UI at `/` for:

- composing runs,
- polling status,
- viewing timeline events,
- viewing normalized decision payload,
- viewing artifact manifest,
- generating handoff payload view.

### 2.5 Packaging/runtime fixes required during bring-up

Resolved runtime blockers:

- Added `jinja2` dependency required by template rendering.
- Added `greenlet` dependency required by async SQLAlchemy flow.
- Added package data inclusion for API static and template assets.
- Added configurable Ollama base URL support to avoid Docker localhost trap.
- Updated compose env for API/worker:
  - `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1`

## 3) I/O Analysis (End-to-End)

## 3.1 Input interface

External input contract:

- `ticker` (symbol, suffix-preserving)
- `trade_date` (`YYYY-MM-DD`)
- `selected_analysts` subset
- optional provider/model overrides

Input validation and normalization occur at API schema layer before DB enqueue.

### 3.2 Control-plane flow

1. Client calls `POST /v1/shadow-runs`.
2. API validates payload and computes idempotency key.
3. API inserts or resolves run row in `shadow_runs`.
4. API returns `202 Accepted` + `run_id` and links.
5. Worker polls queue, claims next job atomically.

### 3.3 Execution-plane flow

1. Worker converts DB run row to `ShadowRunRequest`.
2. Runner loads environment/config and builds TradingAgentsGraph config.
3. Graph executes selected analyst pipeline + debate + portfolio decision.
4. Result is normalized into:
   - final rating
   - final decision markdown
   - provider/model metadata
5. Local artifacts are discovered and hashed into manifest entries.

### 3.4 Output surfaces

Outputs are materialized to:

- Postgres:
  - run status and metadata
  - event timeline
  - normalized output summary
  - artifact manifest rows
- filesystem (within repo container path):
  - state logs
  - memory log
- API retrieval endpoints:
  - `/decision`, `/artifacts`, `/events`, `/handoff`

## 4) Data Sources and Intelligence Behaviors

### 4.1 Data sources used

- Runtime market/news/fundamental tools configured via TradingAgents dataflow
  defaults (yfinance-oriented unless overridden).
- Model inference source:
  - Ollama endpoint via OpenAI-compatible interface.
- Internal memory/state:
  - prior memory log context and run-time state logs.

### 4.2 Agentic behaviors observed

Observed from live worker logs and event payloads:

- Structured-output attempts at role stage.
- Automatic fallback to free-text path when structured parse failed.
- Final pipeline still completed to `succeeded`.

Interpretation: system is resilient to strict schema parse failures at
intermediate agent roles and can still produce terminal advisory output.

## 5) Evidence Summary

Evidence artifact:

- `docs/flint/RUN_EVIDENCE_f4edc7b4-95f8-448b-90dc-d9e0f98919e7.md`

Corroborated signals:

- API run object shows terminal `succeeded`.
- DB row in `shadow_runs` matches API status and timestamps.
- `shadow_run_events` shows `running -> succeeded`.
- `/decision` returns final rating and full decision markdown.
- `/artifacts` returns manifest entries with SHA-256 and byte sizes.

## 6) Interpretation and Operational Readout

### 6.1 What is proven

- Hosted async pattern works in practice for real runs.
- Service produces auditable advisory artifacts suitable for Flint-side ingest.
- Operator UX is sufficient for userland run orchestration and inspection.
- Decision provenance is traceable through run/event/output/artifact records.

### 6.2 What is not proven yet

- High-throughput stability and long-duration soak behavior.
- Multi-worker scale behavior under contention.
- Full production hardening (authn/authz, quotas, robust backpressure).
- Cloudflare-specific runtime adaptation (still a follow-on phase).

### 6.3 Noted risks

- Intermittent DB connection pressure was observed in worker logs
  (`too many clients already`) after heavy activity.
- Structured-output role parsing can fail and trigger fallback;
  quality/consistency should be evaluated over larger samples.

## 7) Recommendations (Next Slice)

1. Add DB pool/concurrency controls and max-client guardrails.
2. Add worker health metrics and run-duration SLO tracking.
3. Add retry/dead-letter semantics for repeated model/tool failures.
4. Add regression suite for API + worker + migration + artifact integrity.
5. Add explicit Flint handoff conformance checks in CI (schema and fields).
6. Introduce optional auth/rate-limit layer before broader hosted exposure.

## 8) Conclusion

The repo now behaves as a functional advisory shadow service:

- asynchronous intake,
- durable execution tracking,
- real-model execution,
- normalized decision output,
- artifact-level provenance.

The system is ready for controlled userland use and structured hardening, with
clear evidence trails already in place.
