# IndiaMarketAgents Agent Guide

## Purpose

IndiaMarketAgents is an India-only institutional market research copilot built as an India-focused fork of `TauricResearch/TradingAgents` under Apache 2.0. The target user is a research analyst covering Indian listed companies, especially pharma, chemicals, oil and gas, and other NSE/BSE-listed companies.

## Non-Negotiables

- Keep the default market scope India-only.
- Preserve Apache 2.0 license text, upstream attribution, and `NOTICE`.
- Do not add live broker order execution.
- Do not integrate Zerodha, Upstox, Angel, Groww, ICICI Direct, or any broker for real order placement.
- If broker integrations are mentioned, keep them mocked, disabled, and clearly marked as future work.
- Treat every output as research and education only, not investment advice.
- Reject US/global/crypto tickers by default unless an explicit config flag allows legacy behavior.
- Do not fabricate market data. Return explicit `UNAVAILABLE`, `NO_DATA_AVAILABLE`, or low-confidence messages when data is missing.
- Prefer official NSE/BSE/company filings and user-supplied files over third-party or scraped sources.
- Respect website terms, rate limits, robots.txt, and public-data limitations.
- Do not commit API keys, tokens, `.env`, caches, local filings, PDFs, generated reports, or secrets.
- Do not delete files or overwrite important user work without approval.
- Be cost effective: prefer local inspection, mocked tests, and cheap validation before live network or LLM calls.

## Phase Workflow

Before editing in any phase:

1. Run `git status`.
2. Run `python --version`; if `python` is unavailable, run `python3 --version` and document the mismatch.
3. Read the relevant repo files before changing them.
4. Keep the phase scope small. Do not perform heavy refactors unless the phase explicitly asks for them.
5. Update `docs/CODEX_HANDOFF.md` before the phase ends.
6. Commit after the phase if possible. If commit is blocked, explain why and provide exact commands for the user.

## Testing Commands

- Install: `python3 -m pip install -e .`
- Offline/unit tests: `python3 -m pytest -m "not integration"`
- All tests: `python3 -m pytest`
- Doctor: `indiamarketagents doctor --ticker RELIANCE.NS`
- Non-India rejection smoke test: `indiamarketagents analyze --ticker AAPL --date 2026-06-05 --no-display --no-save-prompt`

Keep live internet tests behind `@pytest.mark.integration`. Default validation must not require API keys, live exchange access, or paid data.

## Formatting Commands

No dedicated formatter is enforced yet. Keep edits small and consistent with the existing style. If formatting tools are added later, document them here and in `pyproject.toml`.

## Directory Map

- `tradingagents/dataflows/india/`: India symbols, calendar, formatting, source placeholders, local filings, data quality.
- `tradingagents/agents/analysts/india_*.py`: India-specialist analyst prompts.
- `tradingagents/agents/utils/india_market_tools.py`: LangChain tools exposed to India agents.
- `config/india_market_holidays.yml`: explicit verified market holiday overrides.
- `docs/`: India setup, source, compliance, security, audit, and handoff docs.
- `reports/`: generated reports; ignored by git.
- `data/india/filings/`: user-supplied local filings; ignored by git.

## Data Integrity Rules

- Every data block should include source, retrieval/as-of timestamp, coverage, confidence, and limitations where feasible.
- NSE/BSE access must be defensive, timeout-safe, and respectful of public-data limitations.
- If a source is blocked, rate-limited, unsupported, or missing, return `UNAVAILABLE` with a clear next step.
- Do not silently convert USD to INR.
- Use `safe_india_ticker_component()` for report/cache paths.
- Validate India symbols before network calls.
- Do not let agent prompts invent exchange data, filings, FII/DII flows, shareholding, or corporate actions.

## Compliance Requirements

Every CLI, dashboard, README, and generated report must include a research-only disclaimer. Avoid personal-advice language and avoid instructions such as "execute trade now." Use "research view", "model view", "decision-support", and "not financial advice" language.

## Handoff Updates

Update `docs/CODEX_HANDOFF.md` at the end of every phase with:

- Current date and branch.
- Phase completed and commit hash if available.
- Files touched.
- Tests and commands run, including failures.
- Important design decisions.
- Known risks/blockers.
- Next recommended prompt.

Keep the handoff concise and directly useful for the next Codex session.

## Git Expectations

Use small commits with meaningful messages. Run offline tests before final response when practical. Keep the worktree clean after committing unless the user asks otherwise.

## Adding New India Data Sources

1. Add a small source module under `tradingagents/dataflows/india/`.
2. Validate symbols before network calls.
3. Use timeouts, respectful headers, caching, and explicit unavailable responses.
4. Prefer official/user-provided data; do not scrape aggressively.
5. Add a LangChain wrapper in `india_market_tools.py` only after the dataflow function is testable.
6. Add offline unit tests with mocked network responses.
