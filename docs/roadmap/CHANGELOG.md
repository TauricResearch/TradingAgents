# David's TradingAgents Fork Changelog

This changelog tracks changes that are specific to David's TradingAgents fork.
The upstream project changelog remains in the repository root `CHANGELOG.md`.

## 2026-07-20 - Local web workbench (phases E4–G4, H1–H2)

Added a localhost-only web workbench (`tradingagents web`) that runs the real
TradingAgents graph and visualizes the full 13-role debate, tool/data calls,
exact role inputs, and final reports in a browser. Additive to the CLI; shares
one `AnalysisRunner` execution path. See `Handoff.md` for the per-story
evidence trail.

### Added

- `tradingagents web` loopback-only launcher (FastAPI + Uvicorn, `127.0.0.1`
  only, no `--host` flag) with a capability preflight that rejects runtimes
  below the approved LangGraph/checkpointer floor.
- React + TypeScript + Vite frontend (`frontend/`) building straight into the
  tracked `tradingagents/web/static/` package, so an installed wheel serves the
  SPA without Node at runtime. V2 dark financial-research console visual
  language ported from the approved mockup.
- Shared live/history event reducer (`runReducer.ts`): one pure deterministic
  reducer processes both batch replay and one-by-one live SSE delivery, so
  historical and live views cannot drift. Covers every backend event family
  (run/role/turn/model/tool/data/input/artifact/report/graph/stats) with
  sequence dedupe and unknown-type forward-compat.
- 13-role workflow map with custom inline SVG icons; debate/verdict timeline
  with team filters, candidate-vs-committed frontier labels, and lazy-loaded
  per-turn response text; audit inspector with five role-input views (data,
  upstream, prompt, raw values, configuration) + tool-call cards + vendor
  provenance + reports + run-input snapshot.
- Backend observability layer (`tradingagents/observability/`): versioned
  event envelope, 13-role registry, durable observer, canonical business-state
  hashing, redaction, role projections, graph-task commit tokens; durable
  checkpoint frontier reconciliation with crash recovery.
- `SingleRunManager` (one-active-run invariant, startup recovery, retry/resume
  with a frozen resume fingerprint), `EventBroker` (atomic replay-to-live
  handoff, bounded subscriber queues, slow-consumer disconnect), filesystem
  `RunStore` (append-only events, content-addressed artifacts, atomic reports).
- CLI migrated onto the shared `AnalysisRunner` via `state_update_sink`;
  legacy root/`analyze` config, exit, and exception behavior preserved.
- CI gates: Python web + e2e integration tests, frontend typecheck/unit/build,
  committed-asset drift detection, wheel SPA asset verification, CLI smoke.
- `tests/web/e2e_app.py` integration tests (fake runner + real app/store/SSE)
  covering 13 roles, SSE replay/dedupe, run-scoped artifacts, 409 conflict,
  and secret absence.

### Changed

- `cli/main.py` `run_analysis` no longer opens a direct `graph.graph.stream()`
  loop; it builds an `AnalysisRequest` and calls `graph.run_analysis(...,
  state_update_sink=run_observer)`.
- `pyproject.toml` `[tool.setuptools.package-data]` adds
  `tradingagents = ["web/static/*", "web/static/assets/*"]` so the wheel ships
  the built SPA.

### Known limitations

- Playwright browser specs (`frontend/e2e/`) are written but skipped: the
  deterministic fake runner completes in ~50ms and races the EventBroker's
  live-queue delivery, so the browser subscriber receives only the replay
  window. Real LLM runs (seconds/turn) do not hit this race; the backend
  pipeline is verified by `tests/web/e2e_app.py` integration tests. A real
  minimum-depth smoke test is story H3.

## 2026-07-09 - Upstream v0.3.0/v0.3.1 sync (A-share-first)

Synced to upstream v0.3.0/v0.3.1. Adopted upstream's architectural improvements
while stripping team/enterprise-oriented expansion and protecting the local
A-share workflow. See `.upstream-sync-report.md` for the full sync rationale.

### Added

- Provider registry architecture (`ProviderSpec` registry) unifying the
  OpenAI-compatible providers behind a single spec.
- Verified data-access contract: symbol normalization on every vendor path, a
  strict configured vendor chain with no silent fallback, a typed `VendorError`
  taxonomy, look-ahead-safe news windows, and stale-OHLCV rejection.
