# TradingAgents Local Web Workbench Design

**Status:** Approved in conversation; review-round-3 fixes complete, round 4 pending  
**Date:** 2026-07-18  
**Scope:** Localhost-only single-user web application for the existing TradingAgents repository

## 1. Summary

TradingAgents will gain a full local web workbench that starts from the terminal, runs the real LangGraph workflow, and makes the analysis process inspectable while it is happening and after it completes.

The application uses a React and TypeScript frontend, a FastAPI backend, REST commands, and Server-Sent Events (SSE). It visualizes all 13 fixed workflow roles, their debate turns, data and tool calls, exact role inputs, prompt context, progress, failures, and final report artifacts. It remains bound to localhost and is not deployed as a public site.

The design treats observability as a product requirement rather than a presentation layer. Every live UI state must be reconstructible from persisted run events and artifacts. The page must never invent progress or infer an input that was not actually passed to the current role.

## 2. First-principles objective

The real user objective is:

1. Start TradingAgents from a local terminal command.
2. Enter a ticker and analysis settings in a browser.
3. Run the existing TradingAgents decision workflow without changing its trading semantics.
4. See what every role did, what it received, what data it used, and what it produced.
5. Verify company profiles, financial statements, market data, indicators, news, and upstream reports against their original sources.
6. Review completed and failed runs after a browser refresh or server restart.

The design must therefore preserve five invariants:

- **Truthfulness:** UI status and content come from actual graph, callback, dataflow, and artifact events.
- **Traceability:** Every material input and output has a role, timestamp, source, period, and stable reference.
- **Isolation:** The first version permits only one active analysis, preventing shared process state from mixing runs.
- **Durability:** Events are persisted before live delivery so history and reconnect use the same source of truth.
- **Local safety:** The server binds to `127.0.0.1`; secrets remain server-side and are removed before persistence.

## 3. Goals

- Add a `tradingagents web` localhost entrypoint.
- Provide a polished desktop-oriented React workbench.
- Stream the real graph lifecycle through SSE.
- Represent all 13 fixed roles with distinct custom SVG icons and stable actor IDs.
- Show per-turn debate output without duplicating cumulative history.
- Show tool names, arguments, results, vendors, durations, and errors.
- Show each role's actual node input, upstream reports, formatted model messages, and original data artifacts.
- Preserve independent run history using a safe `run_id`.
- Reuse the existing report writer and checkpoint safety rules.
- Preserve the existing CLI behavior and test suite.

## 4. Non-goals

- Public hosting, cloud deployment, authentication, accounts, or multiple users.
- Multiple simultaneous analyses, a distributed queue, Redis, or worker services.
- Live brokerage integration or real-money order execution.
- A visual agent/prompt editor or user-defined graph topology.
- Backtesting dashboards, portfolio performance analytics, or mobile-first layouts.
- Storing API keys in the browser, localStorage, run snapshots, events, or reports.
- Rewriting agent reasoning, prompts, data vendor routing, or financial decision semantics.

## 5. Repository constraints and reusable capabilities

The current repository is Python-only and exposes `tradingagents = cli.main:app` from `pyproject.toml`. There is no existing Node build chain or web framework.

Reusable runtime capabilities already exist:

- `TradingAgentsGraph` accepts callbacks and exposes the compiled LangGraph workflow.
- The CLI streams graph state and already extracts AI messages, `ToolMessage` content, tool arguments, analyst reports, investment debate state, risk debate state, and final decisions.
- `tradingagents.dataflows.progress` emits vendor progress events.
- `tradingagents.reporting.write_report_tree` writes the analyst, research, trading, risk, portfolio, and complete Markdown reports.
- `AgentState` already carries the four analyst reports, investment debate, trader plan, risk debate, and final decision.
- The checkpoint implementation already protects resume with a graph-shape signature.

Constraints that the web design must address:

- `graph.stream()` is synchronous and cannot run on the FastAPI event loop.
- The dataflow config and progress sink are process-global.
- The CLI and programmatic `propagate()` paths currently duplicate execution behavior.
- The existing statistics callback counts calls and tokens but does not expose tool completion, output, or failure.
- Sentiment Analyst prefetches news/social data with direct function calls, bypassing LangChain tool callbacks.
- Evidence Steward may create a separate advisor LLM and call Tavily directly, bypassing graph callbacks.
- Debate and manager nodes frequently call `llm.invoke()` without appending their messages to the graph `messages` list.

## 6. Chosen architecture

```text
React + TypeScript + Vite
        |
        | REST commands and snapshots
        | SSE persisted events
        v
FastAPI bound to 127.0.0.1
        |
        v
SingleRunManager
        |
        v
background worker thread
        |
        v
shared AnalysisRunner + RunObserver
        |
        v
real TradingAgents LangGraph
        |
        +--> append-only events.jsonl
        +--> content-addressed input/tool artifacts
        +--> existing Markdown report tree
```

### 6.1 Technology choices

Backend:

- Python 3.10+
- FastAPI
- Uvicorn
- FastAPI/Starlette `StreamingResponse` for SSE
- Existing LangGraph, LangChain, reporting, checkpoint, and provider code

Frontend:

- React
- TypeScript
- Vite
- A reducer-driven event store shared by live and history views
- `react-markdown` with a strict sanitization plugin for Markdown
- Vitest and React Testing Library
- Playwright for browser-level verification

The `web` Python dependencies belong in an optional dependency group. Normal runtime serves the compiled frontend assets through FastAPI. Node/npm are required for frontend development and rebuilding, not for running an already-built package.

### 6.2 Launch contract

The installed command is:

```bash
tradingagents web
```

Defaults:

- host: `127.0.0.1`
- port: `8000`
- browser URL printed to the terminal
- no public or LAN binding
- optional `--open` flag to open the default browser
- optional `--port` override

Binding to `0.0.0.0` is not exposed by the first-version command because the application intentionally has no authentication boundary.

## 7. Component boundaries

### 7.1 `AnalysisRunner`

Purpose: provide one authoritative way to execute TradingAgents and produce a typed event stream.

Responsibilities:

- Build the graph and initial state from validated run inputs.
- Preserve memory, identity resolution, checkpoint, final-state logging, and report behavior currently split across CLI and programmatic paths.
- Stream node-keyed graph updates.
- Merge graph deltas into the current final state.
- Emit typed run, role, turn, message, report, and artifact events.
- Return the same successful final state and decision expected by existing callers; consumer-specific report writing remains outside the runner.

Successful-result interface:

```python
runner.run(request: AnalysisRequest, observer: RunObserver) -> AnalysisResult

@dataclass(frozen=True)
class AnalysisResult:
    final_state: AgentState
    final_signal: str
```

