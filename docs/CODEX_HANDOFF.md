# Codex Handoff

Date: 2026-06-07
Branch: `india-market-agents`
Latest phase: Rebrand, India-only validation, India config, and tests

## Project Goal

Transform `TauricResearch/TradingAgents` into `IndiaMarketAgents`: an India-first, India-only institutional market research copilot for Indian listed equities, Indian indices, Indian macro context, Indian filings, Indian market flows, and Indian regulatory/compliance context.

The product is research and decision support only. It must not become a live trading or broker execution system.

## Current Status

- The repo is on branch `india-market-agents`.
- The branch is ahead of `upstream/main`.
- Apache 2.0 license text is present in `LICENSE`.
- Upstream attribution is present in `NOTICE`.
- User-facing package metadata now describes IndiaMarketAgents.
- `README_INDIA.md` install instructions use the IndiaMarketAgents repo name.
- Default config remains India-only with `allow_non_india_tickers=False`.
- India symbol validation rejects US/global/crypto tickers by default, with a tested legacy escape hatch.
- Report path generation uses safe India ticker components and rejects unsafe ticker input.
- Offline tests and CLI smoke checks passed for this phase.

## Completed Phases

1. Documentation bootstrap and audit:
   - Updated future-agent operating rules.
   - Created/updated handoff and audit docs.
   - Kept scope limited to documentation; no heavy refactors.
2. Rebrand, India-only validation, India config, and tests:
   - Rebranded package metadata description and README_INDIA install path.
   - Added regression coverage for default India config, console script aliases, legacy ticker escape hatch, report path safety, and non-interactive report path generation.
   - Kept scope limited to rebrand/config/ticker/report-path behavior; no data-source, agent, or dashboard changes.

Prior local commits indicate earlier IndiaMarketAgents work already exists:

- `feat: add India market dataflow profile`
- `feat: wire IndiaMarketAgents agents and CLI`
- `test: cover IndiaMarketAgents validation and reports`

## Files Touched In Latest Phase

- `README_INDIA.md`
- `docs/CODEX_HANDOFF.md`
- `pyproject.toml`
- `tests/test_env_overrides.py`
- `tests/test_india_cli_report.py`
- `tests/test_india_symbols.py`

## Important Design Decisions

- Keep the internal Python package name `tradingagents` for now to avoid high-risk import churn.
- Use `indiamarketagents` as the user-facing CLI alias.
- Keep default config India-only with explicit escape hatch through config for legacy behavior.
- Keep legacy `tradingagents` console script for compatibility while adding IndiaMarketAgents branding.
- Do not add broker execution or broker integrations.
- Prefer official/user-provided data and explicit unavailable responses over fabricated values.
- Keep live exchange/network tests out of the default test suite.
- Update this file after every phase before committing.

## Baseline Inspection Notes

- `git status` showed a clean worktree before edits.
- `python --version` failed because `python` is not on PATH in this environment.
- Use `python3` for local commands in this workspace unless the environment changes.

## Validation

- `python --version`: failed; `python` is not on PATH.
- `python3 --version`: Python 3.14.5.
- `python3 -m pytest tests/test_india_symbols.py tests/test_env_overrides.py tests/test_india_cli_report.py -q`: 36 passed.
- `python3 -m pip install -e .`: succeeded.
- `git diff --check`: passed.
- `python3 -m pytest -m "not integration" -q`: 336 passed, 1 deselected, 7 warnings, 75 subtests passed.
- `indiamarketagents doctor --ticker RELIANCE.NS`: passed and normalized ticker to `RELIANCE.NS`.
- `indiamarketagents analyze --ticker AAPL --date 2026-06-05 --no-display --no-save-prompt`: failed as expected with India-only ticker rejection before LLM/network work.

## Known Risks And Blockers

- `README.md` still contains a large upstream TradingAgents body after an IndiaMarketAgents preface. This is acceptable for attribution during early phases, but user-facing docs should eventually route more clearly to `README_INDIA.md`.
- Some India data source modules are placeholders or best-effort wrappers. Future phases must verify they fail closed with clear data-quality notes.
- NSE/BSE public endpoints can block automation or change response formats.
- Full package rename would be disruptive and should remain out of scope unless explicitly requested.
- `python` remains unavailable on PATH; use `python3` in this workspace.

## Next Recommended Prompt

Proceed to the next phase: data-source layer hardening. Keep scope limited to local filings, yfinance India wrapper behavior, NSE/BSE unavailable-response placeholders, macro/flows unavailable responses, data-quality rendering, and offline mocked tests. Do not change agent prompts or dashboard in this phase. Update `docs/CODEX_HANDOFF.md` and commit when done.
