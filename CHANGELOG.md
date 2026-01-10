# Changelog

All notable changes to the **TradingAgents** project will be documented in this file.

## [Unreleased] - 2026-01-09

### Added
- **API Key Verification**: Added `verify_google_key.py` script to isolate and verify Google API Key functionality for embeddings.
- **Environment Management**: Added `load_dotenv` to `cli/main.py` and `verify_google_key.py` to ensure `.env` variables are correctly loaded.
- **Start Script Enhancements**: Updated `start.sh` to check for `GOOGLE_API_KEY` existence and warn the user.
- **Debug Logging**: Added temporary debug logging (commented out) in `memory.py` for API key verification.

### Fixed
- **Embedding Model Error**: Fixed `BadRequestError` / `404 Not Found` when using Google (Gemini) provider by explicitly setting `text-embedding-004` and using the Google-compatible OpenAI endpoint (`generativelanguage.googleapis.com`).
- **Data Fetching Failure**: Resolved `RuntimeError: All vendor implementations failed for method 'get_fundamentals'` by implementing a fallback to `yfinance` in `tradingagents/dataflows/y_finance.py` and registering it in `interface.py`.
- **Report Saving Crash**: Fixed `TypeError: write() argument must be str, not list` in `cli/main.py` by converting structured list content to string before writing to files.
- **API Rate Limiting**: Added `max_retries` handling (exponential backoff) to both `ChatGoogleGenerativeAI` (10 retries) and `OpenAI` embedding client (5 retries) to robustly handle `429 RESOURCE_EXHAUSTED` errors.
- **Payload Size Error**: Implemented input truncation (max 9000 chars) in `memory.py`'s `get_embedding` method to prevent massive payloads from crashing the API.

### Changed
- **LLM Configuration**: Updated `tradingagents/default_config.py` and `cli/utils.py` to use valid Gemini model names (e.g., `gemini-1.5-flash`, `gemini-1.5-pro`) and `gemini-pro`.
- **Vendor Configuration**: Updated default `fundamental_data` vendor to "alpha_vantage, yfinance" to ensure fallback availability.
