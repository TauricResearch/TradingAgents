# TradingAgents Codex plugin architecture

Status: proposed architecture for review; implementation has not started.

## Objective and scope

Make the existing TradingAgents analysis capabilities available inside Codex through a skill and local MCP server. Codex performs all language-model reasoning through its normal authenticated session. The Python server never constructs an LLM client, launches another coding agent, or reads host authentication tokens. Existing API-backed CLI and Python usage remain supported.

Target the local Codex desktop/CLI environment first. Preserve a host-neutral MCP interface for a later Claude Code integration; Claude packaging and acceptance testing are a separate milestone. Subscription usage and model availability remain controlled by the host. Data-provider credentials remain independent.

Functional coverage includes selectable analysts, stock/crypto instrument context, data vendor selection, technical verification, sentiment sources, news/macro/prediction data, configurable debates, structured decisions, output language, saved reports, restart/resume, decision history, and outcome reflection. API provider selection, token callbacks, and provider-specific sampling controls remain features of the API runner; they are not silently translated into Codex settings.

## Components

```text
User -> Codex + trading-analysis skill
                  |
                  | local MCP over stdio
                  v
             MCP tool server
               /       \
      Workflow service   Data tools
          |                 |
      SQLite state     Existing vendor adapters
          |
      Existing schemas, report renderer, decision memory
```

1. The skill explains when to start/resume an analysis, how to follow a returned stage, how to use evidence, and how to submit outputs. It contains no duplicated financial role prompts.
2. MCP exposes typed data and workflow operations. It is an adapter, with no financial reasoning or duplicate business rules.
3. The workflow service supplies stage instructions, validates submissions, advances the sequence, and persists results. It does not instantiate `TradingAgentsGraph`.
4. Existing code owns vendor routing, calculations, instrument resolution, output schemas, Markdown rendering, ratings, and memory semantics.

Use the official Python MCP SDK as an optional `plugin` dependency. Use stdlib `sqlite3` for persistent workflow state; retain the repository's existing Pydantic and pytest usage. No web UI, hosted service, Redis queue, or general workflow engine is required.

## Shared role logic

Extract prompt preparation and result-to-state updates from existing agent factories into callable functions in the same role modules. Both existing factories and the plugin service call those functions. Keep LangChain invocation and fallback behavior in the API factories.

Share role metadata through a small explicit registry: role key, prompt builder, allowed evidence tools, optional output schema, renderer, and state update function. Reuse `ANALYST_NODE_SPECS` for analyst names and ordering instead of introducing a second analyst catalog.

The plugin accepts the existing structured schemas for sentiment, research manager, trader, and portfolio manager. Other roles submit nonempty report text. Invalid structured submissions return field errors and leave the stage pending; there is no hidden API retry or silent free-text downgrade in plugin mode.

Shared prompt extraction must preserve actual role context: researchers see analyst reports and debate history; research manager sees the debate; trader sees the plan and technical report; risk roles see reports, trader proposal, and debate; portfolio manager sees the plans, risk debate, and eligible past lessons.

One Codex conversation executes roles sequentially in the first version. Stage-specific instructions constrain the workflow but cannot erase earlier conversation context. This preserves functional roles and ordering, not independent-model isolation or numerical equivalence to the existing quick/deep model pipeline. Separate host sessions are a possible later execution mode, not a prerequisite for the local plugin.

## MCP contract

Names below are proposed public tool names. Workflow responses share `run_id`, `status`, `revision`, `current_stage`, and `warnings`. Stage identifiers include role and round, such as `research/bull/1`.

| Tool | Inputs | Behavior |
|---|---|---|
| `get_capabilities` | none | Supported tools, roles, settings, runtime/schema versions, and credential-presence checks without secret values. |
| `start_analysis` | ticker, analysis_date, asset_type, analysts, debate_rounds, risk_rounds, output_language, vendor overrides, request_id | Validate and freeze settings, create a run, return its identifier and current stage. Retrying the same request_id with identical inputs returns the same run; changed inputs conflict. |
| `get_analysis` | run_id, optional section/evidence_id, limit, cursor | Return status, current instructions, schema, relevant saved context, a saved evidence page, or one requested report section. Never refetch evidence merely to read status. |
| `list_analyses` | optional ticker/status, limit, cursor | Find runs after restarting Codex; return compact summaries. |
| `submit_stage` | run_id, stage_id, expected_revision, output | Validate the active stage and output, store it, advance exactly once, and return the next stage. A repeated identical accepted submission returns its receipt; conflicting or stale submissions cannot overwrite accepted work. |
| `finalize_analysis` | run_id | Render existing reports, export the decision to memory, and return artifact paths and rating. Retry safely after interrupted export. |
| `cancel_analysis` | run_id, expected_revision | Mark the run cancelled and retain its evidence/results. A cancelled run is not resumed; starting again creates a new run. |
| `prepare_reflections` | ticker, as_of_date | Calculate eligible outcomes for pending decisions and persist reflection stages linked to those decisions; return run identifiers. Repeated preparation reuses an existing job for the same decision/outcome. No LLM call. |

