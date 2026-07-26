# Fund Mode and Web UI MVP

- Status: implemented in commit `47d0263`
- Prepared: 2026-07-21
- Implemented: 2026-07-21
- Working branch: `feat/fund-web-mvp`

This directory records the specification used to implement the MVP. Follow-on
work is specified in `docs/next-phases/`.

## Objective

Add first-class fund analysis to TradingAgents and expose the existing stock,
fund, and crypto workflows through a local browser application.

The first release supports instruments that Yahoo Finance can resolve as an ETF
or mutual fund. Mainland China off-exchange public funds that Yahoo Finance does
not cover are deliberately deferred to a later data-provider integration.

> Historical scope note: Phase 3 now implements a bounded China public-fund
> catalog and provider adapter. See
> [`docs/next-phases/PHASE_3_CHINA_FUNDS.md`](../next-phases/PHASE_3_CHINA_FUNDS.md)
> for the current behavior; the decisions below remain the original MVP record.

## Fixed MVP Decisions

- Preserve the current CLI and Python package behavior.
- Add `fund` as an asset type, with `etf`, `mutual_fund`, and `unknown` subtypes.
- Resolve fund type from Yahoo `quoteType`, with an explicit user override.
- Reuse the existing `fundamentals_report` state slot, but make its analyst and
  label asset-aware. This limits graph and report migration risk.
- Use yfinance as the only fund data provider in this release.
- Build a local single-user web app with FastAPI, React, TypeScript, and Vite.
- Stream analysis progress to the browser with Server-Sent Events (SSE).
- Keep API keys on the backend. Never send or store provider secrets in the
  browser.
- Do not add authentication, multi-user scheduling, a database, or real order
  execution in the MVP.

## Document Map

Read these files in order before implementation:

1. [PRODUCT.md](PRODUCT.md) - user flows, scope, requirements, and acceptance.
2. [ARCHITECTURE.md](ARCHITECTURE.md) - domain model, data semantics, API, SSE,
   backend services, and frontend shape.
3. [IMPLEMENTATION.md](IMPLEMENTATION.md) - branch workflow and ordered tasks.
4. [TESTING.md](TESTING.md) - automated and manual verification gates.
5. [CODEX_HANDOFF.md](CODEX_HANDOFF.md) - ready-to-run Codex assignment.

If documents conflict, the priority is PRODUCT, ARCHITECTURE, IMPLEMENTATION,
TESTING, then CODEX_HANDOFF.

## Repository and Fork Workflow

The current clone uses the long-lived fork as `origin`:

```text
origin   https://github.com/SShending/TradingAgents-web.git
upstream https://github.com/TauricResearch/TradingAgents.git
```

Develop against the fork. Keep `upstream` only for selectively incorporating
official fixes:

```bash
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
```

Feature pull requests target `SShending/TradingAgents-web:main`. Do not open an
upstream pull request unless the owner explicitly decides to contribute a
specific change back to the official project.

## Development Prerequisites

- Python 3.11-3.13; this machine currently provides `python3` 3.12.
- Node.js 20 or newer; this machine currently provides Node 22 and npm 10.
- One configured LLM provider key, or a reachable local Ollama/OpenAI-compatible
  endpoint, for manual end-to-end analysis.
- Network access for live Yahoo Finance and LLM smoke tests.

For a clean development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
cd web
npm ci
```

Never commit `.env`, API keys, generated reports, `node_modules`, or frontend
build output.

## Completion

The implementation is committed and pushed on `feat/fund-web-mvp`. New
development should use the phase documents in `docs/next-phases/` and separate
feature branches after this MVP is merged to the fork's `main`.
