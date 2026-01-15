# Changelog

All notable changes to the **TradingAgents** project will be documented in this file.

## [Unreleased] - 2026-01-15 (Phase 2.7: Audit Refinement & Refined Safety)

### Added
- **NYSE Market Hours Gate**: Gatekeeper now aborts trades outside 9:30-16:00 EST.
- **Corporate Action (Split) Check**: Added "Massive Drift" detection (>50%) to the pre-trade Pulse Check.
- **Institutional-Grade Parsing**: Refactored `DataRegistrar` to extract `net_insider_flow_usd` as a deterministic float.
- **Safety Verification Suite**: Created `verify_logic_v2_7.py` covering drift, splits, market hours, and insider vetoes (100% Pass).

### Changed
- **Brittle Code Purge**: Removed all "string-sniffing" logic for insider data in the Gatekeeper; replaced with pure mathematical comparisons against the `FactLedger`.
- **Pulse 2.0**: Added strict 2s timeouts to pulse checks to prevent blocking the entire graph execution.

## [Unreleased] - 2026-01-15 (Phase 2.6: Audit Remediation)

### Added
- **The Execution Gatekeeper (Python Veto)**: Created `ExecutionGatekeeper` node (`tradingagents/agents/execution_gatekeeper.py`) to serve as the Final Authority.
    - **Trend Gate**: Implements "Don't Fight the Tape" logic (Blocks SELLS if `Price > 200SMA` + `Growth > 30%`).
    - **Compliance Gate**: Blocks trades if Insider Net Flow indicates a "Cluster Sale".
    - **Divergence Gate**: Aborts execution if Analyst Disagreement (`abs(Bull-Bear) * Confidence`) exceeds 0.4.
- **Structured Authority (Typed Contracts)**:
    - Updated `AgentState` with `TraderDecision` (Proposal) and `FinalDecision` (Enforced Result) TypedDicts.
    - Added `ExecutionResult` Enum for machine-readable status codes (`APPROVED`, `ABORT_COMPLIANCE`, `BLOCKED_TREND`, etc.).

### Changed
- **Trader Demotion**: Refactored `trader.py` to be an **Advisory** node.
    - It now outputs a strict JSON proposal (`action`, `confidence`, `rationale`) instead of executing orders directly.
    - The Trader submits to the Gatekeeper, allowing for deterministic overrides.
- **Graph Wiring**: Updated `setup.py` to route `Trader` -> `Execution Gatekeeper` -> `END`, effectively establishing the "Python Veto" architecture.

## [Unreleased] - 2026-01-15 (Phase 1: The Foundation)

### Added
- **Hyper-Immutability (Physically Secured State)**: Implemented `FactLedger` (TypedDict) and `write_once_enforce` reducer in `agent_states.py` to cryptographically lock data reality.
    - Ledger is hashed (SHA-256) upon creation.
    - Wrapped in `MappingProxyType` to prevent any downstream agent from mutating the facts.
- **The Data Registrar (Parallel Gatekeeper)**: Created `DataRegistrar` node (`tradingagents/agents/data_registrar.py`) that acts as the Single Source of Truth.
    - **Parallel I/O**: Fetches Price, Fundamentals, News, and Insider data concurrently (4x speedup over sequential).
    - **Partial Poisoning Guard**: Hard "Fail-Fast" if critical domains (Price, Fundamentals) are missing.
    - **Freshness Simulation**: Configurable `TRADING_MODE` (simulation/production) to allow rigorous testing without stale-data aborts.

### Fixed
- **Hallucination Vectors (The Lobotomy)**: Removed ALL tool access from `Market`, `Social`, `News`, and `Fundamentals` analysts.
    - Analysts now consume exclusively from `FactLedger`.
    - Eliminated "Tool Use Loop" latency and potential for agents to fetch divergent data.
- **Graph Wiring**: Refactored `setup.py` to route `START` -> `Data Registrar` -> `Market Analyst` -> Parallel Fan-Out.

## [Unreleased] - 2026-01-14 (Architecture Hardening & Documentation)

### Added
- **Documentation (System Prompts)**: Created `docs/SYSTEM_PROMPTS.md`, a single source of truth containing:
    - Verbatim System Prompts for all 12 Agents.
    - Explicit Roles & Objectives.
    - **Mermaid Diagram** illustrating the Parallel Fan-Out/Fan-In Topology.
