<!-- Last verified: 2026-03-31 -->

# Conventions

This file captures the current default implementation rules for the repo.

## Configuration

- Env override pattern: `TRADINGAGENTS_<UPPERCASE_KEY>=value`
- Empty or unset values preserve defaults.
- `.env` loading is centralized in `build_default_config(...)`.
- `llm_provider` and `backend_url` must remain available at top level as fallbacks.
- `mid_think_llm` defaults to `None`, which means it falls back to `quick_think_llm`.

## Agent Construction

- Prefer the factory/closure pattern: `create_X(...) -> node`.
- Extra dependencies such as memory, config, or repo objects are injected at factory time.
- Keep graph topology in graph modules, not in API or CLI code.

## Tool Execution

- If an agent uses `bind_tools()`, it must have a real tool execution path.
- Scanner agents use `run_tool_loop()` inline.
- The trading graph still compiles `ToolNode`-style branches, but the current analyst implementations mostly prefetch context or resolve tools inline before moving on.
- `MAX_TOOL_ROUNDS = 5`.
- `MIN_REPORT_LENGTH = 2000` triggers the one-time nudge path in `run_tool_loop()`.

## Vendor Routing

- Fail-fast is the default behavior.
- Only methods in `FALLBACK_ALLOWED` get cross-vendor fallback.
- Do not add news, indicator, or financial-statement methods to `FALLBACK_ALLOWED` without explicit contract verification.
- `route_to_vendor()` helpers must raise on failure, not return embedded error strings.
- Exception chaining matters: preserve the original cause.

## State and Parallelism

- Any LangGraph field written by parallel nodes needs a reducer.
- `ScannerState` uses `_last_value` reducers because scanner fan-out writes shared fields.
- Portfolio summary nodes also fan out, so reducer-backed fields remain important there as well.

## Report Paths and Stores

- The canonical process identifier is `run_id`.
- All runtime writes should go through `create_report_store(run_id=...)`.
- Do not hardcode report paths; use `report_paths.py`.
- Writes without `run_id` are expected to fail fast.

## Data-Shape Safety

- Inspect real `yfinance` DataFrame structure before coding against it.
- `top_companies` uses the ticker as index, not a normal column.
- `Sector.overview` does not provide performance data; sector performance comes from ETF proxies.

## AgentOS Runtime

- REST endpoints queue and start background execution.
- The WebSocket streams cached events and can lazy-load historical events from disk.
- Event mapping must stay crash-resistant; one malformed event should not kill the run stream.
- Keep rerun filtering selective. Never wipe all events for a targeted rerun.

## Portfolio Layer

- No ORM is used in the current code.
- `SupabaseClient` uses direct PostgreSQL via `psycopg2`.
- `PortfolioRepository` owns business logic over DB state plus report artifacts.

## Testing

- Build config explicitly in tests when env isolation matters.
- Patch vendor function references through the routing layer when testing vendor dispatch.
- Prefer deterministic tests around state shaping, reducers, checkpoint loading, and report-store behavior.
