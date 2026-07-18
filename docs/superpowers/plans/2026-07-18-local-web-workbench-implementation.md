# TradingAgents Local Web Workbench Implementation Plan

**Status:** Ready for implementation  
**Approved design:** `docs/superpowers/specs/2026-07-18-local-web-workbench-design.md`  
**Date:** 2026-07-18

## 1. Delivery objective

Deliver a localhost-only workbench started with `tradingagents web` that runs the real TradingAgents graph, allows only one active analysis, retains history, and truthfully visualizes all 13 roles, debate turns, model/tool/vendor calls, exact role inputs, raw and normalized data, configuration, partial artifacts, and final reports.

Implementation order follows the evidence chain:

```text
contracts and compatibility
  -> durable events, storage, and redaction
  -> graph observation and provenance
  -> shared real AnalysisRunner
  -> checkpoint frontier and run lifecycle
  -> REST/SSE boundary
  -> reducer-driven React workbench
  -> browser and real-provider verification
```

The frontend must never be used to imply progress or provenance that the backend has not actually persisted.

## 2. Working rules

- Complete stories in dependency order unless the plan explicitly marks them parallel.
- Every story begins with a failing focused test or fixture and ends with its focused verification command.
- Preserve unrelated dirty-worktree content and existing untracked `.claude/`, `.codex/`, `.playwright-cli/`, and `openspec/` paths.
- Keep web imports lazy so the existing CLI and base package do not require FastAPI.
- Keep `write_report_tree()` authoritative for canonical final report content.
- Keep `propagate()` success tuples and failure exceptions compatible.
- Update `Handoff.md` at the end of each implementation phase.
- Do not claim a story complete from compilation alone; verify its stated acceptance criteria.

## 3. Priority

### Must have

- All stories in phases A–H.
- One real minimum-depth configured-provider smoke test.
- Compiled frontend assets included in the Python package.

### Won't have in this release

- Public/LAN binding, authentication, multiple concurrent runs, brokerage execution, prompt editing, mobile-first UI, backtesting, or cloud deployment.

## 4. Phase A — compatibility and runtime foundations

### Story A1 — Freeze existing execution and CLI contracts

**As a** current CLI/programmatic user  
**I want** the web refactor to preserve existing behavior  
**So that** the new workbench does not regress existing workflows.

**Points:** 3  
**Dependencies:** none

**Files**

- Create `tests/test_analysis_runner_compat.py`
- Create `tests/test_cli_entrypoint_compat.py`
- Extend `tests/test_reporting.py`
- Extend `tests/test_memory_log.py`
- Inspect without changing behavior: `tradingagents/graph/trading_graph.py`, `cli/main.py`

**Tasks**

- Freeze the exact `(final_state, final_signal)` success tuple.
- Freeze original exception type/message propagation and checkpointer cleanup.
- Freeze memory resolution, identity resolution, state logging, decision-memory writes, and signal processing.
- Freeze `tradingagents analyze`, root Typer dispatch, config/checkpoint flags, CLI report save/no-save, and explicit `save_reports()` behavior.

**Acceptance criteria**

- Success returns exactly the legacy tuple.
- Failure never returns a partial tuple or silently wraps the original exception.
- CLI report publication occurs only under its existing save choice.
- Existing CLI invocation remains unambiguous after a `web` command is added.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/test_analysis_runner_compat.py tests/test_cli_entrypoint_compat.py tests/test_reporting.py tests/test_memory_log.py'
```

### Story A2 — Establish the web runtime and capability floor

**As a** local operator  
**I want** startup to reject incompatible graph runtimes immediately  
**So that** checkpoint correctness never depends on unavailable APIs.

**Points:** 3  
**Dependencies:** none

**Files**

- Modify `pyproject.toml`
- Create `tradingagents/web/__init__.py`
- Create `tradingagents/web/preflight.py`
- Create `tests/web/test_preflight.py`

**Tasks**

- Add the `[web]` optional dependency group with FastAPI, Uvicorn, RFC 8785 support, and approved LangGraph/checkpointer floors.
- Keep all web imports lazy from `cli/main.py`.
- Implement version checks and a temporary SQLite feature probe for sync durability, task/checkpoint streams, task/checkpoint IDs, steps, and `pending_writes`.
- Return a typed `WebCapabilityReport` and actionable install command on failure.

**Acceptance criteria**

- Unsupported versions and missing capabilities fail before Uvicorn starts.
- Base imports work without the web extra.
- Exact resolved runtime capability information is available to fingerprinting.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_preflight.py'
```

