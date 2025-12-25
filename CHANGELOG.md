# Changelog

All notable changes to TradingAgents will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- pytest conftest.py hierarchy for organized test fixtures (Issue #49)
  - Root-level conftest.py with shared fixtures (environment variables, LangChain/ChromaDB mocking, configuration)
  - Unit-level conftest.py with data vendor mocking (akshare, yfinance, sample DataFrames)
  - Integration-level conftest.py with live ChromaDB and temporary directory fixtures
  - Fixture scope management (function, session, module) for test isolation and performance
  - Comprehensive docstrings for all fixtures with usage examples and scope documentation
  - pytest.ini configuration with custom markers (unit, integration, e2e, llm, chromadb, slow, requires_api_key)
  - Test suite validating fixture accessibility across test directories [file:tests/test_conftest_hierarchy.py](tests/test_conftest_hierarchy.py)
  - Updated testing documentation with conftest.py hierarchy section [file:docs/testing/README.md](docs/testing/README.md)
  - Fixture usage examples in writing-tests.md [file:docs/testing/writing-tests.md](docs/testing/writing-tests.md)
- Comprehensive documentation structure (Issue #52)
  - Organized `docs/` directory with structured documentation sections
  - Quick start guide at `docs/QUICKSTART.md`
  - Architecture documentation in `docs/architecture/` (multi-agent-system, data-flow, llm-integration)
  - API reference documentation in `docs/api/` (trading-graph, agents, dataflows)
  - Developer guides in `docs/guides/` (adding-new-analyst, adding-llm-provider, adding-data-vendor, configuration)
  - Testing documentation in `docs/testing/` (README, running-tests, writing-tests)
  - Development setup guide in `docs/development/`
  - Central documentation index at `docs/README.md` with navigation and key concepts
  - Updated PROJECT.md DOCUMENTATION MAP section to reference new docs/ structure
  - Added Documentation section to README.md with links to key guides
- Export reports to file with metadata (Issue #21)
  - YAML frontmatter formatting for report metadata [file:tradingagents/utils/report_exporter.py:63-111](tradingagents/utils/report_exporter.py)
  - Report creation with combined YAML frontmatter and markdown content [file:tradingagents/utils/report_exporter.py:112-136](tradingagents/utils/report_exporter.py)
  - Safe filename generation with date prefixes and sanitization [file:tradingagents/utils/report_exporter.py:137-185](tradingagents/utils/report_exporter.py)
  - JSON metadata serialization with datetime handling and directory creation [file:tradingagents/utils/report_exporter.py:186-220](tradingagents/utils/report_exporter.py)
  - Comprehensive report generation combining multiple sections with table of contents [file:tradingagents/utils/report_exporter.py:221-325](tradingagents/utils/report_exporter.py)
  - Support for organizing report sections by team (Analyst, Research, Trading, Portfolio)
  - Datetime-to-ISO-string conversion for YAML/JSON serialization
  - Helper functions for basic YAML formatting when PyYAML is unavailable
  - Comprehensive test suite for all report export functions [file:tests/test_report_exporter.py](tests/test_report_exporter.py)
  - Public API exports in utils/__init__.py for easy access
- Rate limit error handling for LLM APIs (Issue #39)
  - Unified exception hierarchy for handling rate limit errors across providers (OpenAI, Anthropic, OpenRouter) [file:tradingagents/utils/exceptions.py](tradingagents/utils/exceptions.py)
  - Dual-output logging configuration supporting both terminal and file outputs [file:tradingagents/utils/logging_config.py](tradingagents/utils/logging_config.py)
  - Automatic rotating log files with 5MB rotation and 3 backups
  - Terminal logging at INFO level and file logging at DEBUG level
  - API key sanitization in log messages to prevent credential leaks
  - Error recovery utilities for saving partial analysis state on errors [file:tradingagents/utils/error_recovery.py](tradingagents/utils/error_recovery.py)
  - User-friendly error message formatting for rate limit errors [file:tradingagents/utils/error_messages.py](tradingagents/utils/error_messages.py)
  - Comprehensive test suite for exceptions and logging configuration [file:tests/test_exceptions.py](tests/test_exceptions.py) [file:tests/test_logging_config.py](tests/test_logging_config.py)
- AKShare data vendor integration for US and Chinese stock market data (Issue #16)
  - Unified AKShare vendor module with support for both US and Chinese markets [file:tradingagents/dataflows/akshare.py](tradingagents/dataflows/akshare.py)
  - Date format conversion utility for YYYYMMDD compatibility [file:tradingagents/dataflows/akshare.py:34-67](tradingagents/dataflows/akshare.py)
  - Exponential backoff retry mechanism with configurable attempts and delays [file:tradingagents/dataflows/akshare.py:70-108](tradingagents/dataflows/akshare.py)
  - US stock data retrieval via `get_akshare_stock_data_us()` [file:tradingagents/dataflows/akshare.py:114-211](tradingagents/dataflows/akshare.py)
  - Chinese stock data retrieval via `get_akshare_stock_data_cn()` [file:tradingagents/dataflows/akshare.py:213-320](tradingagents/dataflows/akshare.py)
  - Auto-market detection with `get_akshare_stock_data()` for automatic routing [file:tradingagents/dataflows/akshare.py:322-372](tradingagents/dataflows/akshare.py)
  - Rate limit error handling via `AKShareRateLimitError` exception with vendor fallback [file:tradingagents/dataflows/akshare.py:28-30](tradingagents/dataflows/akshare.py)
  - Integration with interface.py vendor routing system [file:tradingagents/dataflows/interface.py](tradingagents/dataflows/interface.py)
  - Comprehensive test suite for all AKShare functions [file:tests/test_akshare.py](tests/test_akshare.py)
- OpenRouter API provider support for unified access to multiple LLM models
  - Support for `provider/model-name` format (e.g., `anthropic/claude-sonnet-4.5`)
  - Proper API key handling with OPENROUTER_API_KEY environment variable
  - Custom headers for OpenRouter attribution (HTTP-Referer, X-Title)
  - Embedding fallback to OpenAI when using OpenRouter (since OpenRouter lacks embeddings)
  - Comprehensive test suite for OpenRouter provider integration [file:tests/test_openrouter.py](tests/test_openrouter.py)
- Expanded .env.example with all supported LLM provider API keys
- Detailed LLM Provider Options section in README.md with examples for:
  - OpenAI (default)
  - Anthropic
  - OpenRouter (new)
  - Google Generative AI
  - Ollama (local)
- OpenRouter configuration example in Python usage section
- Documentation updates in PROJECT.md for OpenRouter support

### Changed
- Updated trading_graph.py LLM provider initialization to handle OpenRouter separately with proper API key and header management [file:tradingagents/graph/trading_graph.py:75-105](tradingagents/graph/trading_graph.py)
- Enhanced memory.py embedding logic to support OpenRouter's embedding fallback behavior [file:tradingagents/agents/utils/memory.py:6-27](tradingagents/agents/utils/memory.py)
- Main.py now includes OpenRouter configuration example (commented out) for easy reference

### Fixed
- ChromaDB collection persistence issue by using `get_or_create_collection()` instead of `create_collection()` to prevent "collection already exists" errors and enable persistent memory across application restarts [file:tradingagents/agents/utils/memory.py:29](tradingagents/agents/utils/memory.py) (Issue #30)
- Improved error messages for missing OPENROUTER_API_KEY when using openrouter provider
- Better embedding client initialization for different LLM providers

---

## [1.0.0] - 2025-01-01 (Example - Update with actual release date)

### Added
- Initial multi-agent trading framework release
- Support for multiple LLM providers
- Analyst team (fundamental, sentiment, news, technical)
- Researcher debate mechanism
- Risk management workflow
- CLI interface
- Integration with financial data APIs

