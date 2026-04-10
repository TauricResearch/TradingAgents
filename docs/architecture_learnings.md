# Architecture Learnings

## Phase 1: Conditional Logic Simplification

- Identified highly repetitive conditional logic for agents (market, news, social, fundamentals).
- Replaced identical `should_continue_*` methods with a single factory method `make_should_continue`.
- This adheres to DRY principles, making the conditional logic concise, easier to maintain, and simpler to test. The `setup.py` was updated to use this factory instead of dynamic `getattr`.

## Phase 2: Decoupling API and Graph Topology

- Identified tight coupling in `agent_os/backend/routes/runs.py` where graph dependency trees (like `_SCAN_RERUN_DESCENDANTS`) were hardcoded.
- Abstracted this into `get_scanner_descendants` inside `tradingagents/graph/scanner_setup.py`.
- This allows the graph component to own its topology, while the API simply queries it for reruns. This ensures changes to the graph automatically propagate to the API without modifying routes.

## Phase 3: Auto-Run Completion Barrier And Human Decision Gate

- Observed in run `01KN0QTY60VHHJTJ5WA04S33D3` that the auto workflow could move into portfolio management without durable proof that every queued ticker pipeline had reached a terminal artifact.
- The root cause was orchestration state, not a broad tool outage. The run mostly showed graceful tool skips, but Phase 2 still lacked a hard completion barrier before Phase 3.
- Added a terminal-artifact check in `LangGraphEngine.run_auto()` so queued tickers must resolve to `completed`, `aborted`, or an explicit incomplete/failure record before portfolio logic can proceed.
- Added an `awaiting_decision` runtime state so AgentOS can pause before Phase 3, present incomplete tickers to the user, retry only the selected ones, and then either pause again or continue.
- Preserved this decision state in persisted run metadata so reloading the UI or restarting the backend does not silently lose the pending choice.

## Warnings For Future Changes

- Do not treat "pipeline generator returned" as equivalent to "ticker is safe for portfolio stage". The durable source of truth is the saved analysis artifact and its terminal status.
- Do not collapse graceful skips, aborted analyses, and missing artifacts into one generic "failure" bucket. The UI decision prompt needs ticker-specific reasons to support informed retry choices.
- Any new auto-run branch that can pause must update all three layers together:
  - backend run status persistence
  - websocket terminal-state signaling
  - frontend stream status handling
- If `awaiting_decision` is changed or renamed, update the route layer, websocket payload, stream hook, history UI, and tests in the same change. A partial update will strand runs in a pseudo-running state.
- When introducing new sub-run execution keys, keep root run logger cleanup in a `finally` block. This regression was easy to introduce once auto pause/retry logic split the flow across methods.

## Phase 4: Hard Failures on Pipeline Timeouts

- Discovered that gracefully injecting "timeout fallback" statuses (such as fake HOLD recommendations) when an upstream analyst hits an LLM timeout actually poisoned downstream nodes. It caused synthesis agents (e.g. Portfolio Manager, Trader) to hallucinate debate details to meet their prompt constraints using the fallback text.
- More importantly, generating a silent fallback meant the LangGraph node "succeeded", saving the poisoned state to the checkpointer database. This destroyed the system's ability to cleanly resume the pipeline from UI.
- **Learning**: Resilient systems with a checkpointer backend should favor hard failures over graceful logical degradation. When `invoke_with_timeout` encounters an LLM timeout or HTTP connection error, it must forcefully raise an exception to halt LangGraph immediately. This preserves the graph state perfectly up to the prior node, allowing seamless UI retries without manual state-cleaning or dataset hallucination.


## Phase 5: TTM CSV Parse Failure and Financial-Sector Column Gaps

- Root cause of persistent AVGO/BAC failures (run `01KNSNAJJA6JZWA7PCGNRGCCD6`, 6 reruns): vendor functions in `y_finance.py` prepend `# Header comment\n\n` lines before the CSV body. `pd.read_csv(StringIO(text), index_col=0)` treated the first `#` line as the column-header row (1 field), then subsequent data rows with many fields triggered `ParserError: Expected 1 fields in line N, saw M`. The `except Exception: return None` in `_parse_financial_csv` silently swallowed it → `quarters_available: 0` every time.
- Fix: `pd.read_csv(..., comment='#', skip_blank_lines=True)` — pandas skips `#`-prefixed lines before parsing, matching the intended CSV layout.
- **Warning**: Any future vendor function that prepends non-CSV text before the data body (headers, timestamps, metadata) must either strip it before returning, or the parser must use `comment=` to skip it. Don't add new header formats without verifying `_parse_financial_csv` handles them.
- **Financial-sector columns**: Banking tickers (BAC, C, JPM) use `Net Interest Income` instead of `Total Revenue`, and `Total Liabilities Net Minority Interest` instead of `Total Debt`. All column-candidate lists in `ttm_analysis.py` must include these aliases, or TTM metrics will be `N/A` for financials even when the parse succeeds.
- **Empty LLM response guard**: minimax and some weaker models can return `response.content = ""` without raising an error. Downstream code that stores the content directly (e.g. `portfolio_manager.py`) must guard for empty strings and synthesize a fallback from structured state rather than silently persisting an empty `final_trade_decision`. An empty decision causes `analysis_has_deep_dive` to return False, which marks the ticker as failed and blocks portfolio stage.