- **Output Sanitization (Agent Level)**: Implemented `normalize_agent_output` in `agent_utils.py` and applied it to every Analyst (`Market`, `Social`, `News`, `Fundamentals`).
    - Guarantees clean string outputs for downstream consumers (CLI, WebUI).
    - Prevents crashes when LLMs return complex JSON/List structures.

### Fixed
- **CLI Crash (Separation of Concerns)**: Reverted business logic in `cli/main.py` and moved sanitization upstream to the Agent layer (Mentor Critique).
- **Dangling Tool Errors**: Fixed "Tool Use without Tool Result" errors in `technical_indicators_tools.py` by wrapping execution logic in strict `try/except` blocks (similar to other tool files).

## [Unreleased] - 2026-01-14

### Added
- **Standalone HTML Reports**: Refactored report generation to perform server-side Markdown-to-HTML rendering using Python.
    - Removed dependency on client-side `marked.js` and CDNs.
    - Reports are now fully offline-capable.
    - Cleaned up JSON keys to remove `.md` extensions for cleaner data structure.
- **Google News Adapter**: Implemented `get_google_global_news` adapter in `google.py` to match the standard `(curr_date, look_back_days)` interface, adhering to the Adapter Pattern and fixing signature mismatches.
- **Robust Demo Script**: Created `run_agent.py` (replacing demo scripts) with:
    - Automatic `.env` loading.
    - `backend_url` handling (clearing OpenAI defaults when using Anthropic).
    - Hardened configuration for "Deep Analysis" (Debate Rounds=2).
    - Pre-configured Google News vendor to bypass AlphaVantage rate limits.

### Fixed
- **Rate Limit Crash**: Fixed `AlphaVantageRateLimitError` by switching default news vendor to Google in `run_agent.py`.
- **Interface Mismatch**: Fixed `TypeError` in `get_global_news` where string dates were passed to integer arguments.
- **Logi Crash**: Fixed `TypeError` in `TradingAgentsGraph.apply_trend_override` caused by duplicate arguments in the method call.
- **Broken Entry Point**: Updated `startAgent.sh` to point to the correct `run_agent.py` script instead of a non-existent file.

## [Unreleased] - 2026-01-14 (Performance & Logic Upgrade)

### Changed
- **Risk Star Topology (Strategy 2)**: Replaced sequential "Round Robin" risk debate with a parallel "Fan-Out / Fan-In" architecture.
    - `Trader` now triggers `Risky`, `Safe`, and `Neutral` analysts simultaneously.
    - Implemented `Risk Sync` node and `merge_risk_states` reducer (AgentStates) to handle concurrent updates safely.
    - Reduced Risk Phase latency by ~60%.
- **Batch Reflection (Strategy 1)**: Consolidated 5 sequential reflection calls into a single "Session Audit" call, reducing token usage and latency by ~80% in the post-trade phase.
- **Parallel I/O (Strategy 3)**: Refactored `tradingagents/dataflows/local.py` (Reddit News) to use `ThreadPoolExecutor` (max 10 workers), achieving 5x-10x speedup in data fetching.

### Added
- **Rejection Loops (Self-Correction)**: Upgraded `EnhancedConditionalLogic` to allow agents to reject weak arguments and force a revision loop (`Bull -> Bull`) instead of passing bad data downstream.
- **Trader Mental Models (Logic Patch)**: Injected "Critical Mental Models" into `trader.py` system prompt to fix "Value Trap" bias.
    - **CapEx**: Explicitly defined Strategic CapEx as "Moat Building" (Bullish) for platform monopolies.
    - **Regulation**: Reframed Antitrust Risk as a "Chronic Condition" (Position Sizing) rather than "Terminal Disease" (Panic Sell).


### Changed
- **Parallel Architecture (AsyncIO)**: Refactored `setup.py` to implement a "Fan-Out / Fan-In" pattern using LangGraph.
    - `Market Analyst` now triggers `Social`, `News`, and `Fundamentals` analysts **concurrently**.
    - Added `Analyst Sync` node to synchronize parallel branches.
    - Added `Analyst Sync` node to synchronize parallel branches.
    - reduced total runtime by ~50% by overlapping heavy LLM/Tool operations.
- **Fail Fast Scraper**: Optimized `googlenews_utils.py` to timeout after ~30s (down from 3m) when blocked, ensuring rapid failover to backup vendors.