`AnalysisRunner.run` returns only after successful graph completion. It raises `AnalysisCancelled(partial_state: AgentState | None)` on cooperative web cancellation and otherwise re-raises the original graph/provider/data exception with its traceback; early failures are not forced into a fabricated state. A hard process interruption returns nothing and is recovered from `RunStore` on the next server start.

The CLI and web layer consume this interface. CLI rendering remains a consumer, not a second graph execution implementation. The existing `propagate()` compatibility adapter returns `(result.final_state, result.final_signal)` on success and preserves existing exception behavior on failure. Programmatic `propagate()` has no cancellation control and does not gain a partial-result tuple.

### 7.2 `RunObserver`

Purpose: capture everything needed for live visualization and later audit without coupling agents to FastAPI or React.

Responsibilities:

- Attribute callbacks to stable `actor_id` and `node_id` values.
- Capture node-entry input projections.
- Capture formatted model input at `on_chat_model_start` / `on_llm_start`.
- Capture LLM completion, errors, usage, and attempt/fallback path.
- Capture tool start, completion, output, duration, and failure.
- Receive dataflow vendor progress.
- Receive explicit direct-call observations from Sentiment Analyst and Evidence Steward.
- Redact secret-bearing values before persistence.
- Store large data once and replace it with an artifact reference.

Interface:

```python
observer.emit(event: RunEvent) -> PersistedEvent
observer.store_artifact(kind, value, metadata) -> ArtifactRef
```

#### Observation and correlation contract

Every executed role node is wrapped by `ObservedNode(actor_id, projection_fn, node_fn)`. A `turn_id` means one logical role turn, which may span `model -> tool -> model` graph re-entry. Before the first invocation of that logical turn, the wrapper:

1. allocates a stable `turn_id` for the logical role turn;
2. installs an `ObservationContext` in a Python `ContextVar` containing `run_id`, `actor_id`, `node_id`, `turn_id`, `graph_task_id`, and candidate `graph_step` from the task stream/runnable config;
3. captures the whitelisted node-entry projection;
4. emits `turn.started` plus the aggregate `role.status_changed`; and
5. restores the previous context after the Python invocation returns.

Model callbacks read this context and add the LangChain callback run identifier as `model_call_id`. Each initial or fallback model call gets a distinct `attempt_id` under the same `turn_id`. If the model returns tool calls, the observer keeps the turn open and persists `tool.requested` with `tool_call_id -> RoleTurnRef` before the role node returns, so the event is durable before LangGraph checkpoints the transition. Each role-specific `ObservedToolNode` preserves the model-provided `tool_call_id`, looks up that reference, reinstalls the originating observation context, and matches the resulting `ToolMessage` by the same identifier. When the role node is entered again after tool completion, `ObservedNode` reuses the open `turn_id`; it closes the turn only after a final role output without unresolved tool calls, or on terminal failure. A later debate round receives a new `turn_id`. A model retry receives a new `attempt_id`; a repeated logical tool request receives a new `tool_call_id`.

The mapping is restart-safe because `events.jsonl`, not memory, is authoritative. Every graph node invocation also has a `graph_task_id` from LangGraph's `tasks` stream and a candidate `graph_step` equal to the preceding committed checkpoint step plus one. `ObservationContext`, state/prompt/tool/data events, and output-ready events persist both values. Startup reduces these events to rebuild open turns and pending tool references.

#### Durable graph-commit frontier

The installed LangGraph runtime can emit task/update/value output before its default asynchronous checkpoint write is durable. Therefore an update chunk is never treated as a commit barrier. For checkpoint-enabled web runs, `AnalysisRunner` calls:

```python
graph.stream(
    ...,
    stream_mode=["tasks", "updates", "checkpoints"],
    durability="sync",
)
```

Role final output is persisted first as `turn.output_ready`; tool execution is persisted as `tool.execution_completed`. Neither event completes the logical turn/tool request or aggregate role. After the subsequent `checkpoints` stream event confirms that SQLite has synchronously committed the superstep, the runner emits `graph.checkpoint_committed` with checkpoint ID, metadata step, state hash, next nodes, and every applied `graph_task_id`. Only then may it emit `state.updated`, `tool.committed`, `turn.completed`, report revisions, or aggregate-role completion for those tasks. Multiple tools inside one `ToolNode` are correlated by `tool_call_id` and `graph_task_id`, never callback completion order.

Each observed role/tool node also returns one reserved `_observation_commit` state field containing schema version, `graph_task_id`, candidate `graph_step`, node/turn IDs, output-delta hash, and tool-call IDs. It is excluded from every prompt projection, report, and public state view. The applied checkpoint or its `pending_writes` therefore carries the exact same commit token as the candidate event, allowing recovery to match database state to JSONL without timestamp/order inference.

Checkpoint-disabled runs use the yielded applied superstep as an in-process barrier and emit `graph.step_applied` with no checkpoint ID. They can never be resumed after process interruption; the stricter persisted-frontier reconciliation below applies only to checkpoint-enabled runs.

Resume preflight obtains the full latest `CheckpointTuple` from `SqliteSaver.get_tuple()`, including checkpoint ID, metadata step, channel state/next nodes, and `pending_writes`; the existing step-only helper is insufficient. It compares that durable frontier with reduced `graph.checkpoint_committed` events and applies this append-only reconciliation:

1. If the database checkpoint is ahead of the last event marker, match its `_observation_commit` token and output-delta hash to exactly one candidate task, append the missing `graph.checkpoint_committed`, then promote matching `turn.output_ready`/tool execution candidates to their committed terminal events.
2. A task ahead of the checkpoint whose matching `_observation_commit` token appears in `pending_writes` is `executed_pending_apply`. Keep its logical turn/tool request open; LangGraph reuses the durable pending write on resume, and the next synchronous checkpoint promotes it without re-executing the task.
3. Any remaining event-log tail task is `uncommitted_execution`. Append `graph.task_abandoned` plus interrupted lifecycle compensation. A `tool.requested` created by that abandoned task is cancelled with reason `checkpoint_not_committed`; a tool request from an earlier committed task stays pending. On resume, actual model/tool work receives a new `attempt_id`/`tool_execution_id` under the same open `turn_id`.
4. Every checkpoint-pending model `tool_call_id` must still match exactly one committed or `executed_pending_apply` `tool.requested` event and the expected role-specific tool node. Missing, duplicate, state-hash, next-node, or task-ID mismatches are `checkpoint_observation_incompatible` and resume is rejected.

JSONL history is never deleted or rewritten. Candidate and abandoned execution events remain visible as real calls that occurred but were not applied to graph state.

