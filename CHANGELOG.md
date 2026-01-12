# Changelog

All notable changes to the **TradingAgents** project will be documented in this file.

## [Unreleased] - 2026-01-11

### Added
- **Gemini 2.0 & 3.0 Support**: Updated `cli/utils.py` to support `gemini-2.0-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-3-flash-preview` and `gemini-3-pro-preview` models.
- **Console Debugging**: Added explicit console print statements for critical "Smoking Gun" debug traces in `market_analyst.py` and `trading_graph.py`.

### Fixed
- **Override Logic Mismatches**: Fixed critical Enum-to-String type mismatch in `apply_trend_override` that was silencing the "Safety Valve" logic.
- **Data Pipeline Failures**: Injected robust error handling and type checking in `market_analyst.py` to identify why `RegimeDetector` receives invalid data (causing "UNKNOWN" regimes).
- **Gemini 404 Errors**: Removed invalid/deprecated model names causing 404s.

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