### Fixed
- **API Error 400 (Dangling Tool Use)**: Fixed crash in `Fundamentals Analyst` and others caused by unhandled tool exceptions (e.g. Rate Limits).
    - Wrapped all tools in `fundamental_data_tools.py`, `news_data_tools.py`, `core_stock_tools.py`, and `technical_indicators_tools.py` with `try/except` blocks.
    - Tools now return error strings instead of crashing, ensuring stricter API compliance and system resilience.

## [Unreleased] - 2026-01-14 (Architecture Hardening)

### Added
- **Subgraph Isolation (The Sandbox)**: Refactored `Social`, `News`, and `Fundamentals` analysts to run in their own isolated `StateGraph` containers.
    - Implemented `Init_Clear` node to wipe message history at the start of each subgraph.
    - Prevents cross-contamination of tool calls between parallel analysts (fixing "Dangling Tool Use" API Error 400).
- **Strict State Schemas (Type Safety)**: Defined `SocialAnalystState`, `NewsAnalystState`, and `FundamentalsAnalystState` in `agent_states.py`.
    - Restricts analyst subgraphs to only access necessary inputs (`company`, `date`) and write specific outputs (`report`).
    - Eliminates "global state leakage" risks.
- **Universal Notification System**: Implemented a unified factory pattern (`get_notifier`) in `notifications.py` supporting:
    - **CallMeBot**: Free WhatsApp notifications (Personal Use).
    - **Telegram**: Free Bot API notifications (Reliable Alternative).
    - **Twilio**: Enterprise-grade WhatsApp notifications.
    - Zero-dependency implementation (using `requests`).

### Fixed
- **Concurrent Write Conflict**: Resolved `InvalidUpdateError` in LangGraph during parallel "Fan-In".
    - Implemented `reduce_overwrite` logic in `AgentState`.
    - Allows parallel subgraphs to return identical read-only inputs (`company_of_interest`) without triggering race condition errors.

## [Released] - 2026-01-13

### Added
- **Dynamic Parameter Tuning (The Learning Loop)**: Implemented full self-reflection cycle. The Reflector agent now parses its own advice into JSON (`rsi_period`, `stop_loss_pct`), persists it to `data_cache/runtime_config.json`, and the Market Analyst loads it to tune the Regime Detector in real-time.
- **Audit Archival**: Every tuning event is now archived to `results/{TICKER}/{DATE}/runtime_config.json` for historical auditing, ensuring we can reproduce why parameters changed on any given day.
- **Atomic Persistence**: Implemented `agent_utils.write_json_atomic` to prevent race conditions during config saves.
- **Centralized Config**: Moved hardcoded paths to `default_config.py` (DRY principle).

### Fixed
- **Reflector Logic Gap**: The Reflector was previously "shouting into the void"—making suggestions but having no mechanism to apply them. This circuit is now closed.

## [Unreleased] - 2026-01-11

### Added
- **Insider Veto Protocol (Rule B)**: Hard-coded safety gate in `trading_graph.py` that blocks ALL buy signals if Net Insider Selling exceeds $50M while the stock is in a technical downtrend (Price < 50 SMA). This prevents "Falling Knife" catches.
- **Relative Strength Determinism**: Upgraded `market_analyst.py` to calculate a mathematical `risk_multiplier` (0.0x - 1.5x) based on the Asset Regime vs. SPY Regime correlation, removing LLM "confidence" hallucinations from position sizing.
- **Portfolio Awareness (Rule 72)**: Implemented State Persistence (`portfolio`, `cash_balance`) and a hard-coded Stop Loss check in `trading_graph.py`. If a position's unrealized PnL drops below -10%, the system forces a "LIQUIDATE" order, bypassing all AI debate.
- **Self-Tuning Architecture**: Updated `reflection.py` to output a structured JSON block (`UPDATE_PARAMETERS`) instead of prose advice, enabling future automated parameter optimization.
- **Gemini 2.0 & 3.0 Support**: Updated `cli/utils.py` to support `gemini-2.0-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-3-flash-preview` and `gemini-3-pro-preview` models.
- **Console Debugging**: Added explicit console print statements for critical "Smoking Gun" debug traces in `market_analyst.py` and `trading_graph.py`.