The frontend reducer derives `candidate`, `committed`, `pending_apply`, or `abandoned` application status by joining every task-scoped event to frontier events. Candidate/abandoned model or tool output is visually labeled and is never rendered as an accepted report or debate turn.

When interruption occurred inside a logical turn, resume reopens the same `turn_id` through `turn.resumed`; it never invents a disconnected turn. An interrupted in-flight model call gets a new `attempt_id`. An interrupted or merely requested tool keeps its logical `tool_call_id` but gets a new `tool_execution_id`, so a repeated read-only execution and its vendor calls remain distinguishable. The web workflow exposes only read-only research tools; adding side-effecting tools would require an idempotency contract before they could be resumed.

Sentiment prefetch and Evidence Steward enrichment do not pass through `ObservedToolNode`. Their callers must enter an explicit `observer.direct_call_scope(...)` using the current `turn_id`; each provider attempt receives a `vendor_call_id`. Events without a valid current observation context fail a development assertion and are persisted as unattributed internal diagnostics in production, rather than being silently assigned to the wrong role.

The principal immutable join chains are:

```text
run_id -> role_instance_id -> turn_id -> attempt_id/model_call_id
turn_id -> tool_call_id -> tool_execution_id -> vendor_call_id -> artifact_id
turn_id -> cache_hit_id -> origin vendor_call_id/artifact_id
```

Not every call uses every level, but every child records its nearest available parent identifier.

### 7.3 `SingleRunManager`

Purpose: own the single active worker and expose safe lifecycle operations to FastAPI.

Responsibilities:

- Atomically reject a second active run.
- Start `AnalysisRunner` in a background thread.
- Track active `run_id`, status, cancellation request, and latest sequence.
- Request cooperative cancellation.
- Recover history from run directories after server restart.

It does not contain graph logic and does not parse model output.

### 7.4 `RunStore`

Purpose: provide the durable source of truth for history, replay, and artifacts.

Responsibilities:

- Create safe run directories.
- Atomically write `run.json` snapshots.
- Append and flush `events.jsonl` in sequence order.
- Store content-addressed input, prompt, tool-result, and report artifacts.
- Resolve artifacts only inside the selected run directory.
- List and read runs without requiring a database.

The first version intentionally uses the filesystem rather than SQLite because there is one local process, one active run, and append-only history.

### 7.5 FastAPI application

Purpose: validate HTTP requests, serve the SPA, and translate manager/store operations into REST and SSE.

It does not execute the graph on the event loop and does not synthesize events.

### 7.6 React application

Purpose: render the persisted event model and let the user inspect it.

It contains no TradingAgents business logic. A single reducer processes both live SSE events and historical replay, preventing live/history drift.

### 7.7 `DataProvenanceRecorder`

Purpose: capture the actual vendor request, original response, normalized values, and fallback chain at the data routing/normalization boundary.

`DataProgressEvent` keeps its current CLI-facing stage/method/vendor/message fields and gains optional `run_id`, `turn_id`, `tool_call_id`, `vendor_call_id`, and `artifact_id` fields. The recorder is invoked where a concrete vendor adapter is selected and where its response is normalized, not only from LangChain callbacks. Each fallback vendor attempt has its own `vendor_call_id`, status, duration, error category, and raw/normalized artifact references. The value returned to the agent remains unchanged.

Direct Sentiment and Evidence calls enter the same recorder through `direct_call_scope`, so direct and tool-mediated data use share one provenance model.

The existing module-global news result cache becomes explicitly run-scoped. `SingleRunManager` installs a cache namespace keyed by `run_id` before graph construction and clears it in `finally`; a second run can never consume an earlier run's in-memory entry. A cache entry stores the returned value plus origin vendor-call IDs and raw/normalized artifact references. A same-run hit emits `data.cache_hit` with a new `cache_hit_id`, current `turn_id`/optional `tool_call_id`, cache-key hash, origin IDs/artifacts, and age. It does not pretend that a vendor was called again. A hit missing its origin provenance is treated as a cache miss.

### 7.8 `ReportArtifactWriter`

Purpose: make partial reports durable without changing existing final report names.

Each `report.updated` event writes an immutable content-addressed revision under `report-revisions/<kind>/` and records its `artifact_id` and monotonic revision; no earlier revision is replaced. The canonical `reports/` directory is not pre-created. On successful completion, the web completion adapter invokes the existing `write_report_tree` into a temporary sibling directory, verifies its expected files, fsyncs them, and atomically renames the directory to `reports/`. Only then are final report artifacts recorded and `run.completed` emitted. The existing writer remains authoritative for canonical final filenames and `complete_report.md`.

Report ownership stays outside `AnalysisRunner`. The web completion adapter always writes the canonical tree into the run directory. The CLI writes it only when its existing `save_report` selection is true and preserves the existing CLI destination. Programmatic `propagate()` still does not save reports automatically; `TradingAgentsGraph.save_reports()` remains the explicit programmatic writer.

## 8. Run model and storage

### 8.1 Run identifier

Each run receives a server-generated path-safe identifier:

```text
run_<UTC timestamp>_<8-character uuid4 prefix>
```

Ticker text is metadata and never determines a directory path.

### 8.2 Directory layout

```text
~/.tradingagents/web/runs/<run_id>/
  run.json
  events.jsonl
  data/
    <sha256>.json
  prompts/
    <sha256>.json
  tool-results/
    <sha256>.json
  report-revisions/
    <report-kind>/
      <revision>-<sha256>.md
  reports/
    1_analysts/
    2_research/
    3_trading/
    4_risk/
    5_portfolio/
    complete_report.md
```

`run.json` contains:

- run identity and lifecycle status
- ticker, asset type, analysis date, selected analysts, depth, language
- provider and model names
- configured/missing key status only
- timestamps, latest sequence, final signal, and artifact references
- failure or cancellation summary when applicable
- immutable resume fingerprint, event schema version, runtime semantics hash, and dependency/Python manifest
- `retry_of` or `resumed_from_sequence` when applicable

It never contains secret values.

### 8.3 Persistence order

For every event:

1. Redact and serialize the event.
2. Append it to `events.jsonl`.
3. Flush it so reconnect can observe it.
4. Publish the same persisted event to SSE subscribers.

The UI therefore never observes an event that history cannot replay.

### 8.4 Checkpoint identity and resume fingerprint

The current checkpoint identity is derived from ticker/date plus graph shape. The web layer must not assume that this is sufficient semantic compatibility. Its checkpoint thread identifier is namespaced by `run_id` as well as the existing ticker/date/graph-shape values, preventing two history entries from sharing mutable checkpoint state.