### Story A3 — Define event, role, request, and lifecycle contracts

**As a** frontend and backend implementer  
**I want** one typed protocol  
**So that** live and historical rendering cannot drift.

**Points:** 3  
**Dependencies:** none

**Files**

- Create `tradingagents/observability/__init__.py`
- Create `tradingagents/observability/events.py`
- Create `tradingagents/observability/roles.py`
- Create `tradingagents/observability/lifecycle.py`
- Create `tradingagents/execution/__init__.py`
- Create `tradingagents/execution/models.py`
- Create `tests/web/test_event_contracts.py`
- Create `tests/web/test_lifecycle.py`

**Tasks**

- Implement `RunEventDraft`, `PersistedEvent`, `ArtifactRef`, `ObservationCommitV1`, `AnalysisRequest`, successful `AnalysisResult`, `AnalysisCancelled`, and cancellation token.
- Create the exact 13-role registry and stable actor/node/team mapping.
- Implement run, aggregate-role, turn, model-call, logical-tool, tool-execution, and vendor lifecycle validators.
- Freeze required payload identifiers and forward-compatible unknown-event behavior.

**Acceptance criteria**

- Exactly 13 unique actor IDs exist.
- Every legal and illegal state transition in the approved spec has a unit test.
- Event objects cannot be persisted without mandatory relationship identifiers.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_event_contracts.py tests/web/test_lifecycle.py'
```

## 5. Phase B — trustworthy persistence and serialization

### Story B1 — Implement redaction and canonical business hashing

**As a** local researcher  
**I want** durable audit data without secrets or ambiguous hashes  
**So that** history and resume are safe and deterministic.

**Points:** 5  
**Dependencies:** A3

**Files**

- Create `tradingagents/observability/redaction.py`
- Create `tradingagents/observability/canonical.py`
- Modify `tradingagents/agents/utils/agent_states.py`
- Create `tests/web/test_redaction.py`
- Create `tests/web/test_canonical_hashing.py`

**Tasks**

- Implement leaf-segment credential detection for nested and dotted keys.
- Implement `CanonicalBusinessValueV1`, `BusinessStateProjectionV1`, frozen delta/state hashes, schema hash, and unsupported-object failures.
- Add `_observation_commits` with a map-merge reducer while excluding it from prompts, reports, and business hashes.
- Cover LangChain messages, maps/sets, bytes, dates, non-finite floats, and internal graph channels.

**Acceptance criteria**

- Credentials redact before hashing/persistence; `max_tokens` and other semantic keys remain.
- Hashes are stable across mapping/set order.
- LangGraph control channels do not affect business-state hashes.
- A declared `AgentState` field change changes the schema fingerprint.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_redaction.py tests/web/test_canonical_hashing.py'
```

### Story B2 — Build the filesystem RunStore

**As a** local researcher  
**I want** every run and event to survive refresh/restart  
**So that** history is the same source of truth as live updates.

**Points:** 5  
**Dependencies:** A3, B1

**Files**

- Create `tradingagents/web/run_models.py`
- Create `tradingagents/web/store.py`
- Create `tests/web/test_run_store.py`

**Tasks**

- Implement safe run IDs/directories, atomic `run.json`, append-and-flush `events.jsonl`, sequence allocation, event reading, and run listing.
- Implement content-addressed artifacts for data, prompts, tool results, and reports.
- Reject run/artifact traversal and ticker-derived paths.
- Expose snapshot/latest-sequence operations under a per-run lock.

**Acceptance criteria**