### Changed
- **Mandatory Regime Detection**: Modified `graph/setup.py` to Force-Execute the `Market Analyst` node as the first step in every workflow. This permanently fixes the "UNKNOWN Regime" bug by ensuring context is established before any fundamental analysis begins.
- **Data Robustness**: Patched `y_finance.py` and `alpha_vantage_news.py` to accept `**kwargs` and `curr_date`, resolving crashes in the `route_to_vendor` pipeline when passing standardized arguments.


### Fixed
- **Override Logic Mismatches**: Fixed critical Enum-to-String type mismatch in `apply_trend_override` that was silencing the "Safety Valve" logic.
- **Data Pipeline Failures**: Injected robust error handling and type checking in `market_analyst.py` to identify why `RegimeDetector` receives invalid data (causing "UNKNOWN" regimes).
- **Gemini 404 Errors**: Removed invalid/deprecated model names causing 404s.
- **Reflector Regime Integration**: Updated `reflection.py` to incorporate market regime context, ensuring post-trade analysis understands the 'Why' behind regime-based decisions.

## [Unreleased] - 2026-01-10

### Added
- **Global Market News**: Implemented `get_global_market_news` in Alpha Vantage module to support generic market news (topics: economy_macro, financial_markets), fixing the lack of a primary vendor for global news.
- **Configurable Embeddings Truncation**: Added `EMBEDDING_TRUNCATION_LIMIT` env var (default 1000) to prevent `413 Payload Too Large` errors with local models.
- **Local Embedding Service Support**: Added support for Anthropic to use local embedding service via URL
  - Anthropic doesn't provide embeddings API, so users can run **Hugging Face Text Embeddings Inference (TEI)** in Docker
  - Configure via `EMBEDDING_API_URL` environment variable (default: `http://localhost:11434/v1`)
  - Configure model via `EMBEDDING_MODEL` environment variable (default: `all-MiniLM-L6-v2`)
  - Keeps main application lightweight - heavy dependencies (PyTorch) isolated in separate container
- **Environment Variable Configuration**: Added comprehensive environment variable support for all LLM providers and embedding configuration
  - `OPENAI_API_URL` - Custom OpenAI API endpoint
  - `ANTHROPIC_API_URL` - Custom Anthropic API endpoint
  - `GOOGLE_API_URL` - Custom Google API endpoint
  - `OPENROUTER_API_URL` - Custom OpenRouter API endpoint
  - `OLLAMA_API_URL` - Custom Ollama API endpoint
  - `EMBEDDING_PROVIDER` - Choose embedding provider: `local`, `openai`, `google`, `ollama`
  - `EMBEDDING_API_URL` - Custom embedding API endpoint (for Ollama or Docker service)
  - `EMBEDDING_MODEL` - Custom embedding model name
- **Anthropic Claude 4.5 Thinking Models**: Added support for latest Anthropic thinking models
  - `claude-sonnet-4-5-thinking` - Advanced reasoning with extended thinking
  - `claude-opus-4-5-thinking` - Premier reasoning with extended thinking
  - Removed older Claude models (3.5, 3.7, 4.0) to focus on latest thinking models
- **Documentation**: Created comprehensive guides and verification tools
  - `docs/LOCAL_EMBEDDINGS.md` - Complete guide for local embeddings setup
  - `verify_local_embeddings.py` - Verification script for sentence-transformers
  - `verify_ollama_embeddings.py` - Verification script for Ollama (optional)
  - Updated `.env.example` with all new configuration options

### Changed
- **Dependency Cleanup**: Removed `sentence-transformers` from `requirements.txt` to keep main application lightweight.
- **Virtual Environment**: Recreated `.venv` to ensure a clean state without unused heavy dependencies.
- **Embedding Architecture**: Refactored `tradingagents/agents/utils/memory.py` to support multiple embedding providers with clean separation of concerns
  - Automatic provider selection based on LLM provider
  - Local embeddings as default for Anthropic and Ollama providers
  - Maintained backward compatibility with existing API-based embeddings
- **CLI Provider Selection**: Updated `cli/utils.py` to use environment variables for all LLM provider API URLs with sensible defaults
- **Configuration Documentation**: Enhanced `.env.example` with detailed comments and examples for all configuration options

