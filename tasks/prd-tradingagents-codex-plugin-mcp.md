# PRD: TradingAgents Codex Plugin and MCP Integration

Date: 2026-09-11

Status: PRD prepared with confirmed release scope; implementation has not started.

Architecture reference: [Codex plugin architecture](../docs/superpowers/specs/2026-09-11-codex-plugin-architecture.md).

## 1. Introduction / Overview

TradingAgents currently performs financial analysis through a Python/LangGraph workflow whose agents invoke configured language-model backends. Its existing model-client interface cannot directly use the user's authenticated Codex conversation. Merely wrapping the current graph in a plugin would continue making those backend calls.

Add a Codex plugin containing a workflow skill and a local Model Context Protocol (MCP) server. MCP exposes Python functions as tools Codex can call. The skill guides Codex through TradingAgents' analyst, research, trading, risk, portfolio, and reflection roles. Python remains responsible for evidence retrieval, calculations, stage progression, validation, persistence, and report generation.

The plugin path must perform all language-model reasoning inside the user's Codex session. It must not create an LLM API client or launch nested Codex/Claude processes. Existing API-backed CLI and Python workflows remain available.

Primary user: an existing TradingAgents user who wants to run its research workflow through Codex and their existing host access, without configuring separate LLM API credentials for that workflow.

### Confirmed scope

Confirmed by the conversation:

- Use the skill + MCP approach.
- Make the existing financial analysis capabilities available to Codex, including full workflow execution and individual data tools.
- Preserve reports, history, reflection, and restart/resume rather than shipping only a data-fetching wrapper.
- This task produces a PRD, not implementation code.

Confirmed through the user's answers to the three scope questions:

- First release: local Codex desktop and CLI; Claude Code integration is a later host milestone.
- Execution: roles run sequentially in one Codex conversation. This does not isolate each role from earlier conversation context.
- Distribution: personal local installation with documented Python setup. Public marketplace submission is separate work.

Requirements below describe this initial release. Changing these choices requires updating the affected stories before implementation.

## 2. Goals

1. Complete a real, installed-plugin analysis in Codex with all selected stages and no LLM API credentials configured for the Python runtime.
2. Expose all twelve existing public financial tools, instrument identity, Reddit, StockTwits, and decision-history reads through discoverable, typed MCP tools.
3. Preserve analyst selection, stock/crypto handling, vendor selection, debate depth, output language, structured decisions, reports, memory, and outcome reflection.
4. Resume an interrupted run from its pending stage without regenerating accepted outputs or silently replacing saved evidence.
5. Reject invalid or stale stage submissions and prevent duplicate stage advancement, decisions, and reflections after retries.
6. Preserve existing API-runner behavior through shared role logic and existing regression checks.

## 3. User Stories

Each story includes focused automated checks and repository lint. There is no new browser UI. Host installation is verified in Codex itself. The repository currently uses pytest and Ruff rather than a configured static type-checking gate.

### US-001: Start the local MCP runtime

**Description:** As a local user, I want an installable server executable so Codex can access TradingAgents outside the source checkout.

**Acceptance Criteria:**
- [ ] An optional `plugin` dependency group installs the MCP runtime; the base package remains installable without it.
- [ ] `tradingagents-mcp` starts a local stdio server using the installed package from a working directory outside the repository.
- [ ] MCP initialization and tool discovery succeed in a clean environment with no LLM API keys.
- [ ] Logs go to stderr; stdout contains only MCP protocol messages.
- [ ] Startup fails with an actionable message when its configured state directory is unwritable.
- [ ] Clean-install/protocol tests and `ruff check .` pass.

### US-002: Discover capabilities and setup requirements

**Description:** As a user, I want to see supported features and missing data credentials so I can configure the plugin before analysis.

