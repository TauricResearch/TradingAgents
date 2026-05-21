---
date: 2026-05-21
updated_by: agent
status: Proposed
---

# Decision: TypeScript-only Indicator Library

**Date:** 2026-05-21
**Updated by:** agent
**Status:** Proposed

## Context

SCAN-001 requires computing technical indicators (RSI, Bollinger Bands, MA, ADX, MACD, Volume) for SPY/QQQ/IWM as part of an entry/exit signal scan engine. The codebase has two execution tiers: TypeScript (dashboard, CLI, business logic) and Python (tradingagents core, LLM clients). We needed to decide where indicator computation belongs.

The codebase already has `scripts/py/get_price.py` for price fetching and `tradingagents/` for agent logic. Adding a Python indicator module was one option. The other was to keep indicators in TypeScript alongside the CLI that consumes them.

## Decision

All technical indicator computation lives exclusively in TypeScript (`src/server/lib/indicators.ts`). No Python modules, no external indicator libraries (TA-Lib, pandas-ta), no subprocess calls for math. The CLI (`trading scan`) reads from the TypeScript library directly.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Python indicator module (scripts/py/indicators.py) | Creates a subprocess call from CLI for every scan. The bridge is designed for LLM interaction, not math. Mixing Python for math and TypeScript for logic splits the indicator lifecycle across two files with different tooling. |
| External indicator library (TA-Lib via npm) | Adds a native binary dependency. Installation complexity on different platforms. Also, the algorithms are simple enough to implement in pure TypeScript — no need for a C library. |
| Python with FFI/n bindings | Overkill. We're computing RSI and Bollinger bands, not doing high-frequency trading. |

## Consequences

**What became easier:**
- Zero-dependency indicator functions — just TypeScript math
- Unit testing in the Bun test runner without spinning up Python
- CLI stays in one language — no cross-process calls for signal computation
- Indicators are reusable across CLI and future dashboard routes without rewrites

**What became harder:**
- ADX computation (Wilder's smoothing) is slightly verbose in TypeScript but is correct and readable
- Any future indicator with heavy C-level optimization (e.g., FFT for spectral entropy) would need a different approach

**Constraints this imposes:**
- Indicators must be pure functions — no network calls, no DB access, no side effects
- If a new indicator requires complex math (e.g., wavelet transforms), it should be evaluated for TypeScript feasibility before introducing a Python dependency
- `src/server/lib/indicators.ts` is the canonical location — no reimplementations elsewhere

## Related

- Brief: `briefs/epic-technical-indicators-scan.md`
- Epic: SCAN-001 (td-e7284c)
- ADR: `decisions/006-bifrost-local-ai-router.md` (establishes TypeScript/Python boundary)
- **Updated by:** Git history records author of each change; `updated_by` in frontmatter tracks last modifier.