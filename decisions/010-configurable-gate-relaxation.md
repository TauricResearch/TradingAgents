---
date: 2026-05-21
updated_by: agent
status: Accepted
---

# Decision: Configurable Entry Gates with --relax Flags

**Date:** 2026-05-21
**Updated by:** agent
**Status:** Proposed

## Context

The scan engine evaluates six entry gates (RSI < 30, Bollinger support, MA20 > price, ADX > 20, MACD histogram positive, Volume confirmation) before signaling BUY. All six must pass for a signal. During iteration, testing, and live trading, we need the ability to evaluate the system with a subset of gates — either to isolate which condition is failing, or to deliberately relax conditions when the market regime changes.

A hardcoded strict mode would be brittle. A fully configurable rule engine (JSON DSL, YAML config) would be overengineering for six conditions.

## Decision

Each entry gate can be independently disabled via a `--relax=GATE` flag on the `trading scan` CLI. Multiple `--relax` flags can be combined. Gates are identified by short name: `rsi`, `bollinger`, `ma20`, `adx`, `macd`, `volume`.

The 150-day MA filter (price > MA150) is always enforced and cannot be relaxed — it is the structural trend guard, not a market-noise filter.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| YAML/JSON config file (scan.yml) with gate definitions | Adds file I/O, config drift risk, and a new file to maintain. Overkill for six static conditions. |
| Environment variables (SCAN_RELAX=rsi,macd) | Scatters configuration across the shell environment. Hard to track what was relaxed in a given run. Not user-friendly for interactive use. |
| Hardcoded strict mode (no relaxation) | Prevents iteration, testing, and live adaptation. We will need to relax gates during live trading as market conditions change — this needs to be a first-class feature, not a hack. |

## Consequences

**What became easier:**
- Can test signal frequency by relaxing gates one at a time
- Live trading can adapt to different market regimes by relaxing specific gates (e.g., skip ADX filter in choppy markets)
- Debugging a failed signal — run with `--relax=ma20 --relax=adx` to see if other gates would have fired
- Clear CLI UX: `--relax=rsi` is self-documenting

**What became harder:**
- The `--relax` flag adds CLI complexity — must document which gates are relaxable
- Users may overuse `--relax` and disable the system's protective filters

**Constraints this imposes:**
- `--relax` flags are additive — each unique gate name can appear once
- Unknown gate names produce a clear error (not silently ignored)
- Default behavior (no `--relax` flags) must be the strict all-6-gates mode

## Related

- Brief: `briefs/epic-technical-indicators-scan.md`
- Epic: SCAN-001 (td-e7284c)
- Story: SCAN-001-S02 (td-3faad7) — scan CLI command
- ADR: `decisions/009-typescript-indicator-library.md` (establishes pure TS indicator approach)
- **Updated by:** Git history records author of each change; `updated_by` in frontmatter tracks last modifier.