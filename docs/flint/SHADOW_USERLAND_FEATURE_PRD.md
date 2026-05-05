# TradingAgents Shadow Service - Userland Feature PRD

## 1) Purpose

Define user-facing feature set on top of existing async shadow-run service so operators can run, inspect, and hand off advisory outcomes to Flint with traceability.

This PRD is UI/product scope only. It does not alter execution boundary:

- advisory only
- no broker order path
- no writes into Flint repo from this repo

## 2) Product Outcome

User can:

1. submit a shadow run in under 30 seconds,
2. monitor progress and failures with clear stage context,
3. inspect normalized decision + artifacts,
4. export a Flint-ingest-ready payload with receipts.

## 3) Users

- Primary: Flint operators/research users comparing model recommendations.
- Secondary: engineering/ops users validating service health and run integrity.

## 4) UX Modules

### 4.1 Run Composer

Inputs:

- `ticker` (preserve suffixes, e.g. `.T`, `.HK`)
- `trade_date` (`YYYY-MM-DD`)
- `selected_analysts` subset:
  - `market`
  - `social`
  - `news`
  - `fundamentals`

Behavior:

- submit triggers async create call
- immediate `run_id` + `queued` status
- request validation errors shown inline

### 4.2 Run Timeline

Run detail surface with:

- status chip (`queued`, `running`, `succeeded`, `failed`, `cancelled`)
- created/updated timestamps
- event feed ordered by sequence
- failure panel (message + stack excerpt + remediation hints)

### 4.3 Decision View

Normalized decision card:

- `final_rating`
- `final_decision_markdown`
- `provider`, `deep_model`, `quick_model`
- `state_log_dir`
- `memory_log_path`

Actions:

- copy markdown
- copy JSON
- export decision bundle

### 4.4 Artifact Explorer

Table:

- `kind`
- `uri`
- `content_type`
- `bytes`
- `sha256`

Actions:

- open/copy URI
- verify hash badge

### 4.5 Run History

List of historical runs with:

- filters: ticker, date range, status
- sort: newest first
- open run detail
- idempotent retry from prior params

### 4.6 Handoff Payload

One-click generation of Flint-ingest-ready advisory payload from completed run.

Includes:

- contract fields from decision view
- artifact manifest
- run metadata and timestamps
- receipts (`run_id`, event sequence bounds)

## 5) API Mapping (Current Contract)

### Create

- `POST /v1/shadow-runs`
- request body:
  - `ticker`
  - `trade_date`
  - `selected_analysts`
  - optional `provider`
  - optional `model`
- response: `202` + `run_id`, `status`, links

### Poll / Details

- `GET /v1/shadow-runs/{run_id}`
- `GET /v1/shadow-runs/{run_id}/events`
- `GET /v1/shadow-runs/{run_id}/decision`
- `GET /v1/shadow-runs/{run_id}/artifacts`

### Service Health

- `GET /healthz`
- `GET /readyz`

## 6) V1 / V2 Cutline

## V1 (ship now)

- Run Composer
- Run Timeline
- Decision View
- Artifact Explorer
- basic Run History (filter + open detail)
- Handoff Payload export (JSON + markdown)

## V2 (next slice)

- run-to-run diff view
- saved analyst presets
- callback subscription UI
- artifact download signing/backends (R2/S3)
- multi-tenant RBAC + audit screens

## 7) Non-Functional Requirements

- Async-only create behavior (`202` expected; no sync execution).
- UI must remain responsive for long-running jobs.
- All user-visible run states sourced from API (no local fake states).
- Show deterministic identifiers (`run_id`, timestamps, event sequence).
- Preserve advisory warning banner on all run/result screens.

## 8) Error Handling

Must explicitly handle:

- validation errors on create
- service unavailable/readiness failure
- run execution failures (e.g. provider connect errors)
- partial artifacts or missing decision for failed runs

UX rule:

- never hide failed state details behind generic toast only

## 9) Acceptance Criteria

1. User submits valid run and sees `run_id` within 2 seconds.
2. Timeline updates from `queued` to terminal state without refresh loops breaking.
3. Failed run shows error message and at least one failed event payload.
4. Decision view renders terminal output when succeeded and empty-safe state when failed.
5. Artifact table renders empty-safe for failed runs, populated rows for successful runs.
6. Handoff payload export always contains:
   - ticker
   - trade_date
   - final rating (nullable if failed)
   - decision markdown (nullable if failed)
   - model/provider metadata
   - state log dir
   - memory log path
   - artifacts array
   - run_id
7. Health/readiness panel reflects live API endpoints.

## 10) Delivery Plan

### Phase A: UI skeleton + API integration

- Build pages/components
- Wire all existing endpoints
- Implement polling + terminal state handling

### Phase B: History + exports

- Add run list/filter view
- Add handoff payload generator

### Phase C: hardening

- Error UX polish
- Empty/edge states
- Basic observability hooks

## 11) Out of Scope

- broker execution actions
- Flint repo mutations
- strategy auto-trading
- live cutover logic