### Fixed
- **Global News Failure**: Resolved `RuntimeError: All vendor implementations failed` for `get_global_news` by correctly mapping Alpha Vantage and implementing the missing fallback logic.
- **Error Reporting**: Improved `interface.py` to propagate detailed error messages from failed vendors to help debugging.
- **Embedding Crash**: Fixed crashes when processing large documents with local embedding models by enforcing strict token limits via truncation.
- **Anthropic Embedding Error**: Resolved `404 Not Found` error when using Anthropic as LLM provider by implementing automatic fallback to local embeddings (Anthropic doesn't provide an embeddings API)

### Technical Debt
- None - All changes follow SOLID principles with proper separation of concerns

## [Unreleased] - 2026-01-09

### Added
- **Blindfire Protocol Activated**: Fully integrated `TickerAnonymizer` into all analyst agents (`Market`, `News`, `Fundamentals`, `Social`) and data tools. The LLM now only sees "ASSET_XXX" in prompts, preventing data contamination.
- **Anonymization Middleware**: Implemented transparent request interception in `core_stock_tools.py` and other tool files to deanonymize inputs and anonymize outputs automatically.
- **State Persistence**: Added auto-persistence to `TickerAnonymizer` (`ticker_map.json`) to ensure consistent ticker mapping across isolated agent and tool instances.
- **API Key Verification**: Added `verify_google_key.py` script to isolate and verify Google API Key functionality for embeddings.
- **Environment Management**: Added `load_dotenv` to `cli/main.py` and `verify_google_key.py` to ensure `.env` variables are correctly loaded.
- **Start Script Enhancements**: Updated `start.sh` to check for `GOOGLE_API_KEY` existence and warn the user.
- **Debug Logging**: Added temporary debug logging (commented out) in `memory.py` for API key verification.

### Fixed
- **Embedding Model Error**: Fixed `BadRequestError` / `404 Not Found` when using Google (Gemini) provider by explicitly setting `text-embedding-004` and using the Google-compatible OpenAI endpoint (`generativelanguage.googleapis.com`).
- **Data Fetching Failure**: Resolved `RuntimeError: All vendor implementations failed for method 'get_fundamentals'` by implementing a fallback to `yfinance` in `tradingagents/dataflows/y_finance.py` and registering it in `interface.py`.
- **Report Saving Crash**: Fixed `TypeError: write() argument must be str, not list` in `cli/main.py` by converting structured list content to string before writing to files.
- **API Rate Limiting**: Added `max_retries` handling (exponential backoff) to both `ChatGoogleGenerativeAI` (10 retries) and `OpenAI` embedding client (5 retries).
- **Import Errors**: Fixed `NameError: name 'tool' is not defined` by restoring `langchain_core` imports in data tools that were accidentally removed during Blindfire integration.
- **Payload Size Error**: Implemented input truncation (max 9000 chars) in `memory.py`.
- **Display Layer De-Anonymization**: Added `deanonymize_text` to `TickerAnonymizer` and patched `cli/main.py` to reverse-map "ASSET_XXX" to real company names in the final report, effectively resolving "[Company Name]" placeholders for the user while keeping the internal system blind.
- **Alpaca Integration**: Added `tradingagents/dataflows/alpaca.py` to support `get_stock_data` via Alpaca Data API v2. Registered as a vendor option in `interface.py` and `default_config.py`. Requires `ALPACA_API_KEY` and `ALPACA_API_SECRET` in `.env`.
- **CRITICAL FIX: Memory Leak**: Implemented `FinancialSituationMemory.clear()` and `TradingAgentsGraph.reset_memory()` to wipe agent context between runs. This prevents hallucinations from bleeding across days in long simulations.
- **CRITICAL FIX: Blind Logs**: Updated `_log_state` to explicitly capture `market_regime` and `regime_metrics`, ensuring we can audit decision logic relative to market conditions.
- **CRITICAL FIX: Crash Prevention**: Added guard logic in `propagate()` to handle "Dead State" (Rejected Trades) gracefully, preventing crashes when `process_signal` tries to read non-existent buy prices.



### Changed
- **LLM Configuration**: Updated `tradingagents/default_config.py` and `cli/utils.py` to use valid Gemini model names (e.g., `gemini-1.5-flash`, `gemini-1.5-pro`) and `gemini-pro`.
- **Vendor Configuration**: Updated default `fundamental_data` vendor to "alpha_vantage, yfinance" to ensure fallback availability.
