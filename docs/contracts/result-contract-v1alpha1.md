# TradingAgents result contract v1alpha1 draft

Status: draft
Audience: backend, desktop, frontend, verification
Format: JSON-oriented contract notes with examples

## Current implementation snapshot (2026-04)

Mainline backend behavior now partially matches this draft already:

- `web_dashboard/backend/services/job_service.py` emits public task/job payloads with `contract_version = "v1alpha1"`;
- `web_dashboard/backend/services/result_store.py` persists result contracts under `results/<task_id>/result.v1alpha1.json`;
- `web_dashboard/backend/api/portfolio.py` and `/ws/orchestrator` already expose `v1alpha1` envelopes by default;
- live signal payloads currently carry `data_quality`, `degradation`, and `research` as top-level contract fields in addition to `result` / `error`.

This document is therefore a **working contract doc**, not a pure future sketch.

## 1. Goals

`result-contract-v1alpha1` defines the stable shapes exchanged across:

- analysis start/status APIs
- websocket progress events
- live orchestrator streaming
- persisted task state
- historical report projection

The contract should be application-facing, not raw domain dataclasses.

## 2. Design principles

- version every externally consumed payload
- keep transport-neutral field meanings
- allow partial/degraded results when quant or LLM lane fails
- distinguish task lifecycle from signal outcome
- keep raw domain metadata nested, not smeared across top-level fields

## 3. Core enums

## 3.1 Task status

```json
["pending", "running", "completed", "failed", "cancelled"]
```

## 3.2 Stage name

```json
["analysts", "research", "trading", "risk", "portfolio"]
```

## 3.3 Decision rating

```json
["BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL"]
```

## 4. Canonical envelope

All application-facing payloads should include:

```json
{
  "contract_version": "v1alpha1"
}
```

Optional transport-specific wrapper fields such as WebSocket `type` may sit outside the contract body.

## 5. Analysis task contract

## 5.1 Accepted response

```json
{
  "contract_version": "v1alpha1",
  "task_id": "600519.SS_20260413_120000_ab12cd",
  "ticker": "600519.SS",
  "date": "2026-04-13",
  "status": "running"
}
```

## 5.2 Status / progress document

```json
{
  "contract_version": "v1alpha1",
  "task_id": "600519.SS_20260413_120000_ab12cd",
  "ticker": "600519.SS",
  "date": "2026-04-13",
  "status": "running",
  "progress": 40,
  "current_stage": "research",
  "created_at": "2026-04-13T12:00:00Z",
  "elapsed_seconds": 18,
  "stages": [
    {"name": "analysts", "status": "completed", "completed_at": "12:00:05"},
    {"name": "research", "status": "running", "completed_at": null},
    {"name": "trading", "status": "pending", "completed_at": null},
    {"name": "risk", "status": "pending", "completed_at": null},
    {"name": "portfolio", "status": "pending", "completed_at": null}
  ],
  "result": null,
  "error": null
}
```

Notes:

- `elapsed_seconds` is preferred over the current loosely typed `elapsed`.
- stage entries should carry explicit `name`; current positional arrays are fragile.
- `result` remains nullable until completion.

## 5.3 Completed result payload

```json
{
  "contract_version": "v1alpha1",
  "task_id": "600519.SS_20260413_120000_ab12cd",
  "ticker": "600519.SS",
  "date": "2026-04-13",
  "status": "completed",
  "progress": 100,
  "current_stage": "portfolio",
  "result": {
    "decision": "OVERWEIGHT",
    "confidence": 0.64,
    "signals": {
      "merged": {"direction": 1, "rating": "OVERWEIGHT"},
      "quant": {"direction": 1, "rating": "OVERWEIGHT", "available": true},
      "llm": {"direction": 1, "rating": "BUY", "available": true}
    },
    "degraded": false,
    "report": {
      "path": "results/600519.SS/2026-04-13/complete_report.md",
      "available": true
    }
  },
  "error": null
}
```

## 5.4 Failed result payload

```json
{
  "contract_version": "v1alpha1",
  "task_id": "600519.SS_20260413_120000_ab12cd",
  "ticker": "600519.SS",
  "date": "2026-04-13",
  "status": "failed",
  "progress": 60,
  "current_stage": "trading",
  "result": null,
  "error": {
    "code": "analysis_failed",
    "message": "both quant and llm signals are None",
    "retryable": false
  }
}
```

## 6. Live signal batch contract

This covers `/ws/orchestrator` style responses currently produced by `LiveMode`.

```json
{
  "contract_version": "v1alpha1",
  "signals": [
    {
      "ticker": "600519.SS",
      "date": "2026-04-13",
      "status": "completed",
      "result": {
        "direction": 1,
        "confidence": 0.64,
        "quant_direction": 1,
        "llm_direction": 1,
        "timestamp": "2026-04-13T12:00:11Z"
      },
      "degradation": null,
      "data_quality": {"state": "ok"},
      "research": null,
      "error": null
    },
    {
      "ticker": "300750.SZ",
      "date": "2026-04-13",
      "status": "failed",
      "result": null,
      "degradation": {
        "degraded": true,
        "reason_code": "provider_mismatch"
      },
      "data_quality": {"state": "provider_mismatch", "source": "llm"},
      "research": {
        "research_status": "failed",
        "research_mode": "degraded_synthesis",
        "timed_out_nodes": ["Bull Researcher"],
        "degraded_reason": "bull_researcher_connectionerror",
        "covered_dimensions": ["market"],
        "manager_confidence": null
      },
      "error": {
        "code": "live_signal_failed",
        "message": "both quant and llm signals are None",
        "retryable": false
      }
    }
  ]
}
```

## 7. Historical report contract

```json
{
  "contract_version": "v1alpha1",
  "ticker": "600519.SS",
  "date": "2026-04-13",
  "decision": "OVERWEIGHT",
  "report": "# TradingAgents ...",
  "artifacts": {
    "complete_report": true,
    "stage_reports": {
      "analysts": true,
      "research": true,
      "trading": true,
      "risk": true,
      "portfolio": false
    }
  }
}
```

## 8. Mapping from current implementation

Current backend fields in `web_dashboard/backend/main.py` map roughly as follows:

- `decision` -> `result.decision`
- `quant_signal` -> `result.signals.quant.rating`
- `llm_signal` -> `result.signals.llm.rating`
- `confidence` -> `result.confidence`
- `result_ref` -> persisted result contract location under `results/<task_id>/result.v1alpha1.json`
- top-level `error` string -> structured `error`
- positional `stages[]` -> named `stages[]`

## 9. Compatibility notes

### v1alpha1 tolerances

Consumers should tolerate:

- absent `result.signals.quant` when quant path is unavailable
- absent `result.signals.llm` when LLM path is unavailable
- `result.degraded = true` when only one lane produced a usable signal

### fields to avoid freezing yet

Do not freeze these until config-schema work lands:

- provider-specific configuration echo fields
- raw metadata blobs from quant/LLM internals
- report summary extraction fields

Additional note:

- trace/profiling payloads are **not** part of `result-contract-v1alpha1`; they use separate offline trace/A-B helper files under `orchestrator/`.

## 10. Open review questions

- Should `rating` remain duplicated with `direction`, or should one be derived client-side?
- Should task progress timestamps standardize on RFC 3339 instead of mixed clock-only strings?
- Should historical report APIs return extracted summary separately from full markdown?