- Sequences are strictly increasing and history is append-only.
- Events are durable before any publisher observes them.
- Repeated artifact content deduplicates.
- Restart can rebuild run summaries without a database.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_run_store.py'
```

### Story B3 — Add immutable partial and atomic final reports

**As a** local researcher  
**I want** partial work after failures and canonical reports after success  
**So that** useful analysis is never lost or prematurely called final.

**Points:** 3  
**Dependencies:** B1, B2

**Files**

- Create `tradingagents/web/reports.py`
- Extend `tests/test_reporting.py`
- Create `tests/web/test_report_artifacts.py`

**Tasks**

- Write immutable content-addressed report revisions.
- Publish the final report tree through a temporary sibling directory, verification, fsync, and atomic rename.
- Reuse `tradingagents/reporting.py:write_report_tree()` unchanged as content authority.

**Acceptance criteria**

- Partial revisions never overwrite one another.
- `run.completed` cannot precede canonical final-tree publication.
- Failed/cancelled runs retain partial artifacts without a false complete report.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_report_artifacts.py tests/test_reporting.py'
```

## 6. Phase C — observation and data provenance

### Story C1 — Implement observation context and callback capture

**As a** researcher auditing an agent  
**I want** prompts, attempts, tools, and failures joined to the correct turn  
**So that** the UI shows what actually happened.

**Points:** 5  
**Dependencies:** A3, B1, B2

**Files**

- Create `tradingagents/observability/context.py`
- Create `tradingagents/observability/observer.py`
- Create `tests/web/test_observer.py`

**Tasks**

- Implement `ObservationContext` `ContextVar`, `RoleTurnRef`, durable observer, callback hooks, direct-call scopes, and open-turn/tool reconstruction.
- Persist state/prompt snapshots and large-body artifact references.
- Attribute retries/fallback attempts without inventing new debate turns.
- Assert unattributed callbacks in development and diagnose safely in production.

**Acceptance criteria**

- Model prompts and usage join by turn/attempt/model-call IDs.
- Tool results join by model-provided `tool_call_id`, never callback order.
- Direct calls can enter the same correlation chain.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_observer.py'
```

### Story C2 — Add all role projections and observed graph tasks

**As a** researcher auditing role input  
**I want** exact per-role state/config projections  
**So that** unrelated accumulated state is not misrepresented as input.

**Points:** 8  
**Dependencies:** B1, C1

**Files**

- Create `tradingagents/observability/projections.py`
- Create `tradingagents/observability/graph_tasks.py`
- Modify `tradingagents/graph/setup.py`
- Modify `tradingagents/graph/propagation.py`
- Create `tests/web/test_role_projections.py`
- Create `tests/web/test_graph_observation.py`

**Tasks**

- Implement all 13 `(state, run_context)` projection functions and `EvidenceConfigSnapshotV1`.
- Wrap initial input, every role, every role-specific `ToolNode`, and every `Msg Clear` mutation.
- Emit one `graph.task_output_ready` candidate/token for every successful state mutation.
- Reuse a logical turn across model-tool-model re-entry; allocate new turns for later debate/risk rounds.

**Acceptance criteria**

- Each executed role has one truthful node-entry snapshot and actual formatted model input.
- Unselected roles are skipped without fabricated input.
- Multi-tool execution joins solely by task/tool-call IDs.
- Evidence configuration drift fails before Evidence Steward evaluates.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_role_projections.py tests/web/test_graph_observation.py'
```

### Story C3 — Instrument vendor provenance and run-scoped news cache

**As a** researcher checking financial data  
**I want** raw/normalized values and every vendor fallback  
**So that** I can verify company profiles, statements, indicators, and news accuracy.

**Points:** 5  
**Dependencies:** C1

**Files**

- Create `tradingagents/observability/provenance.py`
- Modify `tradingagents/dataflows/progress.py`
- Modify `tradingagents/dataflows/interface.py`
- Modify `tradingagents/agents/analysts/sentiment_analyst.py`
- Modify `tradingagents/agents/evidence_steward.py`
- Modify `tradingagents/dataflows/evidence.py`
- Modify `tradingagents/dataflows/news_advisor.py`
- Modify `tradingagents/dataflows/consistency.py`
- Extend `tests/test_news_cache.py`
- Extend `tests/test_dataflow_progress.py`
- Create `tests/web/test_data_provenance.py`

**Tasks**

