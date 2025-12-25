# Changelog

All notable changes to TradingAgents will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