- Analyst execution planning (graph rebuild) and the complete `DEBATE_PATH_MAP`
  crash-safety fix (#1088).
- Instrument identity resolution + verified market snapshot to stop LLM
  confabulation of prices and indicators.
- Structured-output hardening for local servers and thinking models
  (`tool_choice` fallback, null-ish float coercion).
- Structured output for the Sentiment Analyst.
- FRED macro indicators as an optional data vendor.
- Checkpoint resume keyed on graph shape (selected analysts, debate/risk depth,
  and asset mode folded into the thread id).
- Configurable LLM retry budget (`llm_max_retries`) and env-configurable
  reasoning depth (`TRADINGAGENTS_OPENAI_REASONING_EFFORT`,
  `TRADINGAGENTS_GOOGLE_THINKING_LEVEL`, `TRADINGAGENTS_ANTHROPIC_EFFORT`).
- Refreshed model catalog (Claude 5 incl. Sonnet 5 / Fable 5, GPT-5.5, DeepSeek
  V4, Qwen 3.7, MiniMax M3, Gemini 3.5, Grok 4.3).
- Programmatic report output via `TradingAgentsGraph.save_reports()`.
- CI gate: GitHub Actions runs pytest across Python 3.10-3.13, strict `ruff`,
  and a clean-install smoke import.
- Reddit RSS-first fallback, StockTwits/Alpha Vantage transport hardening, and
  crypto sentiment source mapping.

### Changed

- Switched the fork default LLM provider to **DeepSeek**
  (`deepseek-v4-pro` / `deepseek-v4-flash`) so the A-share-first fork runs
  without an OpenAI key.
- Adopted the upstream provider registry while preserving local provider
  defaults: DeepSeek, Xiaomi MiMo, Qwen (intl/CN), GLM (intl/CN), MiniMax
  (global/CN), OpenRouter, Ollama, Azure, OpenAI, Google, Anthropic, xAI.
- Stripped team/enterprise-oriented upstream expansion: Bedrock, Kimi, Groq,
  Mistral, NVIDIA NIM, and the generic `openai_compatible` endpoint; the
  Polymarket prediction-market data source. FRED was kept.
- Protected local features: Evidence Steward, `china_data` (tushare/akshare),
  `tavily_news`, credibility/consistency, news advisor, and the Chinese CLI /
  JSON config / progress-event layer.
- Hybrid identity resolution: A-shares use the local three-tier chain
  (tushare -> akshare -> yfinance); non-A-shares use upstream yfinance.
- Config precedence: an explicit `TRADINGAGENTS_*` value or CLI flag now wins
  over interactive defaults; invalid boolean env values fail loudly.

### Fixed

- A-share `load_ohlcv` vendor path: the verified snapshot and indicators now
  route A-shares through tushare (added `get_stock_tushare_df`/`akshare_df` and
  a `via_vendor` kwarg), resolving a hang where A-share `propagate` stuck at the
  verified snapshot step.
- Alpha Vantage look-ahead filter now actually runs (parse the JSON-string
  fundamentals payload before filtering).
- News analyst prompt aligned to the `get_news` tool signature.
- Shared debate/risk routers can no longer crash mid-run (every edge shares the
  complete path map).
- Checkpoint resume no longer continues the wrong graph under different choices.
- Crypto sentiment sources resolve (StockTwits `<BASE>.X` and Reddit base-symbol
  matching).
- CI failures from the sync: 9 tests (`via_vendor` mock signatures,
  evidence-steward non-determinism, yfinance-news timestamps, env-override
  default assertions) and 46 ruff errors (import sorting, E402/B008 per-file
  ignores for `cli/`, unused binding, SIM102).

### Verification

- `pytest -q` on the merge commit: 670/671 passed (1 data-stale, non-regression).
- A-share `300750` end-to-end smoke test passed (SELL/Underweight, 288.9s).
- After the CI fix: `ruff check` clean; 684 tests pass in the CI keyless env
  (placeholder API keys); 20 evidence/validator/yfinance tests pass with real
  local keys.

## 2026-05-12 - Upstream v0.2.5 sync with local strategy preservation

### Added

- Added an `Evidence Steward` graph node before the researcher debate stage to
  block downstream discussion when A-share evidence is too thin, contradictory,
  or identity-ambiguous.
- Added canonical A-share company-profile resolution with fallback across
  Tushare, AkShare, and YFinance.
- Added a config-first Chinese CLI path through `tradingagents.config.example.json`.
- Added concise dataflow progress events for market/news/data calls.
- Added local tests covering Evidence Steward behavior, CLI config loading,
  dataflow progress, yfinance cache fallback, and provider API-key mapping.

### Changed

- Adapted upstream v0.2.5 provider improvements while preserving local defaults
  for DeepSeek, Xiaomi MiMo, Qwen, GLM, MiniMax, OpenRouter, Ollama, Azure,
  OpenAI, Google, Anthropic, and xAI.
- Kept Chinese CLI prompts/status output as the default interactive experience.
- Kept A-share data routing as Yahoo Finance primary with Tushare/AkShare and
  Alpha Vantage as configured fallbacks or supplements.
- Kept Tavily as the primary curated market-news search layer in the dataflow
  layer rather than introducing a separate graph node.
- Adapted upstream regional benchmark support while preserving local ticker
  normalization for A-share symbols.

### Fixed

- Restored `curl_cffi` yfinance request-error recovery through the local OHLCV
  cache path for stock data.
- Restored DeepSeek runtime guardrails: retired model names are rejected and
  thinking is disabled by default for this workflow.
- Removed duplicate graph node construction introduced during conflict
  resolution and kept the Trader node on the quick-thinking LLM.
- Unified CLI provider API-key validation with the canonical provider-to-env-var
  mapping used by runtime LLM clients.

### Verification

- `rtk conda run -n tradingagents python -m pytest -q`
  - Result: `239 passed, 78 subtests passed`
- `rtk git diff --check`
- `rtk python3 -m compileall -q cli tradingagents`