Before the first resumable checkpoint, the server computes and persists the redacted canonical document plus SHA-256 digest for `ResumeFingerprintV1`. Its exact top-level shape is:

```json
{
  "fingerprint_version": 1,
  "request": {
    "ticker": "normalized ticker",
    "analysis_date": "YYYY-MM-DD",
    "asset_type": "stock",
    "selected_analysts": ["registry order"],
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1
  },
  "effective_config": {},
  "runtime_semantics_hash": "sha256",
  "runtime_environment": {
    "python": {},
    "distributions": []
  },
  "event_schema_version": 1,
  "initial_context_hash": "sha256"
}
```

`effective_config` is the complete effective graph/data/LLM configuration mapping after defaults, environment, local config, and request overrides. Keys are sorted recursively. Exactly four location-only keys are excluded: `project_dir`, `results_dir`, `data_cache_dir`, and `memory_log_path`. Credential-named keys are removed recursively using the same redaction-name registry as persistence. `backend_url` is replaced by endpoint identity `(scheme, host, explicit/default port, path)` after user-info, query, and fragment removal. All remaining values, including concurrency/recursion, missing-data policy, coverage thresholds, complete vendor fallback mappings, news queries/domains, credibility/consistency/evidence controls, model retry/thinking/temperature settings, output language, benchmark choices, and future configuration keys, must be JSON-serializable and are included automatically. A non-serializable value fails preflight.

`runtime_semantics_hash` deterministically hashes every `*.py` file under the installed or editable `tradingagents/` package using sorted POSIX relative paths followed by file bytes. `__pycache__`, `.pyc`, tests/fixtures, frontend assets, caches, and generated outputs are excluded. This replaces the ambiguous notion of an application code version and catches runner, observer, prompt, schema, dataflow, and graph behavior changes. `initial_context_hash` hashes the resolved, redacted initial `past_context` and instrument identity placed in the checkpoint; if interruption occurs before this context and the first checkpoint are persisted, resume is unavailable.

`runtime_environment.python` records `sys.implementation.name`, `platform.python_version()`, `sys.implementation.cache_tag`, `sys.abiflags` (or empty), and `sysconfig.get_platform()`. `runtime_environment.distributions` is the sorted transitive closure of installed distributions reachable from every `Requires-Dist` entry in TradingAgents package metadata, ignoring `extra` markers for closure discovery so installed optional provider/data/web packages are included. Each normalized entry contains PEP 503 name, exact version, SHA-256 of `RECORD` (or `SOURCES.txt` fallback), and SHA-256 of `direct_url.json` when present. Dependency names are followed recursively regardless of marker, but only installed distributions are recorded. An installed dependency with neither verifiable record/source metadata nor a version makes the run non-resumable with `unfingerprintable_dependency`; it may still run with checkpoint resume disabled. This captures the unpinned LangGraph, LangChain, checkpoint-saver, provider client, data adapter, and transitive versions that can alter callback, formatting, retry, or checkpoint semantics.

Secret values are neither hashed nor compared. `resume` reuses the same `run_id`, checkpoint thread, event sequence, and directory only when a checkpoint exists and every canonical fingerprint component matches. Any mismatch returns a typed `checkpoint_incompatible` error. `retry` always creates a new run and checkpoint namespace.

On server startup, a run left in `running` or `cancel_requested` is recovered under its run lock: first reconcile the database/event frontier, then append lifecycle compensation, then atomically set the snapshot to `interrupted` and append `run.interrupted`. It is resumable only if its compatible checkpoint still exists; otherwise the UI offers retry.

## 9. Event protocol

### 9.1 Envelope

```json
{
  "schema_version": 1,
  "event_id": "run-id:42",
  "run_id": "run_...",
  "sequence": 42,
  "timestamp": "2026-07-18T12:34:56.123Z",
  "type": "agent.message",
  "team_id": "research",
  "actor_id": "researcher.bull",
  "node_id": "Bull Researcher",
  "status": "completed",
  "parent_event_id": null,
  "payload": {}
}
```

Rules:

- `schema_version`, `event_id`, `run_id`, `sequence`, `timestamp`, and `type` are required.
- `sequence` is strictly increasing within a run.
- `actor_id` is stable and language-independent.
- Large payloads use `ArtifactRef` rather than inline values.
- Unknown future event types are ignored by older clients but remain replayable.

### 9.2 Event types

Run lifecycle:

- `run.started`
- `run.cancel_requested`
- `run.cancelled`
- `run.interrupted`
- `run.resumed`
- `run.completed`
- `run.failed`

Execution lifecycle:

- `graph.task_started`
- `graph.step_applied`
- `graph.checkpoint_committed`
- `graph.task_abandoned`
- `role.status_changed`
- `turn.started`
- `turn.resumed`
- `turn.output_ready`
- `turn.completed`
- `turn.failed`
- `turn.cancelled`
- `turn.interrupted`
- `agent.message`
- `state.updated`
- `report.updated`
- `stats.updated`
- `model.started`
- `model.completed`
- `model.failed`
- `model.interrupted`

Tool and data lifecycle:

- `tool.requested`
- `tool.execution_started`
- `tool.execution_completed`
- `tool.execution_failed`
- `tool.execution_interrupted`
- `tool.committed`
- `tool.cancelled`
- `data.progress`
- `data.completed`
- `data.failed`
- `data.interrupted`
- `data.cache_hit`

Input audit lifecycle:

- `input.state_snapshot`
- `input.config_snapshot`
- `input.prompt_snapshot`
- `input.data_snapshot`

Artifacts:

- `artifact.written`

### 9.3 Required payloads and relationship identifiers