**Acceptance Criteria:**
- [ ] `get_capabilities` returns supported roles, data tools, analysis settings, and runtime/schema versions.
- [ ] Credential checks expose presence/absence only, never credential values.
- [ ] Missing optional data credentials do not prevent tool discovery or use of unrelated sources.
- [ ] LLM API settings are identified as belonging to the existing API runner, not the Codex plugin path.
- [ ] Capability and missing-credential tests and `ruff check .` pass.

### US-003: Share analyst prompts with the API runner

**Description:** As a maintainer, I want shared analyst prompt builders so fixes to evidence handling apply to both execution paths.

**Acceptance Criteria:**
- [ ] Market, sentiment, news, and fundamentals prompts can be prepared without constructing a model client.
- [ ] Existing API factories and the plugin use the same prompt-building functions.
- [ ] Instrument identity, analysis date, crypto context, output language, and missing-data instructions are preserved.
- [ ] Sentiment prompt preparation accepts recorded news, StockTwits, and Reddit blocks without independently refetching them.
- [ ] Existing analyst prompt/crypto/language tests, focused shared-prompt checks, and `ruff check .` pass.

### US-004: Share synthesis and reflection role logic

**Description:** As a maintainer, I want shared synthesis prompts and output updates so the plugin preserves the existing analysis procedure.

**Acceptance Criteria:**
- [ ] Bull, bear, research manager, trader, three risk roles, portfolio manager, and reflection prompts are callable without a model client.
- [ ] Existing factories reuse the extracted functions for prompt preparation and accepted-output state updates.
- [ ] Each role receives the same domain fields as its existing counterpart; the trader retains technical-price grounding and the portfolio manager receives eligible lessons.
- [ ] Existing API structured-output fallback behavior remains intact.
- [ ] Debate-opening, structured-agent, reflection-related checks and `ruff check .` pass.

### US-005: Retrieve market and fundamental evidence

**Description:** As a user, I want to request prices, indicators, verified snapshots, and company statements directly from Codex.

