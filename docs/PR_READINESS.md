# PR Readiness Package

Date: 2026-06-07
Branch: `india-market-agents`
Base: `upstream/main`
Branch state: 12 commits ahead of `upstream/main`

## PR Title

Transform TradingAgents into IndiaMarketAgents research copilot foundation

## PR Summary

This branch turns the upstream TradingAgents codebase into the first IndiaMarketAgents foundation: an India-first, India-only research and decision-support copilot for Indian listed equities. It adds India ticker validation, India default configuration, India analyst wiring, defensive data-source placeholders, saved-report hardening, read-only dashboard report review, compliance disclaimers, and offline regression coverage.

The branch explicitly does not add live broker execution, broker integrations, or live trading controls. Missing or unsupported market data is handled through explicit `UNAVAILABLE` and low-confidence paths rather than fabricated values.

## Completed Work

- Added IndiaMarketAgents project docs, handoff, audit, setup, security, compliance, and data-source guidance while preserving Apache 2.0 license and upstream attribution.
- Added India-only ticker validation, India config defaults, CLI rebrand aliases, report path safety, and tests.
- Added India dataflow modules for symbols, calendar, formatting, local filings, yfinance India wrapper behavior, quality metadata, and NSE/BSE/macro/flows unavailable responses.
- Wired India analysts, India tool wrappers, graph execution, CLI defaults, and India report writing.
- Tightened India analyst and downstream Researcher/Trader/Risk/Portfolio language for research-only output, data-quality caveats, and no order-placement wording.
- Hardened saved report artifacts with disclaimers, `sources.md`, `data_quality.json`, standalone section files, and writer-level coverage notes.
- Made the dashboard a read-only saved-report reviewer with optional Streamlit dependency and offline-testable helpers.
- Added security/compliance regressions for tracked generated artifacts, report path validation, fake secret prefixes, and user-facing no-execution wording.

## Validation

- `git status --branch --short`: clean, `india-market-agents...upstream/main [ahead 12]`.
- `python --version`: failed because `python` is not on PATH.
- `python3 --version`: Python 3.14.5.
- `git diff --check`: passed.
- `git grep -n -I -E 'sk-[A-Za-z0-9_-]{8,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY' -- .` with `.env.example*` templates excluded: no matches.
- `git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order'` with audit/test assertion files excluded: no matches.
- `git ls-files | rg '(^reports/|^data/india/filings/|^data/india/manual/|\\.pdf$|__pycache__|\\.pyc$|\\.db$|\\.sqlite$|\\.log$)'`: no matches.
- `python3 -m pytest -m "not integration" -q`: 373 passed, 1 deselected, 7 warnings, 75 subtests passed.

## Remaining Risks

- NSE/BSE official-source modules are still defensive placeholders. They fail closed and need verified public-source workflows before live use.
- yfinance remains a third-party fallback, not an official source.
- README still contains a large upstream TradingAgents body after the IndiaMarketAgents preface; the most direct execution-language issue was removed, but user-facing docs should eventually route more clearly to `README_INDIA.md`.
- Dashboard runtime was not browser-verified in this environment because Streamlit is optional and not installed.
- The internal Python package name remains `tradingagents` to avoid disruptive import churn.

## PR Checklist

- [x] India-only default scope is enforced and tested.
- [x] Legacy/global behavior requires an explicit config escape hatch.
- [x] No broker execution or broker integration was added.
- [x] User-facing report/dashboard language is research-only.
- [x] Missing data paths return explicit unavailable/low-confidence messaging.
- [x] Saved report artifacts include compliance disclaimers and data-quality/source coverage.
- [x] Generated reports, local filings, PDFs, caches, and secrets are ignored and not tracked.
- [x] Offline unit tests pass without API keys or live exchange access.
- [ ] Optional dashboard runtime should be verified after installing `.[dashboard]`.
- [ ] Official NSE/BSE data-source behavior should be implemented only after source/legal/access review.

## Suggested Reviewer Focus

- Confirm India ticker validation and report path safety behavior.
- Review compliance wording in README, README_INDIA, dashboard, CLI reports, and generated artifacts.
- Review unavailable-response and data-quality treatment in India dataflows.
- Review that no live broker/order execution affordance exists.
- Review test coverage around India defaults, report artifacts, dashboard helpers, and security/compliance scans.