| Event family | Required payload fields |
|---|---|
| `run.*` | `run_status`; terminal events also include safe `summary` and optional `error_category`; resume/interruption includes `checkpoint_sequence` |
| `graph.task_started/abandoned` | `graph_task_id`, candidate `graph_step`, node ID, optional `turn_id`, and reason for abandonment |
| `graph.step_applied/checkpoint_committed` | `graph_step`, applied task IDs, state hash, next nodes; durable commit also requires checkpoint ID |
| `role.status_changed` | `role_instance_id`, previous/new role status, reason, optional triggering `turn_id` |
| `turn.*` | `role_instance_id`, `turn_id`, `graph_task_id`, candidate `graph_step`, actor-local `turn_index`, turn status; output-ready includes output artifact; resume includes `resumed_from_sequence`; terminal events include reason/duration |
| `model.*` | `turn_id`, `graph_task_id`, `attempt_id`, `model_call_id`, provider, model, structured/free-text path; terminal events include `duration_ms`, usage, and optional output/error artifact |
| `agent.message` | `turn_id`, `graph_task_id`, `message_id`, message kind, content or artifact reference |
| `state.updated` | originating `turn_id`, changed top-level state keys, and content/artifact references; never an unbounded full-state dump |
| `input.*` | `turn_id`, `graph_task_id`, capture kind, `artifact_id`, content hash, redaction manifest; prompt input also includes `attempt_id` and `model_call_id` |
| `tool.*` | `turn_id`, `graph_task_id`, nearest `attempt_id`, `tool_call_id`, tool name; requested includes arguments and has no execution ID; execution events require `tool_execution_id`; committed requires the checkpoint/step event ID |
| `data.progress/completed/failed/interrupted` | `turn_id`, `graph_task_id`, optional `tool_call_id`, `vendor_call_id`, method, vendor, stage/status; terminal events include duration and raw/normalized artifacts or error |
| `data.cache_hit` | `turn_id`, `graph_task_id`, optional `tool_call_id`, `cache_hit_id`, cache-key hash, origin vendor-call IDs, origin raw/normalized artifacts, age |
| `report.updated` | `turn_id`, report kind, revision, `artifact_id` |
| `artifact.written` | `artifact_id`, kind, media type, content hash, byte size, safe relative locator |
| `stats.updated` | cumulative calls/tokens/cost where available plus the triggering `turn_id` or `model_call_id` |

`role_instance_id` is deterministically `<run_id>:<actor_id>`. The envelope `parent_event_id` points to the lifecycle event that directly caused the event when known. Reducers join business objects by immutable identifiers, never by display label, timestamp, or array position.

### 9.4 State-transition rules

Run state:

```text
created -> running -> completed | failed
                   -> cancel_requested -> cancelled | failed
running | cancel_requested -> interrupted -> running (explicit resume)
```

Role-card aggregate state for all 13 registry entries:

```text
pending -> running | skipped | not_reached
running -> completed | failed | cancelled | interrupted
completed -> running     (a later debate/risk turn)
interrupted -> running   (explicit resume of the open turn)
```

`skipped`, `not_reached`, `failed`, and `cancelled` are terminal for the run. On process interruption, only the currently running role becomes `interrupted`; roles that never started remain `pending` so resume can reach them. A terminal failure/cancellation converts every still-pending role to `not_reached`. A completed run has no pending/running/interrupted role.

Each logical turn has its own lifecycle, independent from the aggregate card:

```text
started -> output_ready -> completed (only after graph commit)
started | output_ready -> failed | cancelled | interrupted
interrupted -> resumed -> output_ready | failed | cancelled | interrupted
```

Resume reuses the same `turn_id`; a later debate/risk round creates a new `turn_id` and increments `turn_index`. Model call state is `started -> completed | failed | interrupted`; an interrupted turn resumes with a new `attempt_id`. A logical tool call is `requested -> committed | cancelled`. Under it, each execution is independently `started -> completed | failed | interrupted`; an uncommitted or interrupted retry uses a new `tool_execution_id` while preserving the checkpoint-visible `tool_call_id`. Vendor data state is `progress -> completed | failed | interrupted`; multiple progress events may precede one terminal event. Invalid transitions are rejected by backend tests and ignored with a diagnostic by the frontend reducer.

At a cooperative cancellation boundary, the runner emits `tool.cancelled` for every requested but uncommitted logical tool, `turn.cancelled` for the open turn, `role.status_changed` to `cancelled`, changes all remaining pending roles to `not_reached`, and finally emits `run.cancelled`. An in-flight provider/vendor call first reaches its ordinary terminal event, so no model/tool-execution/vendor lifecycle is left open. Unexpected run failure applies the analogous failed/not-reached terminalization. Startup performs commit-frontier reconciliation, emits interrupted events for any remaining open execution/turn/role, and only then emits `run.interrupted`.

### 9.5 Replay, live handoff, reconnect, and backpressure

SSE responses emit `id: <sequence>`. The endpoint accepts an `after` query parameter and honors `Last-Event-ID` on automatic reconnect.

Page load behavior:

1. Fetch the run snapshot.
2. Open the SSE endpoint once, after the browser's last reduced sequence or `0` on a fresh load.
3. Reduce its persisted replay and, for an active run, continue on the same connection into live events.
4. For a terminal run, the server closes the stream after the captured watermark.
5. Deduplicate by `sequence`.

Replay-to-live subscription is atomic under a per-run broker lock:

1. acquire the lock shared with event persistence/publication;
2. register a bounded subscriber queue and capture the current persisted watermark;
3. read persisted events in `(after, watermark]`;
4. release the lock;
5. yield that replay, then queued events with sequence greater than the watermark.

Event publication holds the same lock while assigning sequence, appending and flushing the event, updating the snapshot, and enqueueing the persisted event. Therefore no event can fall between replay and subscription.

Each subscriber has a 512-event deque, a `closed_reason`, and an async condition owned by the FastAPI event loop. The worker uses `loop.call_soon_threadsafe` to perform delivery on that loop. On overflow, the delivery callback sets `closed_reason=slow_consumer`, clears the deque, and notifies the condition; the SSE generator waits on `deque or closed_reason`, so it wakes and closes rather than blocking on a full queue. The client reconnects from its last successfully reduced sequence and catches up from disk; persisted events are never dropped. A 15-second SSE comment acts as a keepalive. Browser disconnect does not cancel the analysis, and disconnected subscribers are unregistered promptly.

## 10. Stable role registry

| Actor ID | Display role | Team | Icon concept | Actual principal inputs |
|---|---|---|---|---|
| `analyst.market` | Market Analyst | analysts | chart bars | instrument context, date, graph messages, stock data, indicators, verified market snapshot |
| `analyst.sentiment` | Sentiment Analyst | analysts | speech pulse | company, date, instrument context, prefetched news, StockTwits, Reddit, formatted messages |
| `analyst.news` | News Analyst | analysts | newspaper | date, asset type, instrument context, messages, company/global news, macro data |
| `analyst.fundamentals` | Fundamentals Analyst | analysts | institution columns | date, instrument context, messages, company profile, balance sheet, cash flow, income statement, fundamentals |
| `evidence.steward` | Evidence Steward | evidence | verified magnifier | company/profile, four analyst reports, date, evidence configuration, enrichment results |
| `researcher.bull` | Bull Researcher | research | rising horn/arrow | four analyst reports, context, asset type, debate history, Bear's latest response |
| `researcher.bear` | Bear Researcher | research | falling paw/arrow | four analyst reports, context, asset type, debate history, Bull's latest response |
| `manager.research` | Research Manager | research | scales | instrument context and complete investment debate history |
| `trader` | Trader | trading | opposing arrows | company, instrument context, research manager investment plan |
| `risk.aggressive` | Aggressive Risk Analyst | risk | lightning | four reports, context, trader plan, risk history, neutral/conservative responses |
| `risk.neutral` | Neutral Risk Analyst | risk | centered crosshair | four reports, context, trader plan, risk history, aggressive/conservative responses |
| `risk.conservative` | Conservative Risk Analyst | risk | shield | four reports, context, trader plan, risk history, aggressive/neutral responses |
| `manager.portfolio` | Portfolio Manager | portfolio | portfolio compass | context, risk history, investment plan, trader plan, past decision context |