- Preserve the existing four progress fields while adding optional correlation IDs.
- Record vendor request, attempt, duration, error, raw artifact, normalized artifact, period/unit/currency, and fallback chain.
- Namespace news cache by run and make cache hits reference origin vendor/artifact IDs.
- Instrument direct Sentiment and Evidence advisor/enrichment paths.

**Acceptance criteria**

- Same-run cache hits are source-linked and cross-run cache leakage is impossible.
- Direct and tool-mediated data share one provenance model.
- Existing CLI progress text remains compatible.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/test_news_cache.py tests/test_dataflow_progress.py tests/web/test_data_provenance.py'
```

## 7. Phase D — shared execution and checkpoint correctness

### Story D1 — Extract the shared AnalysisRunner

**As a** CLI, web, or programmatic caller  
**I want** one authoritative graph execution path  
**So that** behavior and side effects cannot diverge.

**Points:** 8  
**Dependencies:** C1, C2, C3

**Files**

- Create `tradingagents/execution/runner.py`
- Modify `tradingagents/graph/trading_graph.py`
- Modify `tradingagents/graph/propagation.py`
- Create `tests/web/test_analysis_runner.py`

**Tasks**

- Move state construction, identity/past-context resolution, streaming/delta merge, checkpoint lifecycle, final-state logging, memory writes, and signal processing into `AnalysisRunner`.
- Return successful `AnalysisResult` only.
- Raise `AnalysisCancelled` only for cooperative web cancellation and preserve original failures.
- Make `propagate()` a thin compatibility tuple adapter; keep report writing outside the runner.

**Acceptance criteria**

- CLI/web/programmatic callers share the same execution semantics.
- Existing success/failure/memory/checkpoint behavior remains covered by A1.
- Cancellation checks occur only at safe graph boundaries.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_analysis_runner.py tests/test_analysis_runner_compat.py tests/test_memory_log.py'
```

### Story D2 — Implement the resume fingerprint and full checkpoint access

**As a** local operator resuming an interrupted run  
**I want** strict semantic compatibility checks  
**So that** a checkpoint never mixes models, config, code, dependencies, or state schema.

**Points:** 5  
**Dependencies:** A2, B1

**Files**

- Create `tradingagents/web/fingerprint.py`
- Modify `tradingagents/graph/checkpointer.py`
- Create `tests/web/test_fingerprint.py`
- Extend `tests/test_checkpoint_resume.py`

**Tasks**

- Implement canonical effective-config, endpoint, source, Python, dependency-closure, event/serializer/projection, initial-context, and `AgentState` schema fingerprints.
- Exclude only the four location keys and credential leaves.
- Namespace web checkpoint threads by `run_id` while preserving legacy helpers.
- Expose latest/parent `CheckpointTuple` and `pending_writes`.

**Acceptance criteria**

- Any semantic/runtime drift returns a safe incompatibility response.
- Secrets are neither hashed nor compared.
- Existing graph-shape signatures remain a lower-level guard.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_fingerprint.py tests/test_checkpoint_resume.py'
```

### Story D3 — Implement the durable checkpoint frontier

**As a** local operator recovering from a crash  
**I want** candidate calls classified against durable graph state  
**So that** nothing uncommitted is accepted and no pending write is needlessly repeated.

**Points:** 8  
**Dependencies:** B2, C2, D1, D2

**Files**

- Create `tradingagents/web/reconciliation.py`
- Extend `tradingagents/execution/runner.py`
- Create `tests/web/test_checkpoint_frontier.py`
- Create `tests/web/test_crash_recovery.py`

**Tasks**

- Stream tasks/updates/checkpoints with sync durability for checkpoint-enabled web runs.
- Promote state, tools, turns, roles, and reports only after the checkpoint barrier.
- Classify DB-ahead/event-ahead tasks as committed, pending-apply, abandoned, or barrier-only using commit-token map differences and declared application channels.
- Add crash injection at every persistence boundary for input, role, multi-tool, and `Msg Clear` tasks.

**Acceptance criteria**

- JSONL is never rewritten during recovery.
- Uncommitted work remains visible but never becomes accepted debate/report state.
- Durable pending work is applied without re-execution.
- Tokenless barriers are valid only when declared application state is unchanged.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_checkpoint_frontier.py tests/web/test_crash_recovery.py --maxfail=1'
```