Reflection jobs use `get_analysis`, `submit_stage`, and `finalize_analysis` too. Their only reasoning stage asks Codex to produce the existing concise reflection; finalization updates the existing decision log with measured returns, benchmark, and resolution date.

Expose named, typed MCP wrappers for the existing twelve public financial tools: prices, indicators, verified snapshot, fundamentals, balance sheet, cash flow, income statement, ticker news, global news, insider transactions, macro indicators, and prediction markets. Also expose instrument identity, StockTwits posts, Reddit posts, and read-only decision history. Do not expose arbitrary Python execution or dynamic method lookup.

Data tools work independently for requests such as “show RSI for NVDA.” They accept an optional run_id. With a run_id, the server uses frozen run settings, validates the tool against the active role, enforces ticker/date boundaries, and records the result as evidence. Standalone calls cannot advance analysis state. Tool-specific arguments remain discoverable through their MCP schemas.

## Workflow and evidence

Analysis sequence: selected analysts in configured order -> bull/bear for N rounds -> research manager -> trader -> aggressive/conservative/neutral for R rounds -> portfolio manager -> finalization. Preserve the existing round meaning: two contributions per research round and three per risk round. No automatic parallel roles in the initial implementation.

Starting a run resolves and records instrument identity and captures eligible historical lessons. The skill calls `prepare_reflections` and completes any eligible reflection jobs before starting a same-ticker analysis to preserve the programmatic runner's deferred-learning behavior. Reflection preparation itself does not mark decisions resolved; only validated reflection finalization does. A reflection job is eligible only when its outcome resolution date is on or before as_of_date.

Sentiment evidence includes news, StockTwits, and Reddit with the same date window as the current analyst. The skill collects those through the named tools; the shared sentiment prompt builder consumes the recorded blocks. Market completion requires an attempted verified snapshot for the run ticker/date. Missing data is an explicit recorded result, not a fabricated estimate.

Evidence records include tool name, arguments, requested analysis window, fetch timestamp, returned content, and source metadata available from the adapter. Record a vendor only when known; do not infer it from the configured fallback chain. Preserve source-level warnings and historical coverage limitations. Do not label a historical run leakage-free merely because its requested end date is in the past.

Return bounded evidence pages with an explicit continuation cursor when needed; never silently truncate a required source. `get_analysis` supplies relevant role context and references rather than every raw response for the entire run. Persist evidence so restart does not silently replace it with newer live data.

Treat fetched articles/posts as untrusted evidence, not workflow instructions. The service can enforce tool permissions and submission shapes; it cannot prove every narrative statement true. Report validation must not claim to establish factual correctness.

## Persistence and recovery

Store plugin state under `~/.tradingagents/plugin/`, configurable at server startup. Store reports under the configured results directory in a run-specific subdirectory. Keep mutable files outside the installed plugin cache.

Use a small SQLite schema for runs, stage outputs, evidence, and export receipts. Each run stores a UUID, frozen configuration, schema/prompt version, revision, status, current stage, and the domain state consumed by existing report renderers. SQLite transactions protect stage advancement across multiple server processes. Network fetching occurs outside write transactions; record its result only if the run and stage revision are still valid.

States are `active`, `ready_to_finalize`, `completed`, and `cancelled`. A recoverable tool or validation error is attached to the pending stage and does not erase accepted outputs. Reject unsupported saved-state versions with an actionable compatibility error rather than silently upgrading or restarting them. A changed ticker, date, analyst selection, vendor configuration, or round count requires a new run.

Reports and Markdown memory cannot be committed in the same transaction as SQLite. Finalization therefore uses retryable exports: regenerate run-owned reports, upsert memory using a stable plugin run/decision identity, then record completion. Extend the memory API with an optional stable identity while preserving old entries. An export interrupted after writing memory must not duplicate decisions or reflections on retry. Shared memory writes need cross-process serialization, including the existing runner's writers; an in-process MCP lock alone is insufficient.

Existing LangGraph checkpoints remain specific to API runs. Plugin resume uses saved plugin stages; do not attempt to reinterpret one checkpoint format as the other.