User-facing labels may be localized. Actor IDs and event semantics do not change with language.

All 13 cards always render. Immediately after `run.started`, the backend emits an initial `role.status_changed` for every registry entry: selected/fixed roles become `pending`, while unselected analysts become `skipped` with reason `not_selected`. A skipped role's audit panel states that it did not execute and therefore has no captured input or prompt. Terminal failure or cancellation changes selected/downstream roles that never started from `pending` to `not_reached`; process interruption leaves them pending for resume. Input and prompt acceptance requirements apply only to roles that reached `running`.

## 11. Exact role input audit

The input audit combines node-entry state, immutable run/config context, formatted model input, and data provenance.

### 11.1 Node-entry state snapshot

At each executed role node entry, the observer captures only the documented state fields that role reads. It does not dump the entire `AgentState`.

Reasons:

- Full state contains cumulative histories and messages that would be duplicated at every node.
- A whitelist proves what the role could read without implying that unrelated state was used.
- Smaller snapshots are easier to inspect, store, and test.

The snapshot records:

- `actor_id`, `node_id`, `turn_id`, `graph_task_id`, candidate `graph_step`, attempt, and capture time
- projected state fields
- upstream report/event references
- data artifact references
- graph/debate counters needed to understand the turn
- redaction metadata

### 11.2 Effective role-configuration snapshot

Projection functions accept `(state, run_context)` rather than state alone. Every executed role references the immutable redacted effective-config artifact from `run.json`. Evidence Steward additionally emits `input.config_snapshot` at node entry from the actual process-global dataflow `get_config()` value because its evidence/advisor path reads configuration outside `AgentState`.

`EvidenceConfigSnapshotV1` contains these exact current fields: `evidence_gate_enabled`, `evidence_max_enrichment_rounds`, `evidence_max_enrichment_seconds`, `news_min_company_items`, `news_min_mixed_items`, `evidence_stop_on_fail`, `credibility_enabled`, `credibility_domain_overrides`, `consistency_enabled`, `news_advisor_enabled`, `wrong_identity_hints`, `news_article_limit`, `global_news_article_limit`, `global_news_lookback_days`, `global_news_queries`, `news_curator_max_items`, `data_vendors`, `tool_vendors`, `halt_on_missing_data`, `llm_provider`, `quick_think_llm`, `deep_think_llm`, normalized `backend_url` endpoint identity, `google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort`, `temperature`, `llm_max_retries`, `output_language`, and every effective key whose normalized name begins with `tavily_`. The artifact records the whitelist version and hash.

At entry, its canonical hash must equal the corresponding projection from the run's immutable effective configuration. A mismatch means process-global configuration drift and fails the run before evidence evaluation; the UI shows both safe hashes and differing non-secret keys.

### 11.3 Formatted model-input snapshot

`on_chat_model_start` / `on_llm_start` is the authority for what was actually formatted and sent to the selected model. The observer captures:

- message roles and order or final prompt text
- model provider and name
- structured-output versus free-text path
- retry/fallback attempt
- references to large embedded data
- content hash
- redaction manifest

Structured-output fallback is recorded as another attempt of the same role turn, not as another debate turn.

### 11.4 Direct-call coverage

Two existing paths require explicit instrumentation:

- Sentiment Analyst direct news, StockTwits, and Reddit prefetches emit `input.data_snapshot` through the run observer.
- Evidence Steward injects the observer into its temporary advisor LLM and Tavily enrichment calls.

Relying only on LangChain tool callbacks would leave these inputs invisible and is not acceptable.

Every direct or tool-mediated vendor call is captured at the adapter and normalization boundaries by `DataProvenanceRecorder`. This is the authority for the "Raw values" view; `data.progress` text alone is not sufficient evidence.

### 11.5 Artifact representation

Every data artifact stores:

- vendor and tool/method
- request/query arguments after redaction
- retrieval timestamp
- source period/date range
- original field name, value, unit, and currency where applicable
- normalized field name, value, unit, and currency
- completeness or validation metadata already produced by the data layer
- SHA-256 content hash

The role input panel presents five views:

1. **Data fields:** readable normalized values and tables.
2. **Upstream material:** reports, debate responses, and history supplied to the role.
3. **Prompt:** the redacted formatted model messages.
4. **Raw values:** vendor field names, original values, periods, and artifact hashes.
5. **Configuration:** immutable run settings and the executed role's whitelisted configuration snapshot.

## 12. API contract

### 12.1 Configuration

`GET /api/config`

Returns:

- runtime provider/model choices from the actual registry
- configured/missing key status
- supported analysts, depths, output languages, and checkpoint availability
- no secret values

### 12.2 Runs

`POST /api/runs`

Creates and starts a run after validation. Returns HTTP `409` if another run is active.

`GET /api/runs`

Lists run summaries newest first.

`GET /api/runs/{run_id}`

Returns the non-secret `run.json` snapshot.

`POST /api/runs/{run_id}/cancel`

Requests cooperative cancellation for the active run.

`POST /api/runs/{run_id}/retry`

Creates a new run with the same safe input configuration and a new `run_id`.

`POST /api/runs/{run_id}/resume`

Available only for an `interrupted` run when a checkpoint exists, observation correlation reconciles, and the complete stored resume fingerprint matches the current runtime. It continues the same run directory and event sequence, emits `run.resumed`, and records `resumed_from_sequence`. A mismatch is returned as HTTP `409` with the safe fields that differ; secret values are never compared or returned.

### 12.3 Events and artifacts

`GET /api/runs/{run_id}/events?after=<sequence>`

Streams persisted and new SSE events.

`GET /api/runs/{run_id}/artifacts`

Lists safe artifact metadata.

`GET /api/runs/{run_id}/artifacts/{artifact_id}`

Returns an artifact only after validating it belongs to the selected run.

## 13. UI design

The approved desktop workbench uses three persistent columns.

### 13.1 Left column: control and history