## 8. Phase E — local service boundary

### Story E1 — Implement atomic EventBroker and SSE handoff

**As a** browser client  
**I want** replay to transition into live delivery without a gap  
**So that** refresh and reconnect never lose or duplicate events.

**Points:** 5  
**Dependencies:** B2

**Files**

- Create `tradingagents/web/broker.py`
- Create `tests/web/test_event_broker.py`

**Tasks**

- Implement per-run persist/publish locking, watermark replay, bounded subscriber deque, loop-thread delivery, slow-consumer wake/close, keepalive, and cleanup.

**Acceptance criteria**

- Subscribe/replay/live is atomic under concurrent publication.
- Overflow disconnects only the slow subscriber and disk replay recovers it.
- Browser disconnect never cancels a run.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_event_broker.py'
```

### Story E2 — Implement SingleRunManager

**As a** single local user  
**I want** exactly one controlled background run  
**So that** process-global config/progress/cache state cannot mix analyses.

**Points:** 5  
**Dependencies:** B3, C3, D1, D2, D3, E1

**Files**

- Create `tradingagents/web/manager.py`
- Create `tests/web/test_single_run_manager.py`

**Tasks**

- Implement start/cancel/retry/resume/startup recovery and worker cleanup.
- Install/restore dataflow config, progress sink, observer, and run cache namespace in `try/finally`.
- Reject a second run atomically and terminalize every lifecycle on cancel/failure/interruption.

**Acceptance criteria**

- A second active submission receives one deterministic conflict.
- Startup reconciliation precedes `run.interrupted`.
- Retry creates a new run; resume continues only the same compatible interrupted run.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_single_run_manager.py'
```

### Story E3 — Add FastAPI REST, SSE, artifacts, and SPA serving

**As a** browser workbench  
**I want** a safe localhost API  
**So that** commands, history, events, and artifacts have one boundary.

**Points:** 5  
**Dependencies:** A2, B2, E1, E2

**Files**

- Create `tradingagents/web/schemas.py`
- Create `tradingagents/web/api.py`
- Create `tests/web/test_api.py`
- Create `tests/web/test_sse.py`

**Tasks**

- Implement `/api/config`, run list/create/read/cancel/retry/resume, event stream, artifact list/read, CSP, static assets, and SPA fallback.
- Honor `after`/`Last-Event-ID`, terminal stream closure, safe mismatch fields, and lazy artifact reads.
- Ensure `/api/*` never falls through to the SPA.

**Acceptance criteria**

- Requests validate ticker/date/analysts/provider/model/language before worker creation.
- Every response is secret-free and run/artifact scoped.
- Live and historical events use the same persisted envelope.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_api.py tests/web/test_sse.py'
```

### Story E4 — Add `tradingagents web` and migrate CLI rendering

**As a** local operator  
**I want** terminal launch and unchanged analysis CLI behavior  
**So that** web is additive rather than a replacement.

**Points:** 5  
**Dependencies:** A1, D1, E3

**Files**

- Create `tradingagents/web/cli.py`
- Create `cli/run_observer.py`
- Modify `cli/main.py`
- Optionally extend `cli/stats_handler.py` without duplicating runner statistics
- Create `tests/web/test_web_cli.py`
- Create `tests/test_cli_runner_compatibility.py`

**Tasks**

- Add lazy `web --port --open` with hardcoded `127.0.0.1` and no host flag.
- Run capability preflight before Uvicorn and print the URL.
- Replace CLI direct graph streaming with runner events mapped into the existing `MessageBuffer`/report display.

**Acceptance criteria**

- `tradingagents web` starts only on loopback.
- Existing CLI config, statuses, save/display behavior, exits, and exceptions remain compatible.
- Missing web dependencies yield the exact install command.

**Verify**

```bash
rtk zsh -lic 'python -m pytest -q tests/web/test_web_cli.py tests/test_cli_runner_compatibility.py tests/test_cli_config.py tests/test_cli_symbol_handling.py'
```

## 9. Phase F — React workbench foundations

### Story F1 — Scaffold React/Vite and Python asset packaging

**As a** packaged local user  
**I want** the UI included with Python  
**So that** Node is unnecessary at runtime.

**Points:** 3  
**Dependencies:** A2

**Files**

- Create `frontend/package.json`, `frontend/package-lock.json`
- Create `frontend/index.html`
- Create `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`
- Create `frontend/vite.config.ts`, `frontend/vitest.config.ts`, `frontend/playwright.config.ts`
- Create `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Create `frontend/src/styles/tokens.css`, `global.css`, `workbench.css`
- Create compiled output directory `tradingagents/web/static/`
- Modify `pyproject.toml` package data
- Create `tests/web/test_package_assets.py`

