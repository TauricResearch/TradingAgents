# TradingAgents Local Web Workbench Design

**Status:** Approved in conversation; independent review fixes in progress  
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
- Emit typed run, node, message, report, and artifact events.
- Return the same final decision and report artifacts expected by existing callers.

Interface and compatibility result:

```python
runner.run(request: AnalysisRequest, observer: RunObserver) -> AnalysisResult

@dataclass(frozen=True)
class AnalysisResult:
    run_id: str
    status: Literal["completed", "cancelled", "failed", "interrupted"]
    final_state: AgentState
    final_signal: str | None
    artifact_refs: tuple[ArtifactRef, ...]
    complete_report: ArtifactRef | None
```

The CLI and web layer consume this interface. CLI rendering remains a consumer, not a second graph execution implementation. The existing `propagate()` compatibility adapter returns `(result.final_state, result.final_signal)` so its tuple semantics do not change.

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
2. installs an `ObservationContext` in a Python `ContextVar` containing `run_id`, `actor_id`, `node_id`, and `turn_id`;
3. captures the whitelisted node-entry projection;
4. emits `node.started`; and
5. restores the previous context after the Python invocation returns.

Model callbacks read this context and add the LangChain callback run identifier as `model_call_id`. Each initial or fallback model call gets a distinct `attempt_id` under the same `turn_id`. If the model returns tool calls, the observer keeps the turn open and records `tool_call_id -> RoleTurnRef` before the role node returns. Each role-specific `ObservedToolNode` preserves the model-provided `tool_call_id`, looks up that reference, reinstalls the originating observation context, and matches the resulting `ToolMessage` by the same identifier. When the role node is entered again after tool completion, `ObservedNode` reuses the open `turn_id`; it closes the turn and emits `node.completed` only after a final role output without unresolved tool calls, or `node.failed` on terminal failure. A later debate round receives a new `turn_id`. A model retry receives a new `attempt_id`; a repeated tool invocation receives a new `tool_call_id`.

Sentiment prefetch and Evidence Steward enrichment do not pass through `ObservedToolNode`. Their callers must enter an explicit `observer.direct_call_scope(...)` using the current `turn_id`; each provider attempt receives a `vendor_call_id`. Events without a valid current observation context fail a development assertion and are persisted as unattributed internal diagnostics in production, rather than being silently assigned to the wrong role.

The immutable join chain is:

