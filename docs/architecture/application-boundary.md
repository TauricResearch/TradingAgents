# TradingAgents architecture convergence draft: application boundary

Status: draft
Audience: backend/dashboard/orchestrator maintainers
Scope: define the boundary between HTTP/WebSocket delivery, application service orchestration, and the quant+LLM merge kernel

## 1. Why this document exists

The current backend mixes three concerns inside `web_dashboard/backend/main.py`:

1. transport concerns: FastAPI routes, headers, WebSocket sessions, task persistence;
2. application orchestration: task lifecycle, stage progress, subprocess wiring, result projection;
3. domain execution: `TradingOrchestrator`, `LiveMode`, quant+LLM signal merge.

For architecture convergence, these concerns should be separated so that:

- the application service remains a no-strategy orchestration and contract layer;
- `orchestrator/` remains the quant+LLM merge kernel;
- transport adapters can migrate without re-embedding business rules.

## 2. Current evidence in repo

### 2.1 Merge kernel already exists

- `orchestrator/orchestrator.py` owns quant runner + LLM runner composition.
- `orchestrator/signals.py` owns `Signal`, `FinalSignal`, and merge math.
- `orchestrator/live_mode.py` owns batch live execution against the orchestrator.

This is the correct place for quant/LLM merge semantics.

### 2.2 Backend currently crosses the boundary

`web_dashboard/backend/main.py` currently also owns:

- analysis subprocess template creation;
- stage-to-progress mapping;
- task state persistence in `app.state.task_results` and `data/task_status/*.json`;
- conversion from `FinalSignal` to UI-oriented fields such as `decision`, `quant_signal`, `llm_signal`, `confidence`;
- report materialization into `results/<ticker>/<date>/complete_report.md`.

This makes the transport layer hard to replace and makes result contracts implicit.

## 3. Target boundary

## 3.1 Layer model

### Transport adapters

Examples:

- FastAPI REST routes
- FastAPI WebSocket endpoints
- future CLI/Tauri/worker adapters

Responsibilities:

- request parsing and auth
- response serialization
- websocket connection management
- mapping application errors to HTTP/WebSocket status

Non-responsibilities:

- no strategy logic
- no quant/LLM weighting logic
- no task-stage business rules beyond rendering application events

### Application service

Suggested responsibility set:

- accept typed command/query inputs from transport
- orchestrate analysis execution lifecycle
- map domain results into stable result contracts
- own task ids, progress events, persistence coordination, and rollback-safe migration switches
- decide which backend implementation to call during migration

Non-responsibilities:

- no rating-to-signal research logic
- no quant/LLM merge math
- no provider-specific data acquisition details

### Domain kernel

Examples:

- `TradingOrchestrator`
- `SignalMerger`
- `QuantRunner`
- `LLMRunner`
- `TradingAgentsGraph`

Responsibilities:

- produce quant signal, LLM signal, merged signal
- expose domain-native dataclasses and metadata
- degrade gracefully when one lane fails

## 3.2 Canonical dependency direction

```text
transport adapter -> application service -> domain kernel
transport adapter -> application service -> persistence adapter
application service -> result contract mapper
```

Forbidden direction:

```text
transport adapter -> domain kernel + ad hoc mapping + ad hoc persistence
```

## 4. Proposed application-service interface

The application service should expose typed use cases instead of letting routes assemble logic inline.

## 4.1 Commands / queries

Suggested surface:

- `start_analysis(request) -> AnalysisTaskAccepted`
- `get_analysis_status(task_id) -> AnalysisTaskStatus`
- `cancel_analysis(task_id) -> AnalysisTaskStatus`
- `run_live_signals(request) -> LiveSignalBatch`
- `list_analysis_tasks() -> AnalysisTaskList`
- `get_report(ticker, date) -> HistoricalReport`

## 4.2 Domain input boundary

Inputs from transport should already be normalized into application DTOs:

- ticker
- trade date
- auth context
- provider/config selection
- execution mode

The application service may choose subprocess/backend/orchestrator execution strategy, but it must not redefine domain semantics.

## 5. Boundary rules for convergence work

### Rule A: result mapping happens once

Current code maps `FinalSignal` to dashboard fields inside the analysis subprocess template. That mapping should move behind a single application mapper so REST, WebSocket, export, and persisted task status share one contract.

### Rule B: stage model belongs to application layer

Stage names such as `analysts`, `research`, `trading`, `risk`, `portfolio` are delivery/progress concepts, not merge-kernel concepts. Keep them outside `orchestrator/`.

### Rule C: orchestrator stays contract-light

`orchestrator/` should continue returning `Signal` / `FinalSignal` and domain metadata. It should not learn about HTTP status, WebSocket payloads, pagination, or UI labels beyond domain rating semantics already present.

### Rule D: transport only renders contracts

Routes should call the application service and return the already-shaped DTO/contract. They should not reconstruct `decision`, `quant_signal`, `llm_signal`, or progress math themselves.

## 6. Suggested module split

One viable split:

```text
web_dashboard/backend/
  application/
    analysis_service.py
    live_signal_service.py
    report_service.py
    contracts.py
    mappers.py
  infra/
    task_store.py
    subprocess_runner.py
    report_store.py
  api/
    fastapi_routes remain thin
```

This keeps convergence local to backend/application without moving merge logic out of `orchestrator/`.

## 7. Non-goals

- Do not move signal merge math into the application service.
- Do not turn the application service into a strategy engine.
- Do not require frontend-specific field naming inside `orchestrator/`.
- Do not block migration on a full rewrite of existing routes.

## 8. Review checklist

A change respects this boundary if all are true:

- route handlers mainly validate/auth/call service/return contract;
- application service owns task lifecycle and contract mapping;
- `orchestrator/` remains the only owner of merge semantics;
- domain dataclasses can still be tested without FastAPI or WebSocket context.