**Tasks**

- Configure Vite output directly to tracked Python static assets with hashed bundles.
- Resolve packaged assets through `importlib.resources`.
- Port approved V2 visual tokens, not its mock data.

**Acceptance criteria**

- A built wheel contains `index.html` and all hashed assets.
- The installed server renders without Node.
- Rebuilding produces no uncommitted asset drift.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend ci && npm --prefix frontend run build'
rtk zsh -lic 'python -m pytest -q tests/web/test_package_assets.py'
```

### Story F2 — Implement typed API client and shared event reducer

**As a** live or history viewer  
**I want** identical state reconstruction  
**So that** replay and live pages cannot disagree.

**Points:** 8  
**Dependencies:** A3, F1

**Files**

- Create `frontend/src/api/contracts.ts`, `schema.ts`, `client.ts`, `eventSource.ts`
- Create `frontend/src/state/model.ts`, `runReducer.ts`, `selectors.ts`, `WorkbenchStore.tsx`
- Create `frontend/src/hooks/useRunStream.ts`

**Tasks**

- Model normalized roles, turns, messages, tasks, attempts, logical tools, executions, vendors, artifacts, reports, and diagnostics.
- Keep UI selection/filters outside persisted run state.
- Implement sequence dedupe/gap diagnostics/reconnect and frontier-derived application status.
- Ignore unknown event types and diagnose invalid transitions without corrupting accepted state.

**Acceptance criteria**

- Batch replay and one-by-one live reduction produce deep-equal state.
- Per-run state is isolated by `run_id`.
- Candidate/pending/committed/abandoned states are derivable without UI inference.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run runReducer'
```

### Story F3 — Build controls, key status, and run history

**As a** local researcher  
**I want** to start, control, and revisit analyses  
**So that** the browser is the complete local workflow.

**Points:** 5  
**Dependencies:** E3, F2

**Files**

- Create layout/control/history components under `frontend/src/components/layout/`, `controls/`, and `history/`
- Create `frontend/src/hooks/useConfig.ts`, `useRunHistory.ts`

**Tasks**

- Implement ticker/date, analyst selection, depth, provider/models, language, checkpoint, key status, start/cancel/retry/resume, and history selection.
- Treat `/api/config` as authority for wire keys including `social` compatibility.

**Acceptance criteria**

- Validation and 409 conflicts render truthfully.
- Browser state never contains key values.
- Retry selects a new run; resume continues the same sequence.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run test -- --run RunHistory RunControls'
```

## 10. Phase G — visual workflow and audit experience

### Story G1 — Implement the 13-role workflow and icon registry

**As a** researcher watching the workflow  
**I want** every role to be visually distinct  
**So that** the debate structure is immediately understandable.

**Points:** 5  
**Dependencies:** F2

**Files**

- Create `frontend/src/domain/roles.ts`
- Create `frontend/src/components/icons/RoleIcon.tsx`, `roleIconPaths.ts`
- Create workflow components under `frontend/src/components/workflow/`

**Tasks**

- Implement exactly 13 stable actor IDs and 13 distinct inline SVG definitions.
- Render all roles grouped by stage with aggregate status/current round.
- Render skipped/not-reached/interrupted/cancelled truthfully.

**Acceptance criteria**

- Registry cardinality and icon-path uniqueness tests equal 13.
- Repeated turns update the aggregate card without destroying turn history.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run test -- --run roles WorkflowMap'
```

### Story G2 — Implement debate and verdict timeline

**As a** researcher following the debate  
**I want** each immutable turn and decision visible  
**So that** I can understand how the final judgment developed.

**Points:** 5  
**Dependencies:** G1

**Files**

