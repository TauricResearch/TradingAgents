# Codex Handoff

Date: 2026-06-07
Branch: `india-market-agents`
Latest phase: India analyst prompt and decision-language review

## Project Goal

Transform `TauricResearch/TradingAgents` into `IndiaMarketAgents`: an India-first, India-only institutional market research copilot for Indian listed equities, Indian indices, Indian macro context, Indian filings, Indian market flows, and Indian regulatory/compliance context.

The product is research and decision support only. It must not become a live trading or broker execution system.

## Current Status

- The repo is on branch `india-market-agents`.
- The branch is ahead of `upstream/main`.
- Apache 2.0 license text is present in `LICENSE`.
- Upstream attribution is present in `NOTICE`.
- India analyst prompts now require research-only language, explicit data-quality caveats, and no-fabrication handling for unavailable market, filing, macro, flow, sentiment, and compliance data.
- Downstream Researcher, Research Manager, Trader, Risk, and Portfolio Manager prompts now use research/model-view language and explicitly prohibit order-placement wording, personalized advice, and "execute trade now" language.
- Structured Trader rendering now ends with `FINAL MODEL VIEW` rather than transaction-proposal language.
- Offline tests cover India prompt-language requirements and legacy structured-agent behavior.
- Data-source and dashboard code were intentionally left unchanged in this phase.

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
4. India analyst prompt and decision-language review:
   - Tightened India analyst prompts for research-only output, India-market scope, data-quality caveats, unavailable-source handling, and no fabrication.
   - Revised downstream Researcher, Trader, Risk, and Portfolio prompts where needed to avoid live-trading wording and order-placement instructions.
   - Updated structured Trader schema/rendering terminology from transaction proposal to model research view.
   - Added offline prompt-language tests and isolated legacy structured-agent tests from India-only ticker validation.

Prior local commits indicate earlier IndiaMarketAgents work already exists:

- `feat: add India market dataflow profile`
- `feat: wire IndiaMarketAgents agents and CLI`
- `test: cover IndiaMarketAgents validation and reports`

## Files Touched In Latest Phase

- `docs/CODEX_HANDOFF.md`
- `tests/test_india_prompt_language.py`
- `tests/test_structured_agents.py`
- `tradingagents/agents/analysts/india_compliance_risk_analyst.py`
- `tradingagents/agents/analysts/india_flows_analyst.py`
- `tradingagents/agents/analysts/india_fundamentals_analyst.py`
- `tradingagents/agents/analysts/india_macro_policy_analyst.py`
- `tradingagents/agents/analysts/india_market_analyst.py`
- `tradingagents/agents/analysts/india_news_filings_analyst.py`
- `tradingagents/agents/analysts/india_sentiment_analyst.py`
- `tradingagents/agents/managers/portfolio_manager.py`
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- `tradingagents/agents/risk_mgmt/conservative_debator.py`
- `tradingagents/agents/risk_mgmt/neutral_debator.py`
- `tradingagents/agents/schemas.py`
- `tradingagents/agents/trader/trader.py`

## Important Design Decisions

- Keep the internal Python package name `tradingagents` for now to avoid high-risk import churn.
- Use `indiamarketagents` as the user-facing CLI alias.
- Keep default config India-only with explicit escape hatch through config for legacy behavior.
- Keep legacy `tradingagents` console script for compatibility while adding IndiaMarketAgents branding.
- Third-party yfinance outputs must carry data-quality notes; official/user-provided sources remain preferred.
- PDF extraction stays disabled by default to avoid expensive/OCR-heavy behavior; users should convert key pages to text notes.
- Prompts should describe outputs as research views, model views, or research plans rather than live trading decisions.
- The final structured Trader marker is now `FINAL MODEL VIEW`; preserve this wording for IndiaMarketAgents report and downstream parsing work.
- Legacy/global structured-agent tests should opt into global scope explicitly when they exercise non-India tickers.
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
- `python3 -m pytest tests/test_india_prompt_language.py tests/test_structured_agents.py -q`: 36 passed.
- `git diff --check`: passed.
- `python3 -m pytest -m "not integration" -q`: 362 passed, 1 deselected, 7 warnings, 75 subtests passed.

## Known Risks And Blockers

- `README.md` still contains a large upstream TradingAgents body after an IndiaMarketAgents preface. This is acceptable for attribution during early phases, but user-facing docs should eventually route more clearly to `README_INDIA.md`.
- NSE/BSE official-source modules are still placeholders; they fail closed and need verified endpoints or local-file workflows before use as live sources.
- NSE/BSE public endpoints can block automation or change response formats.
- yfinance remains third-party fallback data, not an official source.
- Some legacy/global prompt text outside the IndiaMarketAgents path may still use transaction-oriented vocabulary; this phase only changed India analyst prompts and downstream prompts needed for India research-only behavior.
- Some schema field names such as `TraderAction` and `TraderProposal.action` remain for compatibility, even though user-facing language now renders as a model view.
- Full package rename would be disruptive and should remain out of scope unless explicitly requested.
- `python` remains unavailable on PATH; use `python3` in this workspace.

## Next Recommended Prompt

Proceed to the next phase: report/disclaimer and saved-artifact review. Keep scope limited to generated report structure, disclaimer placement, source/data-quality coverage in reports, and offline report-writer tests. Do not add data sources, agent prompts, or dashboard changes in this phase. Update `docs/CODEX_HANDOFF.md` and commit when done.