- ticker and analysis date
- analyst selection
- research depth
- provider and model selectors
- output language and checkpoint option
- configured/missing key status
- start or cancel state
- recent completed, failed, cancelled, interrupted, and active runs

### 13.2 Center column: workflow and debate

- run header with ticker, stage, elapsed time, calls, and token usage
- all 13 role nodes grouped by workflow stage
- custom inline SVG icon, status, and current round for each role
- live debate/decision timeline
- team and role filters
- manager and portfolio decisions highlighted as verdict cards
- no timer-based fake progress

Debate messages use the node update's current response. Accumulated `history` strings are used for audit/history, not repeatedly rendered as new turns.

### 13.3 Right column: audit inspector

Primary tabs:

- Role Input
- Data & Tools
- Artifacts
- Run Input

Clicking a role selects it and opens Role Input. The panel supports normalized fields, upstream references, prompt messages, raw vendor values, and whitelisted effective configuration. Tool calls expand on demand. Candidate or abandoned work is visibly separated from graph-committed output. Large bodies are fetched only when expanded.

### 13.4 Visual language

- dark financial-research console rather than a generic SaaS dashboard
- restrained gold for active/verified emphasis
- green/red for Bull/Bear only where semantically meaningful
- cyan family for risk roles
- distinctive custom SVG symbols with a shared line weight and container shape
- compact desktop density with readable hierarchy and no decorative animation that obscures state

The approved V2 mockup is stored under the ignored `.superpowers/brainstorm/` directory and was verified with Playwright at a 1280-pixel viewport.

## 14. Run lifecycle

### 14.1 Preflight

Before creating the worker:

- validate ticker and asset type
- reject future or malformed dates
- require at least one analyst
- validate provider, model, and required API key
- verify the run root is writable
- reject a second active run

Validation failures do not create a partially active run.

### 14.2 Execution

- create run directory, emit `run.started`, and initialize all 13 aggregate role states
- start worker thread
- resolve instrument identity and past context
- finalize and persist `ResumeFingerprintV1` before the first resumable checkpoint
- execute graph through `AnalysisRunner`
- persist events and input/tool artifacts
- write immutable partial report revisions when sections become available
- on success, atomically publish the canonical report tree and only then emit `run.completed`

### 14.3 Cancellation

Cancellation is cooperative:

- API sets a cancellation flag and emits `run.cancel_requested`
- an in-flight provider or vendor call is allowed to return
- runner checks the flag at the nearest safe graph/node boundary
- terminalize the open tool/turn/role and mark pending downstream roles `not_reached` as defined in section 9.4
- partial artifacts remain readable
- final status is `cancelled`

The application does not kill Python threads.

### 14.4 Failure

All failures terminalize open model/tool/data/turn lifecycles, update aggregate roles, and emit a safe run error category and message. The run remains in history with all prior events and partial artifacts. The web worker may retain a partial state for display, but it never returns that state through the existing `propagate()` tuple.

Error categories include:

- missing configuration
- no or stale data
- vendor rate limit
- provider timeout or authentication failure
- structured-output failure after configured retry budget
- Evidence Steward rejection
- checkpoint incompatibility
- unexpected internal failure

### 14.5 Retry and resume

Retry creates a new run and links it to `retry_of`. This preserves audit independence.

Only an `interrupted` run is resumable; failed and cancelled runs use retry. Resume is explicit and first requires the existing ticker/date/graph-shape compatibility check, then the complete immutable fingerprint and persisted observation/checkpoint reconciliation in sections 7.2 and 8.4. It continues the same history record and reopens the persisted logical turn when necessary; it never silently changes provider, model, language, data routing, prompt/schema version, or runtime semantics. A process restart converts an orphaned active run and its open lifecycles to `interrupted` before resume is offered.

## 15. Privacy and security

- Bind only to `127.0.0.1`.
- Do not add authentication in the first version because no non-loopback binding is supported.
- Keep API keys in environment/local server configuration.
- Never return key values in config endpoints.
- Recursively redact keys matching authorization, cookie, token, secret, password, api-key, and provider-specific credential names.
- Apply redaction before hashing, persistence, logging, and SSE delivery.
- Mark any redaction in the snapshot metadata.
- Sanitize Markdown and disallow embedded scripts, event handlers, and unsafe URLs.
- Serve frontend assets locally with a restrictive Content Security Policy.
- Validate run and artifact IDs; never construct paths from ticker or request-provided filesystem fragments.
- Explain in the UI that localhost does not prevent selected data vendors and model providers from receiving queries and model context.

### 15.1 Credential-key registry