- Create timeline components under `frontend/src/components/timeline/`
- Create `frontend/src/components/shared/ApplicationStatusBadge.tsx`

**Tasks**

- Render one item per `turn_id` with team/role filters.
- Use current response, never cumulative history, for each timeline entry.
- Highlight manager/portfolio verdicts and separate candidate/abandoned output.

**Acceptance criteria**

- Later Bull/Bear/risk rounds neither overwrite nor duplicate earlier rounds.
- Uncommitted output is never styled as an accepted verdict.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run test -- --run Timeline'
```

### Story G3 — Implement role input, data/tool, configuration, and artifact inspector

**As a** researcher verifying source accuracy  
**I want** exact inputs, prompts, raw values, tools, and artifacts  
**So that** I can audit company profiles, statements, indicators, and evidence.

**Points:** 8  
**Dependencies:** C2, C3, F2, G1

**Files**

- Create inspector components under `frontend/src/components/inspector/`
- Create tool/data components under `frontend/src/components/tools/`
- Create artifact components under `frontend/src/components/artifacts/`
- Create `frontend/src/components/run-input/RunInputPanel.tsx`
- Create `frontend/src/hooks/useArtifact.ts`

**Tasks**

- Implement five audit views: normalized data, upstream material, prompt, raw values, and configuration.
- Implement turn selection, logical tool/execution/vendor fallback cards, durations/errors, and application status.
- Lazy-load and cache artifacts by `run_id + artifact_id`.
- Render Markdown with `react-markdown`, GFM, strict sanitize, and no raw HTML.

**Acceptance criteria**

- Fundamentals exposes company profile and all three statements with periods/units/vendors/raw/normalized/hash data.
- Market exposes price/indicator/verified snapshot data.
- Bull/Bear/risk roles expose actual upstream/opponent input.
- Skipped roles explain that no captured input exists.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run test -- --run RoleInputPanel ToolCallCard SafeMarkdown'
```

### Story G4 — Complete frontend unit coverage

**As a** maintainer  
**I want** deterministic reducer/component tests  
**So that** UI state remains truthful during later changes.

**Points:** 5  
**Dependencies:** F2, F3, G1, G2, G3

**Files**

- Create `frontend/src/test/setup.ts`, `fixtures.ts`, `FakeEventSource.ts`
- Add focused `*.test.ts(x)` files for roles, reducer, selectors, workflow, timeline, inspector, tools, Markdown, and history

**Acceptance criteria**