**Acceptance Criteria:**
- [ ] Named MCP tools expose `get_stock_data`, `get_indicators`, `get_verified_market_snapshot`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`.
- [ ] An instrument-identity tool exposes existing symbol normalization and identity resolution.
- [ ] Wrappers reuse existing implementations and preserve source warnings, unavailable-data results, and vendor selection rules.
- [ ] Typed arguments are discoverable; arbitrary function names, Python code, and filesystem destinations are not accepted.
- [ ] Tests cover exchange suffixes, a supported alias, crypto context, and unavailable market data; `ruff check .` passes.

### US-006: Retrieve news, sentiment, macro, and event evidence

**Description:** As a user, I want the full range of existing contextual evidence so the plugin does not omit sources used by the current analysts.

**Acceptance Criteria:**
- [ ] Named MCP tools expose ticker news, global news, insider transactions, macro indicators, prediction markets, StockTwits messages, and Reddit posts.
- [ ] Existing date-window filtering and vendor fallback semantics remain in effect.
- [ ] Missing FRED credentials and unavailable social sources return the existing failure/unavailable meaning without fabricated replacements.
- [ ] No wrapper invokes an LLM to summarize, repair, or replace failed source data.
- [ ] Fake-vendor protocol tests and existing relevant source tests pass; `ruff check .` passes.

### US-007: Create a configured analysis

**Description:** As a user, I want to start an analysis with explicit choices so the run matches my requested instrument and depth.

**Acceptance Criteria:**
- [ ] `start_analysis` accepts ticker, date, asset type, selected analysts, research/risk round counts, language, vendor overrides, and a request identifier.
- [ ] Defaults are all four analysts, one research round, one risk round, and English; an absent date resolves to the host's local calendar date and is echoed.
- [ ] Analyst keys are `market`, `social`, `news`, and `fundamentals`; `social` is presented as Sentiment Analyst. Default order follows existing analyst metadata; an explicit ordered selection is preserved.
- [ ] Invalid dates, reversed windows, unknown/duplicate analysts, empty selections, unsupported settings, and nonpositive round counts fail before run creation.
- [ ] The run freezes configuration, instrument context, and eligible past lessons and returns its UUID, revision, and first stage.
- [ ] The same request identifier and normalized inputs return the same run; changed inputs return a conflict.
- [ ] Creation/validation/retry tests and `ruff check .` pass.

### US-008: Record evidence against the correct run

**Description:** As a user, I want evidence tied to my analysis so another run's settings or newer data cannot silently alter it.

**Acceptance Criteria:**
- [ ] Data tools accept an optional run identifier; standalone calls do not create or advance workflow stages.
- [ ] Run-bound calls use frozen configuration and validate ticker, date boundaries, active-stage tool permissions, and run status.
- [ ] Recorded evidence includes arguments, fetch time, requested window, content, available source metadata, and warnings; unknown vendor identity is marked unknown.
- [ ] Identical run/stage requests reuse saved evidence by default. Status reads never trigger fresh network fetches.
- [ ] Large evidence is retrievable in bounded pages with explicit continuation; omitted content is never silently presented as complete.
- [ ] Concurrent configurations cannot leak; configuration is fully restored after both successful and failing fetches.
- [ ] Evidence/configuration isolation tests and `ruff check .` pass.

### US-009: Complete analyst stages

**Description:** As a user, I want Codex to produce the selected analyst reports from recorded evidence before the research debate begins.

**Acceptance Criteria:**
- [ ] `get_analysis` returns the active role, instructions, required evidence, output schema, relevant context, and revision.
- [ ] Market completion requires a recorded verified-snapshot attempt for the correct ticker/date.
- [ ] Sentiment completion requires recorded news, StockTwits, and Reddit attempts for its existing seven-day lookback window.
- [ ] An unavailable-data result satisfies an attempt requirement; a transport error leaves collection retryable and is not disguised as no data.
- [ ] Sentiment submissions validate against `SentimentReport`; remaining analyst submissions require nonempty text.
- [ ] Submission validation returns field-level errors without advancing the stage.
- [ ] Selected/skipped analyst and missing-evidence tests and `ruff check .` pass.

### US-010: Conduct research debate and create the investment plan

**Description:** As a user, I want bullish and bearish arguments considered before Codex chooses an investment stance.

**Acceptance Criteria:**
- [ ] Every research round contains one bull contribution followed by one bear contribution, with exactly the configured number of rounds.
- [ ] Opening prompts identify an absent opponent response rather than inventing one.
- [ ] Debate history and role prefixes are stored by Python, not supplied as authoritative counters by Codex.
- [ ] The research manager follows the final debate round and submits a valid `ResearchPlan`.
- [ ] Recommendations use the existing five-tier rating enum and renderer.
- [ ] One-round/multiple-round/order tests and `ruff check .` pass.

### US-011: Produce the trader proposal and risk debate

**Description:** As a user, I want a grounded trade proposal examined from three risk perspectives before a final decision.

**Acceptance Criteria:**
- [ ] The trader receives the research plan and selected market report and submits a valid `TraderProposal`.
- [ ] Action is Buy, Hold, or Sell; optional entry and stop-loss fields follow existing numeric schema rules.
- [ ] Each risk round runs aggressive, conservative, then neutral, for exactly the configured round count.
- [ ] Risk prompts include the proposal, analyst reports, and relevant debate history through shared builders.
- [ ] Invalid trader output and out-of-order risk submissions leave the current stage unchanged.
- [ ] Trader/schema/risk-order tests and `ruff check .` pass.

### US-012: Submit the portfolio decision

**Description:** As a user, I want a validated final decision that preserves TradingAgents' existing reporting format.

**Acceptance Criteria:**
- [ ] Portfolio synthesis starts only after all required risk contributions are accepted.
- [ ] Its prompt includes plans, risk history, instrument context, and eligible prior lessons.
- [ ] Output validates against `PortfolioDecision` and renders through the existing renderer.
- [ ] A valid decision moves the run to `ready_to_finalize`; it does not claim reports or memory have already been exported.
- [ ] No extra model call extracts the rating; unparseable legacy text remains `REVIEW` rather than silently becoming Hold.
- [ ] Final-decision/state/rating tests and `ruff check .` pass.

### US-013: Resume, inspect, and cancel a run

**Description:** As a user, I want to recover an interrupted analysis or stop it without losing accepted work.

**Acceptance Criteria:**
- [ ] `list_analyses` supports ticker/status filters and pagination; `get_analysis` retrieves a chosen run and saved sections.
- [ ] After server restart, the pending stage, accepted outputs, evidence, and frozen configuration are unchanged.
- [ ] `submit_stage` requires stage ID and expected revision. Identical accepted retries return their receipt; stale or conflicting submissions cannot overwrite results.
- [ ] `cancel_analysis` retains data and prevents further submissions; restarting a cancelled analysis requires a new run.
- [ ] Unsupported saved-state versions return a compatibility error without deleting or silently resetting data.
- [ ] Restart, duplicate, stale, cancellation, and two-writer tests pass; `ruff check .` passes.

### US-014: Export reports and decision history safely

**Description:** As a user, I want saved reports and history entries that remain correct when finalization is retried.

**Acceptance Criteria:**
- [ ] `finalize_analysis` writes the existing per-section report tree and consolidated report into a run-owned directory and returns paths and rating.
- [ ] It exports one decision using a stable identity and marks the run completed only after exports succeed.
- [ ] A failure after memory write but before completion can be retried without duplicate decisions.
- [ ] Concurrent writes preserve both plugin and existing-runner history; legacy memory entries remain readable.
- [ ] A read-only history tool supports ticker and as-of filtering without exposing arbitrary local files.
- [ ] Export fault-injection, concurrent-memory, legacy-memory, and reporting tests pass; `ruff check .` passes.

### US-015: Prepare historical outcomes for reflection

**Description:** As a user, I want measured outcomes attached to past decisions so reflections use real results.

**Acceptance Criteria:**
- [ ] `prepare_reflections` finds same-ticker pending decisions and reuses shared return/benchmark calculation code.
- [ ] A job is prepared only when the full required holding window is available and its resolution date is no later than the requested as-of date.
- [ ] Raw return, benchmark-relative return, holding period, benchmark identity, and resolution date are stored with the job.
- [ ] Too-recent or unavailable outcomes leave the decision pending; repeated preparation reuses the existing decision/outcome job.
- [ ] Outcome-window, benchmark, historical-cutoff, and duplicate-preparation tests pass; `ruff check .` passes.

### US-016: Save and reuse Codex-authored reflections

**Description:** As a user, I want Codex to review past decisions and carry eligible lessons into later analysis.

**Acceptance Criteria:**
- [ ] Reflection jobs use the same read/submit/finalize lifecycle and the existing concise reflection prompt.
- [ ] Codex supplies the reflection; the Python runtime never invokes `Reflector` with an API model.
- [ ] Finalization updates the intended decision with outcome fields and reflection exactly once, including for supported legacy entries.
- [ ] The skill completes eligible same-ticker reflection jobs before starting a new analysis, unless the user explicitly requests analysis without that learning step; such a run records the omission.
- [ ] New historical runs include only lessons resolved by their analysis date.
- [ ] Reflection lifecycle/retry/historical-memory tests and `ruff check .` pass.

### US-017: Guide the entire workflow through a skill

**Description:** As a user, I want to request an analysis in ordinary language without manually operating each MCP stage.

**Acceptance Criteria:**
- [ ] The bundled `trading-analysis` skill recognizes full analysis, resume, standalone data, history, and reflection requests.
- [ ] It follows returned stage instructions and schemas, submits each role separately, and reports final artifact links.
- [ ] It does not duplicate financial prompts, invent successful tool results, call the existing API runner, or launch nested agent processes.
- [ ] It treats source content as evidence rather than instructions and uses saved evidence after interruptions.
- [ ] It repairs field-validation errors using the returned schema; unresolved source/runtime errors are surfaced with the pending run identifier.
- [ ] Documentation clearly describes sequential roles without claiming independent context isolation.
- [ ] Skill validation, scripted workflow acceptance checks, and `ruff check .` pass for associated code.

### US-018: Install the plugin and verify the complete product

**Description:** As a user, I want a documented installation that enables a complete subscription-hosted analysis in Codex.

**Acceptance Criteria:**
- [ ] The package includes a valid Codex manifest, local MCP launch configuration, skill, and setup instructions.
- [ ] Instructions cover a version-pinned Python environment, executable path, data credentials, writable state roots, plugin activation, and verification in a new session.
- [ ] The instructions do not imply that installing a manifest automatically installs Python dependencies or provides unlimited subscription usage.
- [ ] A clean-environment protocol smoke test runs outside the repository on supported Python versions, alongside base-package installation tests.
- [ ] A manual Codex desktop/CLI acceptance checklist verifies discovery, standalone data, complete analysis, saved artifacts, and recovery from interruption.
- [ ] A real installed Codex run completes with LLM API credentials absent from the Python runtime; fixture-based tests fail immediately if the LLM-client factory is called.
- [ ] Existing CI, added plugin checks, `ruff check .`, and plugin/skill validators pass; live host validation records its date, host version, and result.

## 4. Functional Requirements

### Host integration and compatibility

- **FR-1:** The plugin must bundle a workflow skill and local stdio MCP integration. The server must expose a capability-discovery operation.
- **FR-2:** Plugin operations must not construct LLM clients, call paid LLM APIs, read host authentication tokens, or launch nested coding-agent processes. Codex performs reasoning in its current session.
- **FR-3:** The existing API CLI and programmatic runner must retain supported providers, model settings, structured fallbacks, and LangGraph checkpoint behavior.
- **FR-4:** Financial prompts, schema renderers, rating extraction, and state-update logic must be shared where both paths require them; the skill must not maintain a parallel copy of those prompts.

### Data and configuration

- **FR-5:** MCP must expose twelve existing financial tools, instrument identity, Reddit, StockTwits, and decision-history reads as named typed operations.
- **FR-6:** A standalone evidence request must work without starting an analysis. A run-bound request must enforce the active role's permitted tools and frozen ticker/date/settings.
- **FR-7:** Runs must support stock and crypto context, selected analysts, ordered vendor overrides, output language, and research/risk round counts. Unsupported API-model settings must return an explanatory error.
- **FR-8:** The server must validate real dates, ordered windows, supported enum values, unique/nonempty analyst selection, positive rounds, ticker syntax, identifiers, and payload bounds before accepting inputs.
- **FR-9:** Run configuration must not leak across calls. Startup-controlled storage paths and credentials must not be accepted as arbitrary model-supplied overrides.
- **FR-10:** Evidence must retain content, tool arguments, request window, fetch time, known source identity, and warnings. Historical source limitations must remain visible.
- **FR-11:** Repeated evidence reads must use saved content by default. Oversized results must return explicit continuation rather than silent truncation.
- **FR-12:** Missing optional sources must retain their existing unavailable semantics. Network/authentication errors must not be presented as verified absence of data.

### Analysis and validation

- **FR-13:** Python must enforce selected analysts -> bull/bear debate -> research manager -> trader -> three-role risk debate -> portfolio manager -> finalization.
- **FR-14:** Research depth N means exactly 2N contributions; risk depth R means exactly 3R contributions. Python owns counters and stage identities.
- **FR-15:** Stage reads must return role instructions, relevant saved context, required evidence, output schema, and revision.
- **FR-16:** Market and sentiment evidence requirements must be checked before accepting those reports. Recorded unavailable results may satisfy attempted retrieval, with warnings preserved.
- **FR-17:** Sentiment, research manager, trader, and portfolio submissions must use existing Pydantic schemas; other report stages require nonempty text. Invalid output cannot advance the run.
- **FR-18:** Existing numeric price-field semantics and five-tier portfolio ratings must be retained. Schema validation must not be represented as proof of narrative truth.

### State, exports, and learning

- **FR-19:** Runs must persist a stable identifier, configuration, versions, revision, accepted outputs, evidence, pending stage, and status outside the plugin installation cache.
- **FR-20:** Start requests and stage submissions must be retry-safe. Conflicting retries and stale writers cannot overwrite accepted work.
- **FR-21:** Users must be able to list, inspect, resume active runs, and cancel unfinished runs. Cancelled data remains readable; completed/cancelled runs reject new stage submissions.
- **FR-22:** Incompatible saved-state versions must fail explicitly without destructive resets. Changed run settings require a new run.
- **FR-23:** Finalization must reuse report rendering and return durable artifact paths. A completed status requires successful report and memory exports.
- **FR-24:** Decision and reflection exports must remain duplicate-free after crashes and retries, and shared memory writes must preserve concurrent writers and old entries.
- **FR-25:** Reflection preparation must reuse measured returns and benchmark resolution, wait for the full outcome window, and honor the requested as-of cutoff.
- **FR-26:** Reflection generation must occur in Codex; finalized lessons must be readable by subsequent analyses without leaking outcomes resolved after a historical analysis date.
- **FR-27:** The skill must guide the complete lifecycle and identify unresolved errors with a recoverable run ID, without claiming partial execution is complete.

### Installation and transparency

- **FR-28:** Setup must work outside the repository, describe dependency provisioning explicitly, and keep protocol stdout free of logs.
- **FR-29:** Model availability and subscription consumption remain host-controlled. Missing host token/cost data must be reported as unavailable, never estimated as an API bill.
- **FR-30:** Initial documentation must disclose that sequential roles share conversation context and that financial conclusions need not match the API runner.

## 5. Non-Goals / Out of Scope

- Broker connectivity, order placement, portfolio custody, and new trading strategies.
- A new dashboard, browser UI, hosted multi-user server, or public marketplace submission in the initial release.
- Using Codex/Claude subscription tokens as generic API keys or building an authentication proxy.
- Replacing the existing API execution path or removing its provider configuration.
- Converting LangGraph checkpoints into plugin runs.
- Guaranteeing identical decisions, profitability, independent role contexts, or historical data coverage unavailable from the existing sources.
- Automatic schedules, background execution while Codex is closed, and independent multi-agent sessions.
- Claude Code packaging and end-to-end acceptance in the initial release; the MCP business interface should remain host-neutral.

## 6. Design Considerations

The primary interface is conversation. Example requests:

- “Analyze NVDA as of 2026-09-10 with all analysts and two debate rounds.”
- “Show the verified market snapshot for BTC-USD.”
- “Resume my latest unfinished NVDA analysis.”
- “Review the outcomes of my past AAPL decisions.”

Codex should state the resolved ticker/date/options, surface material data gaps, and provide stage progress and final report links. It should use defaults when the request is sufficiently clear. If “two debate rounds” does not specify research versus risk, the skill must state how it interpreted that choice before execution.

Stored instructions and outputs are stage-specific, but a single host conversation retains earlier context. This distinction must be visible in the README and must not be described as an isolated ensemble.

Use existing report sections: analysts, research, trader proposal, risk debate, and portfolio decision. Optional price fields remain optional when evidence cannot support a number. Operational failure must not be turned into a fabricated Hold recommendation.

## 7. Technical Considerations

### Boundaries and reuse

- Proposed modules: `tradingagents/plugin/server.py`, `workflow.py`, `store.py`, and `data.py`; add files only for concrete responsibilities.
- Existing role modules provide shared prompt/output functions. The plugin never instantiates `TradingAgentsGraph`.
- Reuse `ANALYST_NODE_SPECS`, `agents/schemas.py`, `reporting.py`, vendor adapters, symbol utilities, and historical-memory filtering.
- Extract deterministic outcome calculations currently coupled to the graph so they can run without its model initialization.
- Add the official Python MCP SDK through an optional dependency. Reuse stdlib SQLite; no separate database service or job queue.

### Proposed public operations

`get_capabilities`, `start_analysis`, `get_analysis`, `list_analyses`, `submit_stage`, `finalize_analysis`, `cancel_analysis`, and `prepare_reflections`, plus named data/history tools. The architecture draft defines the proposed inputs. Public schemas must explain error recovery and expose no arbitrary execution escape hatch.

### Storage and failure behavior

Use `active`, `ready_to_finalize`, `completed`, and `cancelled` run states. Default plugin state root is `~/.tradingagents/plugin/`, overridable at startup. Reports use run-specific paths below the configured results root; memory remains compatible with the existing log.

Use transactions for stage acceptance and revision checks. Perform network calls outside database write transactions. Reject results that return after their stage was cancelled or advanced. Do not hold a transaction while waiting for Codex to reason.

Report files, memory, and SQLite cannot be committed atomically together. Finalization must retain enough state to retry exports and identify the same decision/reflection without duplication. Cross-process memory serialization must apply to the existing runner too.

The current data configuration is global. The initial implementation may serialize configured fetches and restore a complete configuration snapshot in `finally`. This is a documented throughput limit; a new configuration architecture is not a prerequisite.

### Verification and compatibility

Preserve the existing Python 3.10–3.13 test matrix unless dependency investigation produces an explicit, reviewed compatibility change. Add plugin-extra installation and protocol tests without making base installs require the optional MCP SDK.

Automated tests use deterministic vendor fixtures and supplied role outputs; they test orchestration and safeguards, not investment quality. At least one installed-host run is required to prove the Codex reasoning path. No new static type-checker or test framework is required for this feature.

## 8. Success Metrics / Release Gates

| Measure | Required result | Evidence |
|---|---|---|
| LLM backend independence | Zero model-client factory calls and zero LLM API requests in plugin tests; one real installed run without LLM API credentials | Factory guard, test logs, manual host record |
| Data feature coverage | All 12 financial tools plus identity, Reddit, StockTwits, and history discoverable and callable | Protocol contract tests |
| Workflow coverage | All selected roles complete; N=2 produces 4 research contributions and R=2 produces 6 risk contributions | Persisted stage receipts |
| Recovery | Mid-run restart preserves outputs/evidence and resumes the pending stage | Restart test |
| Retry correctness | Duplicate requests/submissions/exports do not duplicate stages, decisions, or reflections | Retry and fault-injection tests |
| Historical correctness | No injected lesson has a resolution date later than the analysis cutoff | Historical-memory tests |
| Output coverage | Existing report tree, final rating, saved decision, and finalized reflection are produced | Artifact and history assertions |
| Existing behavior | Existing test/lint/base-install checks pass | CI results |
| Installation | Plugin launches outside the checkout and works in a new Codex session | Clean-install and host acceptance record |

Release requires all gates above. Data vendor latency and host reasoning speed are external dependencies; this PRD does not promise a fixed completion time or a reduction in subscription usage.

### Suggested delivery order

1. US-001–004: runtime and shared role logic.
2. US-005–008: evidence tools, run creation, and data isolation.
3. US-009–013: full staged workflow and recovery.
4. US-014–016: artifacts, memory, and learning.
5. US-017–018: skill integration, packaging, and installed-host release gates.

This order is a delivery guide, not permission to claim an early subset provides full feature parity.

## 9. Open Questions

1. **Payload and runtime limits:** Choose concrete maximum report size, evidence page size, tool timeout, and round-count ceiling during the MCP contract implementation plan. Limits must be visible, tested, and must not silently truncate content; ordinary existing defaults must fit.
2. **MCP SDK version:** Select and pin a compatible SDK release during dependency verification, preserving the existing Python support matrix or documenting any required compatibility decision before implementation.

Resolved scope decisions: Codex first with Claude Code later; sequential roles in one Codex conversation; personal local installation with documented setup. The remaining questions are implementation constraints to resolve during file-level planning, not missing product-scope decisions.
