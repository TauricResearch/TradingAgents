# Codex Handoff

Date: 2026-06-07
Branch: `india-market-agents`
Latest phase: Data-source layer hardening

## Project Goal

Transform `TauricResearch/TradingAgents` into `IndiaMarketAgents`: an India-first, India-only institutional market research copilot for Indian listed equities, Indian indices, Indian macro context, Indian filings, Indian market flows, and Indian regulatory/compliance context.

The product is research and decision support only. It must not become a live trading or broker execution system.

## Current Status

- The repo is on branch `india-market-agents`.
- The branch is ahead of `upstream/main`.
- Apache 2.0 license text is present in `LICENSE`.
- Upstream attribution is present in `NOTICE`.
- Local filing reads now include explicit data-quality coverage and PDF extraction limitations.
- yfinance India wrappers now append source, coverage, confidence, and verification warnings.
- Macro context now emits an explicit `UNAVAILABLE` marker for official macro datapoints in the offline-safe path.
- NSE/BSE and flows placeholders remain fail-closed with unavailable responses and no-fabrication instructions.
- Offline mocked tests cover local filings, yfinance wrappers, NSE/BSE placeholders, macro/flows unavailable behavior, and data-quality rendering.

## Completed Phases

1. Documentation bootstrap and audit:
   - Updated future-agent operating rules.
   - Created/updated handoff and audit docs.
   - Kept scope limited to documentation; no heavy refactors.
2. Rebrand, India-only validation, India config, and tests:
   - Rebranded package metadata description and README_INDIA install path.
   - Added regression coverage for default India config, console script aliases, legacy ticker escape hatch, report path safety, and non-interactive report path generation.
   - Kept scope limited to rebrand/config/ticker/report-path behavior; no data-source, agent, or dashboard changes.
3. Data-source layer hardening:
   - Added current-run data-quality rendering helpers.
   - Hardened local filing output with source coverage, read warnings, and PDF no-OCR caveats.
   - Added yfinance India source notes to make third-party fallback provenance explicit.
   - Added offline tests using temp files and monkeypatched vendors.

Prior local commits indicate earlier IndiaMarketAgents work already exists:

- `feat: add India market dataflow profile`
- `feat: wire IndiaMarketAgents agents and CLI`
- `test: cover IndiaMarketAgents validation and reports`

## Files Touched In Latest Phase

- `docs/CODEX_HANDOFF.md`
- `tests/test_india_data_sources.py`
- `tradingagents/dataflows/india/filings.py`
- `tradingagents/dataflows/india/macro.py`
- `tradingagents/dataflows/india/quality.py`
- `tradingagents/dataflows/india/yfinance_india.py`

## Important Design Decisions

- Keep the internal Python package name `tradingagents` for now to avoid high-risk import churn.
- Use `indiamarketagents` as the user-facing CLI alias.
- Keep default config India-only with explicit escape hatch through config for legacy behavior.
- Keep legacy `tradingagents` console script for compatibility while adding IndiaMarketAgents branding.
- Third-party yfinance outputs must carry data-quality notes; official/user-provided sources remain preferred.
- PDF extraction stays disabled by default to avoid expensive/OCR-heavy behavior; users should convert key pages to text notes.
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
- `python3 -m pytest tests/test_india_data_sources.py tests/test_india_vendor_routing.py tests/test_no_data_handling.py -q`: 16 passed.
- `git diff --check`: passed.
- `python3 -m pytest -m "not integration" -q`: 347 passed, 1 deselected, 7 warnings, 75 subtests passed.

## Known Risks And Blockers

- `README.md` still contains a large upstream TradingAgents body after an IndiaMarketAgents preface. This is acceptable for attribution during early phases, but user-facing docs should eventually route more clearly to `README_INDIA.md`.
- NSE/BSE official-source modules are still placeholders; they fail closed and need verified endpoints or local-file workflows before use as live sources.
- NSE/BSE public endpoints can block automation or change response formats.
- yfinance remains third-party fallback data, not an official source.
- Full package rename would be disruptive and should remain out of scope unless explicitly requested.
- `python` remains unavailable on PATH; use `python3` in this workspace.

## Next Recommended Prompt

Proceed to the next phase: India analyst prompt and decision-language review. Keep scope limited to India analyst prompts plus downstream Researcher/Trader/Risk/Portfolio prompts where needed for research-only language, India context, data-quality caveats, and no live-trading wording. Do not add data sources or dashboard changes in this phase. Update `docs/CODEX_HANDOFF.md` and commit when done.