- Tests cover replay/live equivalence, dedupe, unknown/invalid events, every role status/icon, repeated turns, audit views, lazy artifacts, sanitization, and run isolation.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run'
```

## 11. Phase H — end-to-end proof and closeout

### Story H1 — Add deterministic FastAPI/Playwright end-to-end tests

**As a** maintainer  
**I want** browser tests against the production boundary  
**So that** REST, SSE, static assets, reducer, and UI are verified together.

**Points:** 8  
**Dependencies:** E3, F1, F2, F3, G1, G2, G3

**Files**

- Create `tests/web/e2e_app.py`
- Create deterministic fixtures under `tests/fixtures/web/`
- Create Playwright specs under `frontend/e2e/`

**Tasks**

- Inject a deterministic fake runner while retaining production app/store/SSE/static paths.
- Cover successful run, all 13 roles, role audits, tools/vendors, refresh/reconnect, failure/cancel/interruption history, retry/resume, and secret absence.

**Acceptance criteria**

- Refresh mid-run yields no missing/duplicate turns.
- Browser and persisted files contain no configured test secret.
- Wheel-served SPA and `/api/*` behavior match development behavior.

**Verify**

```bash
rtk zsh -lic 'npm --prefix frontend run build && npm --prefix frontend run test:e2e'
```

### Story H2 — Add package, CI, and documentation gates

**As a** local installer  
**I want** reproducible packaged assets and launch instructions  
**So that** `tradingagents web` works from a clean environment.

**Points:** 5  
**Dependencies:** E4, F1, G4, H1

**Files**

- Modify `.github/workflows/ci.yml`
- Modify `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/roadmap/CHANGELOG.md`
- Modify `Handoff.md`
- Modify `Dockerfile` only if package build evidence requires a frontend build stage

**Tasks**

- Add Python web tests, frontend typecheck/unit/build, committed-asset drift, Playwright, wheel asset, and CLI smoke gates.
- Document local installation, configuration, launch, history location, privacy boundary, and troubleshooting.

**Acceptance criteria**

- A clean wheel installs and serves the SPA without Node.
- Rebuilding the frontend leaves no diff.
- Existing CLI usage remains documented and tested.

**Verify**

```bash
rtk zsh -lic 'python -m build && python -m pytest -q'
rtk zsh -lic 'npm --prefix frontend ci && npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run && npm --prefix frontend run build && npm --prefix frontend run test:e2e'
rtk git diff --check
```

### Story H3 — Run one real minimum-depth analysis and completion audit

**As the** local researcher who requested the workbench  
**I want** one real stock analysis proven end to end  
**So that** the delivered UI is not merely a deterministic demo.

**Points:** 5  
**Dependencies:** all previous stories

**Files**

- Create `scripts/smoke_web.py`
- Update `Handoff.md` with exact evidence and artifact paths

**Tasks**

- Start the packaged server on loopback.
- Submit one explicit minimum-depth stock analysis using already configured provider/data credentials.
- Verify real graph, model/tool/vendor/role-input events, final reports, restart history, and secret scanning.
- Inspect the final page at a 1280-pixel desktop viewport and correct material visual/interaction defects.
- Audit every design acceptance criterion against code, tests, browser state, and persisted artifacts.

**Acceptance criteria**

- The real run completes and all participating role inputs are auditable.
- Company profile, balance sheet, cash flow, income statement, market data, and indicators expose source/period/unit/raw/normalized/hash evidence where returned.
- History and reports survive server restart.
- No configured secret exists in DOM, HTTP responses, JSONL, logs, prompts, or artifacts.
- `tradingagents web` is the proven terminal-to-browser path.

**Verify**

```bash
rtk zsh -lic 'python scripts/smoke_web.py --config tradingagents.local.json --ticker 600519.SS --allow-live-provider'
```

## 12. Baseline and final verification matrix

Run the focused legacy baseline before implementation and after phases D and E:

```bash
rtk zsh -lic 'python -m pytest -q tests/test_checkpoint_resume.py tests/test_reporting.py tests/test_cli_config.py tests/test_cli_config_precedence.py tests/test_dataflow_progress.py tests/test_news_cache.py tests/test_analyst_execution.py tests/test_safe_ticker_component.py'
```

Run after every backend phase:

```bash
rtk zsh -lic 'python -m pytest -q tests/web'
rtk zsh -lic 'ruff check tradingagents cli tests'
```

Run before completion:

```bash
rtk zsh -lic 'python -m pytest -q'
rtk zsh -lic 'ruff check .'
rtk zsh -lic 'npm --prefix frontend ci && npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run && npm --prefix frontend run build && npm --prefix frontend run test:e2e'
rtk zsh -lic 'python -m build'
rtk git diff --check
```

## 13. Known implementation risks

- `tests/conftest.py` injects placeholder API keys; web config tests need explicit clean-credential fixtures and isolated run roots.
- `tests/test_checkpoint_resume.py` assumes an exact legacy step and uses a module-global crash flag; retain legacy coverage but add full-tuple/pending-write fixtures using `tmp_path`.
- `tests/test_memory_log.py` mocks execution deeply; runner tests must cover real state/side-effect ordering.
- `tests/test_news_cache.py` directly clears a global dict; migrate tests to run namespaces without weakening cross-run isolation.
- Adding a second Typer command can change root dispatch; A1 and E4 must prove current command behavior.
- Current CLI partial-report decorators write directly; migrate only after runner compatibility tests are green.
- The active shell may not expose the project Python environment; establish the authoritative interpreter before running baseline commands rather than treating missing dependencies as product failures.

## 14. Definition of done

- Every story acceptance criterion is proven by its focused tests.
- Full Python, frontend, Playwright, package, and asset-drift gates pass.
- One real minimum-depth analysis passes the secret and restart audit.
- `README.md`, changelogs, and `Handoff.md` match actual behavior.
- The final completion audit proves every approved design acceptance criterion with current evidence.
