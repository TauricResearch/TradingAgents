# David's TradingAgents Fork Changelog

This changelog tracks changes that are specific to David's TradingAgents fork.
The upstream project changelog remains in the repository root `CHANGELOG.md`.

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