## Configuration and validation

The existing dataflows configuration is process-global. For the initial MCP server, serialize configured data operations with a lock, install a complete run configuration for the operation, and restore the previous configuration in `finally`. This deliberately limits concurrent data fetching within a server. Replace it with explicit per-request configuration only if throughput warrants the larger refactor. Snapshot/restore must replace the complete dictionary, not use the current merge-only setter.

Allow only documented analysis and vendor settings through tools. Output/cache/memory roots and provider credentials are server startup settings, not model-selected paths. Validate UUIDs, ticker syntax using existing symbol rules, real calendar dates, ordered windows, supported asset types, unique nonempty analyst selections, positive round counts, and bounded page/output sizes. Default to existing round counts and language. Derive absent analysis dates in the user's local timezone and return the selected date explicitly.

Do not accept LLM provider/model/sampling options in plugin runs as if they affected Codex. Return an explanatory unsupported-setting error. Host model selection stays with Codex; collect host usage only if the host actually supplies it, and label missing usage unavailable.

## Proposed file layout

```text
plugins/tradingagents/
  .codex-plugin/plugin.json    supported Codex scaffold manifest
  .mcp.json                   local server launch configuration
  skills/trading-analysis/SKILL.md
  README.md                   installation and data credential setup
tradingagents/plugin/
  __init__.py
  server.py                   MCP registration and input/output schemas
  workflow.py                 explicit role sequence and stage validation
  store.py                    SQLite persistence and revisions
  data.py                     typed tool adapters, evidence, config scope
```

Modify existing role modules for shared prompt/update functions; `graph/trading_graph.py` and `graph/reflection.py` for reusable outcome calculation and reflection preparation; `agents/utils/memory.py` for safe idempotent exports; and `dataflows/config.py` for complete scoped restoration. Reuse `reporting.py` and `agents/schemas.py`. Split additional files only when a concrete responsibility outgrows these boundaries.

Add a `tradingagents-mcp` executable entry point and optional dependency in `pyproject.toml`. Launch the installed executable directly over stdio; stdout is protocol-only and logs go to stderr. The installation instructions provision a version-pinned Python environment before enabling the plugin. Do not imply that installing a manifest automatically installs Python dependencies. Validate clean-machine setup and launch outside this repository before distribution.

The current plugin-creator compatibility layout is supported by OpenAI documentation. Portable root manifests can be evaluated when adding another host; do not mix manifest schemas or assume Claude installs the Codex package unchanged.

## Implementation milestones and acceptance

1. **Share role logic.** Extract prompts and state updates without changing API behavior. Existing structured-output, debate-opening, crypto, language, and analyst-execution tests continue passing; shared-role fixtures compare prompt context and updates between execution paths.
2. **Expose data tools.** Add local MCP startup, capability discovery, named data tools, complete configuration restoration, and evidence storage. Protocol tests exercise discovery/calls and a missing-key source using fake vendors; no LLM credentials are present.
3. **Run the complete workflow.** Add transactional start/read/list/submit/cancel and the skill. A fixture-backed run covers all roles and multiple debate rounds. Tests reject skipped roles, invalid schemas, wrong dates/tickers, stale submissions, and changed retry payloads; identical retries succeed once.
4. **Complete persistence and learning.** Restart the server mid-run, resume with saved evidence, finalize existing reports, export memory, calculate benchmark outcomes, and submit a reflection. Inject failure between export and receipt to prove retries do not duplicate memory. Historical lessons remain bounded by resolution date.
5. **Install and prove the subscription path.** Validate the plugin, install into a clean Codex session, and run one real analysis with LLM API credentials absent. Instrument the factory to fail if called in plugin tests. Check saved reports and stage receipts, missing-data behavior, and resume after interruption. This is the release gate, not a claim made by static tests.

No feature-complete claim before all five milestones pass. No guarantee of identical investment conclusions between different models or between sequential Codex roles and the API graph. Initial release targets one local user; remote multi-user hosting and independently isolated host agents require separate designs.

## References

- Existing workflow: `tradingagents/graph/setup.py`, `analyst_execution.py`, `conditional_logic.py`, and `trading_graph.py`.
- Existing evidence: `tradingagents/dataflows/interface.py`, `config.py`, and `agents/analysts/sentiment_analyst.py`.
- Existing outputs: `tradingagents/agents/schemas.py`, `reporting.py`, and `agents/utils/memory.py`.
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins).
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
- [Codex authentication](https://learn.chatgpt.com/docs/auth).
- [Claude Code MCP](https://code.claude.com/docs/en/mcp).