```text
run_id -> turn_id -> attempt_id/model_call_id -> tool_call_id -> vendor_call_id -> artifact_id
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

### 7.8 `ReportArtifactWriter`

Purpose: make partial reports durable without changing existing final report names.

Each `report.updated` event atomically writes or replaces the latest revision of that report section and records its `artifact_id` and revision. On successful completion, the existing `write_report_tree` function remains authoritative for canonical final filenames and `complete_report.md`.

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
- immutable resume fingerprint and code/prompt schema versions
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

At run creation the server stores a secret-free, canonical resume fingerprint containing:

- normalized ticker, analysis date, asset type, selected analysts, debate depth, and risk depth;
- provider, quick/deep model names, backend endpoint identity, temperature/reasoning settings, and output language;
- selected data vendors and evidence/news configuration that can alter graph semantics;
- prompt schema version, event schema version, and application code version.

Secret values are excluded. `resume` reuses the same `run_id`, checkpoint thread, event sequence, and directory only when a checkpoint exists and the complete fingerprint matches. Any mismatch returns a typed `checkpoint_incompatible` error. `retry` always creates a new run and checkpoint namespace.

On server startup, a run left in `running` or `cancel_requested` is atomically changed to `interrupted`, and a `run.interrupted` event is appended. It is resumable only if its compatible checkpoint still exists; otherwise the UI offers retry.

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

- `node.started`
- `node.skipped`
- `node.not_reached`
- `node.interrupted`
- `node.completed`
- `node.failed`
- `agent.message`
- `state.updated`
- `report.updated`
- `stats.updated`
- `model.started`
- `model.completed`
- `model.failed`

Tool and data lifecycle:

- `tool.requested`
- `tool.started`
- `tool.completed`
- `tool.failed`
- `data.progress`
- `data.completed`
- `data.failed`

Input audit lifecycle:

- `input.state_snapshot`
- `input.prompt_snapshot`
- `input.data_snapshot`

Artifacts:

- `artifact.written`

### 9.3 Required payloads and relationship identifiers

| Event family | Required payload fields |
|---|---|
| `run.*` | `run_status`; terminal events also include safe `summary` and optional `error_category`; resume/interruption includes `checkpoint_sequence` |
| `node.*` | `role_instance_id`, `role_status`; executed turns include `turn_id`; skip/not-reached/interrupted includes `reason`; completion includes `duration_ms` |
| `model.*` | `turn_id`, `attempt_id`, `model_call_id`, provider, model, structured/free-text path; terminal events include `duration_ms`, usage, and optional output/error artifact |
| `agent.message` | `turn_id`, `message_id`, message kind, content or artifact reference |
| `input.*` | `turn_id`, capture kind, `artifact_id`, content hash, redaction manifest; prompt input also includes `attempt_id` and `model_call_id` |
| `tool.*` | `turn_id`, nearest `attempt_id`, `tool_call_id`, tool name; requested includes arguments; terminal events include duration and result/error artifact |
| `data.*` | `turn_id`, optional `tool_call_id`, `vendor_call_id`, method, vendor, stage/status; terminal events include duration and raw/normalized artifacts or error |
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

Role state for all 13 registry entries:

```text
pending -> running -> completed | failed
pending -> skipped
pending -> not_reached
running -> interrupted  (process termination before a terminal node event)
```

Model state is `started -> completed | failed`. Tool state is `requested -> started -> completed | failed`. Vendor data state is `progress -> completed | failed`; multiple progress events may precede one terminal event. Invalid transitions are rejected by backend tests and ignored with a diagnostic by the frontend reducer.

### 9.5 Replay, live handoff, reconnect, and backpressure

SSE responses emit `id: <sequence>`. The endpoint accepts an `after` query parameter and honors `Last-Event-ID` on automatic reconnect.

Page load behavior:

1. Fetch the run snapshot.
2. Reduce persisted events through the latest stored sequence.
3. If the run is active, open SSE after that sequence.
4. Deduplicate by `sequence`.

Replay-to-live subscription is atomic under a per-run broker lock:

1. acquire the lock shared with event persistence/publication;
2. register a bounded subscriber queue and capture the current persisted watermark;
3. read persisted events in `(after, watermark]`;
4. release the lock;
5. yield that replay, then queued events with sequence greater than the watermark.

Event publication holds the same lock while assigning sequence, appending and flushing the event, updating the snapshot, and enqueueing the persisted event. Therefore no event can fall between replay and subscription.

Subscriber queues hold 512 events. If a client is too slow and its queue fills, the server closes only that SSE connection. The client reconnects from its last successfully reduced sequence and catches up from disk; persisted events are never dropped. A 15-second SSE comment acts as a keepalive. Browser disconnect does not cancel the analysis, and disconnected queues are unregistered promptly.

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

All 13 cards always render. At run creation, each unselected analyst receives `node.skipped` with reason `not_selected`; its audit panel states that the role did not execute and therefore has no captured input or prompt. If failure, cancellation, or interruption prevents a selected/downstream role from starting, it receives `node.not_reached` with the terminal reason. Input and prompt acceptance requirements apply only to roles that reached `running`.

## 11. Exact role input audit

The input audit is a two-layer capture system.

### 11.1 Node-entry state snapshot

At each of the 13 role node entries, the observer captures only the documented state fields that role reads. It does not dump the entire `AgentState`.

Reasons:

- Full state contains cumulative histories and messages that would be duplicated at every node.
- A whitelist proves what the role could read without implying that unrelated state was used.
- Smaller snapshots are easier to inspect, store, and test.

The snapshot records:

- `actor_id`, `node_id`, `turn_id`, attempt, and capture time
- projected state fields
- upstream report/event references
- data artifact references
- graph/debate counters needed to understand the turn
- redaction metadata

### 11.2 Formatted model-input snapshot

`on_chat_model_start` / `on_llm_start` is the authority for what was actually formatted and sent to the selected model. The observer captures:

- message roles and order or final prompt text
- model provider and name
- structured-output versus free-text path
- retry/fallback attempt
- references to large embedded data
- content hash
- redaction manifest

Structured-output fallback is recorded as another attempt of the same role turn, not as another debate turn.

### 11.3 Direct-call coverage

Two existing paths require explicit instrumentation:

- Sentiment Analyst direct news, StockTwits, and Reddit prefetches emit `input.data_snapshot` through the run observer.
- Evidence Steward injects the observer into its temporary advisor LLM and Tavily enrichment calls.

Relying only on LangChain tool callbacks would leave these inputs invisible and is not acceptable.

Every direct or tool-mediated vendor call is captured at the adapter and normalization boundaries by `DataProvenanceRecorder`. This is the authority for the "Raw values" view; `data.progress` text alone is not sufficient evidence.

### 11.4 Artifact representation

Every data artifact stores:

- vendor and tool/method
- request/query arguments after redaction
- retrieval timestamp
- source period/date range
- original field name, value, unit, and currency where applicable
- normalized field name, value, unit, and currency
- completeness or validation metadata already produced by the data layer
- SHA-256 content hash

The role input panel presents four views:

1. **Data fields:** readable normalized values and tables.
2. **Upstream material:** reports, debate responses, and history supplied to the role.
3. **Prompt:** the redacted formatted model messages.
4. **Raw values:** vendor field names, original values, periods, and artifact hashes.

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

Available only when a checkpoint exists and the complete stored resume fingerprint matches the current runtime. It continues the same run directory and event sequence, emits `run.resumed`, and records `resumed_from_sequence`. A mismatch is returned as HTTP `409` with the safe fields that differ; secret values are never compared or returned.

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
- recent completed, failed, cancelled, and active runs

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

Clicking a role selects it and opens Role Input. The panel supports normalized fields, upstream references, prompt messages, and raw vendor values. Tool calls expand on demand. Large bodies are fetched only when expanded.

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

- create run directory and `run.started`
- start worker thread
- resolve instrument identity and past context
- execute graph through `AnalysisRunner`
- persist events and input/tool artifacts
- write partial reports when sections become available
- on success, write the existing complete report tree and `run.completed`

### 14.3 Cancellation

Cancellation is cooperative:

- API sets a cancellation flag and emits `run.cancel_requested`
- an in-flight provider or vendor call is allowed to return
- runner checks the flag at the nearest safe graph/node boundary
- partial artifacts remain readable
- final status is `cancelled`

The application does not kill Python threads.

### 14.4 Failure

All failures emit a typed node/tool/run event with a safe error category and message. The run remains in history with all prior events and partial artifacts.

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

Resume is explicit and first requires the existing ticker/date/graph-shape compatibility check, then the complete immutable fingerprint in section 8.4. It continues the same history record; it never silently changes provider, model, language, data routing, prompt/schema version, or code version. A process restart converts an orphaned active run and any open role turn to `interrupted` before resume is offered.

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

## 16. Compatibility and migration

- Existing `tradingagents` interactive behavior remains available.
- `tradingagents web` is additive.
- Existing environment variables and local JSON config remain the source of secret/provider configuration.
- Provider choices come from the runtime registry rather than copied README text.
- Existing report file names and report content remain compatible.
- Existing graph-shape checkpoint signatures and validation rules are retained as a lower-level guard; the web resume fingerprint adds stricter semantic compatibility.
- `AnalysisRunner` refactoring must preserve programmatic `propagate()` return behavior and the existing CLI output contract.

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

### 17.2 Backend integration tests

- deterministic fake graph produces the full workflow lifecycle
- graph node updates map to stable actor IDs
- unselected analysts become `skipped`; unreachable roles become `not_reached`
- direct Sentiment and Evidence Steward calls are observable
- model/tool/vendor identifiers join retries, fallback calls, and artifacts to the correct role turn
- tool completion, vendor fallback, raw/normalized data, failure, and output references persist correctly
- SSE initial replay, atomic replay-to-live handoff, slow-subscriber disconnect, reconnect, and deduplication
- failure retains events and partial reports
- retry creates a separate linked run
- strict compatible and incompatible checkpoint resume behavior, including orphaned active runs
- partial report revisions and canonical final report writer compatibility
- `AnalysisResult`, `propagate()` tuple, and CLI compatibility

### 17.3 Frontend tests

- live and history events use the same reducer
- unknown event types do not crash replay
- all 13 roles render with correct label, team, icon, and status
- role selection opens the correct input audit
- data, upstream, prompt, and raw-value audit tabs
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
4. The UI shows actual live node, debate, tool, data, and report events.
5. All 13 roles have stable IDs, distinct icons, and correct `pending`, `running`, `completed`, `failed`, `skipped`, `not_reached`, or `interrupted` workflow status.
6. Clicking an executed role shows its captured state inputs and formatted model input; clicking a skipped or not-reached role truthfully explains why no input exists.
7. Fundamentals input exposes company profile, financial statements, periods, units, vendors, raw values, normalized values, and hashes.
8. Market input exposes price data, indicators, and verified snapshot data.
9. Bull/Bear and risk roles expose their upstream reports and current opponent inputs.
10. Large results are referenced rather than duplicated in events.
11. Refresh/reconnect produces no missing or duplicated events.
12. Completed, failed, and cancelled runs remain in history after restart.
13. Partial artifacts remain visible after failure or cancellation.
14. Secrets are absent from browser state, HTTP responses, events, prompts, logs, and artifacts.
15. Existing CLI behavior and existing automated tests continue to pass.
16. Backend, frontend, and Playwright tests for the web workflow pass.
17. One real minimum-depth analysis validates the end-to-end path.
18. Every prompt, tool, direct vendor call, fallback attempt, raw/normalized artifact, and partial report can be joined to the correct role turn by persisted identifiers.
19. Resume is refused when any semantic fingerprint field differs, and an interrupted compatible run resumes without mixing configuration or event sequences.

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