Key names are normalized to lowercase snake case by replacing dots/hyphens/spaces with underscores. A value is secret only when the normalized key is in the exact registry (`authorization`, `proxy_authorization`, `cookie`, `set_cookie`, `password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `access_token`, `refresh_token`, `id_token`, `bearer_token`, `client_secret`, `private_key`, `aws_secret_access_key`) or ends with `_api_key`, `_token`, `_secret`, `_password`, or `_private_key`. Provider API-key environment names returned by the runtime provider registry are added as exact normalized entries. Arbitrary substring matching is forbidden.

Canonical tests must redact `OPENAI_API_KEY`, `api-key`, `headers.Cookie`, `client-secret`, and `access_token`, while retaining semantic keys such as `max_tokens`, `token_budget`, `news_article_limit`, `secretary_name`, and `consistency_enabled`. The same registry and test vectors are used for HTTP/log/event/artifact redaction and resume-fingerprint exclusion.

## 16. Compatibility and migration

- Existing `tradingagents` interactive behavior remains available.
- `tradingagents web` is additive.
- Existing environment variables and local JSON config remain the source of secret/provider configuration.
- Provider choices come from the runtime registry rather than copied README text.
- Existing report file names and report content remain compatible.
- Existing graph-shape checkpoint signatures and validation rules are retained as a lower-level guard; the web resume fingerprint adds stricter semantic compatibility.
- `AnalysisRunner` returns a successful state/signal only; web status and artifacts are composed by the web worker/observer rather than added to the programmatic tuple.
- `propagate()` still returns `(final_state, final_signal)` only on success and raises on failure. `save_reports()` remains explicit.
- The CLI consumes runner events for live rendering, preserves existing exception/exit behavior, and invokes the canonical report writer only under its existing save-report choice and destination.

## 17. Testing strategy

### 17.1 Backend unit tests

- event schema and strictly increasing sequence
- atomic run snapshot and append-only event writes
- content-addressed artifact deduplication
- recursive secret redaction
- safe run/artifact path resolution
- single-active-run lock
- cancellation state transitions
- all 13 role input projection functions
- structured-output retry/fallback attempt attribution
- observation context propagation and assertion on unattributed callbacks
- run, role, model, tool, and vendor lifecycle transition validation
- resume fingerprint canonicalization and secret exclusion
- complete effective-config inclusion, exact four-key exclusion, endpoint normalization, and runtime semantics hashing
- Python/distribution closure fingerprinting, record/direct-URL digests, and unfingerprintable-dependency handling
- credential registry canonical vectors that retain `max_tokens` and redact real credential keys
- completed-only `AnalysisResult` typing and failure/cancellation exception mapping

### 17.2 Backend integration tests

- deterministic fake graph produces the full workflow lifecycle
- graph node updates map to stable actor IDs
- unselected analysts become `skipped`; unreachable roles become `not_reached`
- repeated Bull/Bear and risk turns update one role card while retaining distinct turn IDs
- direct Sentiment and Evidence Steward calls are observable
- model/tool/vendor identifiers join retries, fallback calls, and artifacts to the correct role turn
- tool completion, vendor fallback, raw/normalized data, failure, and output references persist correctly
- same-run news cache hits reference origin artifacts; later runs cannot consume the prior in-memory cache
- SSE initial replay, atomic replay-to-live handoff, slow-subscriber disconnect, reconnect, and deduplication
- failure retains events and partial reports
- retry creates a separate linked run
- strict compatible and incompatible checkpoint resume behavior, including event-log reconstruction of a pending tool call and rejection of mismatches
- crash injection after each task-scoped event, after pending-write durability, after SQLite commit, and before/after `graph.checkpoint_committed`; recovery must classify committed, pending-apply, and abandoned tails without rewriting JSONL
- cancellation and startup interruption leave no open lifecycle; compatible resume reopens the same turn with new attempt/execution IDs
- Evidence Steward config snapshot matches run config, and deliberate process-global drift fails before evaluation
- immutable partial report revisions and atomic canonical final report publication before `run.completed`
- successful `AnalysisResult`, failing `propagate()` exception, tuple, CLI save/no-save, and explicit `save_reports()` compatibility

### 17.3 Frontend tests

- live and history events use the same reducer
- unknown event types do not crash replay
- all 13 roles render with correct label, team, icon, and status
- role selection opens the correct input audit
- data, upstream, prompt, and raw-value audit tabs
- role configuration audit view and committed/candidate/abandoned output labels
- timeline filtering and per-turn debate rendering
- tool expansion and lazy artifact loading
- safe Markdown rendering
- refresh restores state from sequence replay

### 17.4 Browser tests

- create a fake deterministic run from the UI
- observe all workflow phases and 13 roles, including explicit skipped/not-reached states
- inspect Fundamentals company profile and financial statements
- inspect Market data and indicators
- inspect Bull/Bear upstream reports and opponent responses
- inspect a raw vendor artifact and prompt snapshot
- refresh mid-run and reconnect without duplicates
- review completed and failed history
- verify no configured test secret appears in DOM, HTTP payloads, event files, or artifacts

### 17.5 Real smoke test

With explicit use of an already configured provider and data keys, run one minimum-depth stock analysis. Verify:

- real graph execution completes
- real vendor/tool calls appear
- all participating role inputs are auditable
- reports are written and readable
- history survives server restart
- no secret appears in persisted files or the browser

## 18. Acceptance criteria

The work is complete only when all of the following are true:

1. `tradingagents web` starts the service and prints a working localhost URL.
2. The browser can submit a validated stock analysis.
3. A second active submission is rejected clearly.
4. The UI shows actual live role-turn, debate, tool, data, and report events.
5. All 13 roles have stable IDs, distinct icons, and correct `pending`, `running`, `completed`, `failed`, `cancelled`, `skipped`, `not_reached`, or `interrupted` workflow status across repeated turns.
6. Clicking an executed role shows its captured state inputs and formatted model input; clicking a skipped or not-reached role truthfully explains why no input exists.
7. Fundamentals input exposes company profile, financial statements, periods, units, vendors, raw values, normalized values, and hashes.
8. Market input exposes price data, indicators, and verified snapshot data.
9. Bull/Bear and risk roles expose their upstream reports and current opponent inputs.
10. Large results are referenced rather than duplicated in events.
11. Refresh/reconnect produces no missing or duplicated events.
12. Completed, failed, cancelled, and interrupted runs remain in history after restart.
13. Partial artifacts remain visible after failure or cancellation.
14. Secrets are absent from browser state, HTTP responses, events, prompts, logs, and artifacts.
15. Existing CLI behavior and existing automated tests continue to pass.
16. Backend, frontend, and Playwright tests for the web workflow pass.
17. One real minimum-depth analysis validates the end-to-end path.
18. Every prompt, tool, direct vendor call, fallback attempt, raw/normalized artifact, and partial report can be joined to the correct role turn by persisted identifiers.
19. Resume is refused when any semantic fingerprint field differs, and an interrupted compatible run resumes without mixing configuration or event sequences.
20. Same-run news cache reuse is visible and source-linked, while no in-memory cache entry leaks into a later run.
21. Programmatic success tuples, failure exceptions, explicit report saving, and CLI save/no-save behavior remain compatible.
22. Crash-frontier tests prove that no event-log tail is mistaken for committed graph state and no durable pending write is unnecessarily re-executed.
23. Resume is rejected after Python or semantic dependency version/record changes even when repository source and user configuration are unchanged.

## 19. Alternatives considered

### FastAPI + server-rendered HTML + native JavaScript

Rejected because the approved product requires substantial stateful interaction: 13 roles, live/historical reducers, filters, lazy audit artifacts, and multiple synchronized inspector views. It would reduce tooling but increase bespoke state-management risk.

### Streamlit

Rejected because its rerun model makes long-running lifecycle control, precise event replay, reconnect, cancellation, and deeply customized role auditing harder to reason about.

### WebSocket instead of SSE

Rejected for the first version because run updates are predominantly server-to-client. REST handles start, cancel, retry, and resume. SSE provides native reconnection and a simpler persistence-to-delivery model.

### Multiple simultaneous runs

Deferred because current dataflow configuration and progress sinks are process-global. Single-run operation also matches the first-version local research workflow and avoids premature queue infrastructure.

## 20. Approved design artifacts

- Architecture, event, UI, error, privacy, and testing sections were approved incrementally in conversation.
- The V2 interactive mockup was approved on 2026-07-18.
- The V2 mockup was inspected in a real browser with Playwright; 13 role nodes, role input switching, raw input view, primary tabs, and tool expansion worked without console errors after the favicon fix.
- Progress and current decisions are mirrored in `Handoff.md`.
