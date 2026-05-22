# TradingAgentsWeb Architecture

## Purpose

TradingAgents currently exposes its primary user workflow through an interactive CLI. TradingAgentsWeb will provide a browser-based replacement for that CLI workflow while reusing the existing TradingAgents analysis engine.

The first version is intentionally simple: one local TradingAgentsWeb app, one active real analysis run at a time, and no mock/demo execution mode.

## Product Direction

TradingAgentsWeb should visually execute what can currently be done in the CLI.

Selected direction:

- One-page run console.
- CLI-equivalent controls visible on the page.
- Operations dashboard for live execution output.
- Real TradingAgents analyses only.
- One active analysis run at a time.

Out of scope for the first version:

- Multi-user hosting.
- Parallel ticker runs.
- Background job queues.
- Authentication.
- Mock/demo runs.
- Stored run history browser beyond saved report files.
- React or another separate frontend build system.

## Architecture

The TradingAgentsWeb layer should be thin and should not duplicate the trading logic.

Backend:

- FastAPI application inside the root `web/` package, matching the existing root `cli/` package style.
- Wraps the existing `TradingAgentsGraph`.
- Reuses CLI validation and configuration behavior where practical.
- Streams live run events to the browser while the graph executes.
- Enforces one active run at a time.

Frontend:

- Plain HTML, CSS, and JavaScript served by FastAPI.
- No separate frontend build step in the first version.
- One screen split into setup controls and live run dashboard.

Execution:

- User submits run settings from the browser.
- Backend builds a `DEFAULT_CONFIG.copy()` with submitted overrides.
- Backend creates `TradingAgentsGraph`.
- Backend streams graph chunks and converts them into UI events.
- Browser updates agent statuses, run statistics, recent messages, report sections, and final decision.

## Setup Controls

The first screen should expose controls equivalent to the CLI:

- Ticker symbol.
- Analysis date.
- Output language.
- Analyst selection.
- Research depth.
- LLM provider.
- Provider region where applicable, such as Qwen, GLM, and MiniMax.
- Quick-thinking model.
- Deep-thinking model.
- Provider-specific reasoning or effort options where applicable.
- Checkpoint/resume toggle.
- Clear checkpoints action.

The UI should preserve current CLI behavior:

- Normalize ticker symbols while preserving exchange suffixes.
- Detect stock versus crypto from ticker suffix.
- Disable or remove fundamentals analysis for crypto.
- Require at least one analyst.
- Validate date format as `YYYY-MM-DD`.
- Surface missing provider API keys clearly.
- Default the web console to local Ollama: `llm_provider = "ollama"`, backend endpoint `http://localhost:11434/v1`, quick model `qwen3:latest`, and deep model `qwen3:latest`. Using the same smaller model for both paths avoids loading the larger `glm-4.7-flash:latest` model, which can exceed local memory on machines with about 11 GiB available.
- Honor `OLLAMA_BASE_URL` when an Ollama backend URL is not supplied, matching the root README guidance for remote `ollama-serve`.

## Live Operations Dashboard

The right side of the page should prioritize report reading and keep operational telemetry secondary.

Primary report experience:

- Render streamed report sections as a polished investor memo, not as a raw wall of text.
- Show a memo header with ticker, date, asset type, and a decision badge when detectable.
- Maintain an executive summary with a live thesis and key takeaways while the run is still executing.
- Render each report section as a readable memo section with a prose summary, extracted highlights, and collapsed raw output for auditability.
- Promote the final portfolio decision into the memo thesis and decision badge when available.

Operational telemetry remains available below the memo for debugging and run monitoring.

Saved reports:

- TradingAgentsWeb exposes a read-only saved reports browser backed by `results_dir`.
- The browser lists `*/TradingAgentsStrategy_logs/full_states_log_*.json` files under the configured results directory.
- Loading a saved report reuses the same investor memo renderer as live runs.
- The backend resolves requested report paths under `results_dir` and rejects files outside that directory.

Primary dashboard sections:

- Agent/team progress.
- Reports completed count.
- LLM call count.
- Tool call count.
- Token counts when available.
- Recent messages.
- Recent tool calls.
- Current report section.
- Final portfolio decision when complete.

Agent groups should mirror the CLI:

- Analyst Team: Market Analyst, Sentiment Analyst, News Analyst, Fundamentals Analyst.
- Research Team: Bull Researcher, Bear Researcher, Research Manager.
- Trading Team: Trader.
- Risk Management: Aggressive Analyst, Neutral Analyst, Conservative Analyst.
- Portfolio Management: Portfolio Manager.

Report sections should mirror the CLI:

- Market Analysis.
- Sentiment Analysis.
- News Analysis.
- Fundamentals Analysis.
- Research Team Decision.
- Trading Team Plan.
- Portfolio Management Decision.

## Streaming Events

The backend should translate graph chunks into browser-friendly events.

Expected event categories:

- `run_started`
- `agent_status`
- `message`
- `tool_call`
- `report_section`
- `stats`
- `run_completed`
- `run_failed`

The frontend should treat streamed events as incremental state updates. It should not need to understand LangGraph internals.

## Persistence

TradingAgentsWeb should continue to use existing TradingAgents persistence behavior:

- Decision log at `~/.tradingagents/memory/trading_memory.md`, unless overridden by environment.
- Checkpoints under `~/.tradingagents/cache/checkpoints`, unless overridden by environment.
- Generated reports under the configured `results_dir`.
- Previously generated web reports can be loaded from `results_dir/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<DATE>.json` through the Saved Reports browser.

Report saving should reuse the CLI report structure where possible.

## Error Handling

The app should display direct, actionable errors for:

- Another run already active.
- Missing API key.
- Invalid ticker.
- Invalid date.
- No analysts selected.
- Provider/model mismatch.
- Data provider failures.
- LLM provider failures.
- Unexpected backend exceptions.

The first version should avoid complex retry or recovery behavior. Failures should be visible and debuggable.

## Testing Strategy

Minimum useful coverage:

- Backend request validation tests.
- Config-building tests.
- One-active-run guard test.
- Smoke test that imports the FastAPI app.
- Manual browser verification that the app loads and renders the run controls.

Real end-to-end TradingAgents runs require API keys and may incur provider costs, so they should be manual unless explicitly configured in the environment.

## Current Decisions

- Use a one-page console, not a wizard or reports-first workspace.
- Show CLI-equivalent controls, not simplified defaults or presets.
- Use an operations dashboard, not report-only or debate-board output.
- Support one active run at a time.
- Run only real analyses, no mock mode.
