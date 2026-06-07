# Codex Handoff

Date: 2026-06-07
Branch: `india-market-agents`
Latest phase: Documentation bootstrap and repo audit

## Project Goal

Transform `TauricResearch/TradingAgents` into `IndiaMarketAgents`: an India-first, India-only institutional market research copilot for Indian listed equities, Indian indices, Indian macro context, Indian filings, Indian market flows, and Indian regulatory/compliance context.

The product is research and decision support only. It must not become a live trading or broker execution system.

## Current Status

- The repo is on branch `india-market-agents`.
- The branch is ahead of `upstream/main`.
- Apache 2.0 license text is present in `LICENSE`.
- Upstream attribution is present in `NOTICE`.
- `AGENTS.md` now captures India-only scope, no-live-trading rules, data integrity rules, test expectations, and handoff requirements.
- `docs/REPO_AUDIT_INDIA.md` has been refreshed for the current repo state.
- This handoff file was created for phase-by-phase continuity.
- Runtime code was not changed in this phase.

## Completed Phases

1. Documentation bootstrap and audit:
   - Updated future-agent operating rules.
   - Created/updated handoff and audit docs.
   - Kept scope limited to documentation; no heavy refactors.

Prior local commits indicate earlier IndiaMarketAgents work already exists:

- `feat: add India market dataflow profile`
- `feat: wire IndiaMarketAgents agents and CLI`
- `test: cover IndiaMarketAgents validation and reports`

## Files Touched In This Phase

- `AGENTS.md`
- `docs/CODEX_HANDOFF.md`
- `docs/REPO_AUDIT_INDIA.md`

## Important Design Decisions

- Keep the internal Python package name `tradingagents` for now to avoid high-risk import churn.
- Use `indiamarketagents` as the user-facing CLI alias.
- Keep default config India-only with explicit escape hatch through config for legacy behavior.
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
- `python3 -m pytest -m "not integration" -q`: 331 passed, 1 deselected, 7 warnings, 75 subtests passed.

## Known Risks And Blockers

- `README.md` still contains a large upstream TradingAgents body after an IndiaMarketAgents preface. This is acceptable for attribution during early phases, but user-facing docs should eventually route more clearly to `README_INDIA.md`.
- Some India data source modules are placeholders or best-effort wrappers. Future phases must verify they fail closed with clear data-quality notes.
- NSE/BSE public endpoints can block automation or change response formats.
- Full package rename would be disruptive and should remain out of scope unless explicitly requested.

## Next Recommended Prompt

Proceed to the next phase: rebrand + India-only ticker validation + India config + tests. Keep the scope limited to user-facing rebrand, config defaults/env overrides, symbol validation, report path safety, and offline tests. Do not add data sources, agents, or dashboard changes in that phase.
