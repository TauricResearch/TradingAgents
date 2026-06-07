# IndiaMarketAgents Agent Guide

## Purpose

IndiaMarketAgents is an India-only institutional market research copilot built as an India-focused fork of TauricResearch/TradingAgents under Apache 2.0.

## Non-Negotiables

- Keep the default market scope India-only.
- Do not add live broker order execution.
- Do not integrate Zerodha, Upstox, Angel, Groww, ICICI Direct, or any broker for real order placement.
- Treat every output as research and education only, not investment advice.
- Do not fabricate market data. Return explicit unavailable/low-confidence messages when data is missing.
- Prefer official NSE/BSE/company filings and user-supplied files over scraped third-party sources.
- Respect website terms, rate limits, robots.txt, and public-data limitations.
- Do not commit API keys, tokens, `.env`, caches, local filings, or generated reports.
- Do not delete files or overwrite important user work without approval.

## Testing Commands

- Install: `python3 -m pip install -e .`
- Unit tests: `python3 -m pytest -m "not integration"`
- All tests: `python3 -m pytest`
- Doctor: `indiamarketagents doctor --ticker RELIANCE.NS`

## Formatting Commands

No dedicated formatter is enforced yet. Keep edits small and consistent with the existing style. If formatting tools are added later, document them here and in `pyproject.toml`.

## Directory Map

- `tradingagents/dataflows/india/`: India symbols, calendar, formatting, source placeholders, local filings, data quality.
- `tradingagents/agents/analysts/india_*.py`: India-specialist analyst prompts.
- `tradingagents/agents/utils/india_market_tools.py`: LangChain tools exposed to India agents.
- `config/india_market_holidays.yml`: explicit verified market holiday overrides.
- `docs/`: India setup, source, compliance, security, and extension docs.
- `reports/`: generated reports; ignored by git.
- `data/india/filings/`: user-supplied local filings; ignored by git.

## Data Integrity Rules

- Every data block should include source, retrieval/as-of timestamp, coverage, confidence, and limitations where feasible.
- NSE/BSE access must be defensive and timeout-safe. If blocked, return `UNAVAILABLE`.
- Do not silently convert USD to INR.
- Use `safe_india_ticker_component()` for report/cache paths.
- Keep live integration tests behind `@pytest.mark.integration`.

## Compliance Requirements

Every CLI, dashboard, README, and generated report must include a research-only disclaimer. Avoid personal-advice language and avoid instructions such as "execute trade now."

## Git Expectations

Use small commits with meaningful messages. Run offline tests before final response. Keep worktree clean after committing unless the user asks otherwise.

## Adding New India Data Sources

1. Add a small source module under `tradingagents/dataflows/india/`.
2. Validate symbols before network calls.
3. Use timeouts, respectful headers, caching, and explicit unavailable responses.
4. Add a LangChain wrapper in `india_market_tools.py` only after the dataflow function is testable.
5. Add offline unit tests with mocked network responses.
