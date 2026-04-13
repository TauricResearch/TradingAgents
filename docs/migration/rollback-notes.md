# TradingAgents backend migration and rollback notes draft

Status: draft
Audience: backend/application maintainers
Scope: migrate toward application-service boundary and result-contract-v1alpha1 with rollback safety

## 1. Migration objective

Move backend delivery code from route-local orchestration to an application-service layer without changing the quant+LLM merge kernel behavior.

Target outcomes:

- stable result contract (`v1alpha1`)
- thin FastAPI transport
- application-owned task lifecycle and mapping
- rollback-safe migration using dual-read/dual-write where useful

## 2. Current coupling hotspots

Primary hotspot: `web_dashboard/backend/main.py`

It currently combines:

- route handlers
- task persistence
- subprocess creation and monitoring
- progress/stage state mutation
- result projection into API fields
- report export concerns

This file is the first migration target.

## 3. Recommended migration sequence

## Phase 0: contract freeze draft

Deliverables:

- agree on `docs/contracts/result-contract-v1alpha1.md`
- agree on application boundary in `docs/architecture/application-boundary.md`

Rollback:

- none needed; documentation only

## Phase 1: introduce application service behind existing routes

Actions:

- add backend application modules for analysis status, live signals, and report reads
- keep existing route URLs unchanged
- move mapping logic out of route functions into service/mappers

Compatibility tactic:

- routes still return current payload shape if frontend depends on it
- internal service also emits `v1alpha1` DTOs for verification comparison

Rollback:

- route handlers can call old inline functions directly via feature flag or import switch

## Phase 2: dual-read for task status

Why:

Task status currently lives in memory plus `data/task_status/*.json`. During migration, new service storage and old persisted shape may diverge.

Recommended strategy:

- read preference: new application store first
- fallback read: legacy JSON task status
- compare key fields during shadow period: `status`, `progress`, `current_stage`, `decision`, `error`

Rollback:

- switch read preference back to legacy JSON only
- leave new store populated for debugging, but non-authoritative

## Phase 3: dual-write for task results

Why:

To avoid breaking status pages and historical tooling during rollout.

Recommended strategy:

- authoritative write: new application store
- compatibility write: legacy `app.state.task_results` + `data/task_status/*.json`
- emit diff logs when new-vs-legacy projections disagree

Guardrails:

- dual-write only for application-layer payloads
- do not dual-write alternate domain semantics into `orchestrator/`

Rollback:

- disable new-store writes
- continue legacy writes only

## Phase 4: websocket and live signal migration

Actions:

- make `/ws/analysis/{task_id}` and `/ws/orchestrator` render application contracts
- keep websocket wrapper fields stable while migrating internal body shape

Suggested compatibility step:

- send legacy event envelope with embedded `contract_version`
- update frontend consumers before removing legacy-only fields

Rollback:

- restore websocket serializer to legacy shape
- keep application service intact behind adapter

## Phase 5: remove route-local orchestration

Actions:

- delete dead inline task mutation helpers from `main.py`
- keep routes as thin adapter layer
- preserve report retrieval behavior

Rollback:

- only safe after shadow metrics show parity
- otherwise revert to Phase 3 dual-write mode, not direct deletion

## 4. Suggested feature flags

Environment-variable style examples:

- `TA_APP_SERVICE_ENABLED=1`
- `TA_RESULT_CONTRACT_VERSION=v1alpha1`
- `TA_TASKSTORE_DUAL_READ=1`
- `TA_TASKSTORE_DUAL_WRITE=1`
- `TA_WS_V1ALPHA1_ENABLED=0`

These names are placeholders; exact naming can be chosen during implementation.

## 5. Verification checkpoints per phase

For each migration phase, verify:

- same task ids are returned for the same route behavior
- stage transitions remain monotonic
- completed tasks persist `decision`, `confidence`, and degraded-path outcomes
- failure path still preserves actionable error text
- live websocket payloads preserve ticker/date ordering expectations

## 6. Rollback triggers

Rollback immediately if any of these happen:

- task status disappears after backend restart
- WebSocket clients stop receiving progress updates
- completed analysis loses `decision` or confidence fields
- degraded single-lane signals are reclassified incorrectly
- report export or historical report retrieval cannot find prior artifacts

## 7. Explicit non-goals during migration

- do not rewrite `orchestrator/signals.py` merge math as part of boundary migration
- do not rework provider/model selection semantics in the same change set
- do not force frontend redesign before contract shadowing proves parity
- do not implement a new strategy layer inside the application service

## 8. Minimal rollback playbook

If production or local verification fails after migration cutover:

1. disable application-service read path
2. disable dual-write to new store if it corrupts parity checks
3. restore legacy route-local serializers
4. keep generated comparison logs/artifacts for diff analysis
5. re-run backend tests and one end-to-end manual analysis flow

## 9. Review checklist

A migration plan is acceptable only if it:

- preserves orchestrator ownership of quant+LLM merge semantics
- introduces feature-flagged cutover points
- supports dual-read/dual-write only at application/persistence boundary
- provides a one-step rollback path at each release phase
