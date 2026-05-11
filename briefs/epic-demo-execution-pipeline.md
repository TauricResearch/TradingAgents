# Epic: Demo Execution Pipeline

**Date:** 2026-05-10
**Epic ID:** DEMO-EXEC-001
**Status:** Closed — superseded by unified registry model
**Priority:** P1
**Stories:** DEMO-EXEC-001-S01 through DEMO-EXEC-001-S05

---

## Vision

Wire the analysis pipeline directly to IG demo execution: run `trading analyze AAPL`, get a trade recommendation, then execute it on the demo account with proper risk management — all without leaving the CLI. The human always confirms, but the friction is minimal.

---

## Background

`trading execute <ticker>` already exists but has gaps:

| Issue | Current | Fixed |
|-------|---------|-------|
| No non-interactive mode | Prompts `[y/N]` | `--yes` flag skips prompt |
| No dry-run | Shows plan but hard to preview | `--dry-run` shows plan + IG order details, exits 0 |
| Stop loss calculation | Hard-coded `atr14 × 1.5` | Use plan's `entry - 2×atr14` |
| No analysis linkage | `trades` table has no `analysis_id` | Link execution to analysis UUID |
| Separate commands | Analyze then execute, two steps | `trading analyze AAPL --execute` chains them |

---

## Stories

### DEMO-EXEC-001-S01: Non-interactive execution

**What:** Add `--yes` flag to `trading execute`.

**Acceptance:**
- `trading execute AAPL --yes` calculates plan, skips confirmation prompt, submits order
- Without `--yes`, behaviour unchanged (prompts as before)
- Exit code 0 on success, 1 on rejection with error message

**Estimate:** 0.5d

---

### DEMO-EXEC-001-S02: Dry-run mode

**What:** Add `--dry-run` flag to `trading execute`.

**Acceptance:**
- Calculates plan and prints full order details (entry, stop, size, limit, epic)
- Calls IG to validate instrument (epic resolution, min size, currency) without placing order
- Exits 0 — no side effects
- Combine with `--yes --dry-run` to validate without executing (useful in CI / scripts)

**Estimate:** 0.5d

---

### DEMO-EXEC-001-S03: Use plan stop loss

**What:** Fix stop loss in IG order payload to use plan values.

**Current broken code:**
```typescript
stopDistance: Math.round(plan.atr14 * 1.5),  // WRONG: uses ATR multiple
```

**Fix:**
```typescript
stopDistance: Math.max(1, Math.round(plan.entry - plan.stopLoss)),  // correct: points from entry
limitDistance: Math.max(1, Math.round(plan.target1 - plan.entry)),
```

**Acceptance:**
- IG order uses `stopDistance` derived from `plan.entry - plan.stopLoss`
- IG order uses `limitDistance` derived from `plan.target1 - plan.entry`
- Values >= 1 point (IG requirement)
- Works for both `BUY` and `SELL` direction

**Estimate:** 0.5d

---

### DEMO-EXEC-001-S04: Analysis linkage

**What:** Store `analysis_id` in `trades` table so we can trace execution back to the analysis that generated it.

**Schema change:**
```sql
ALTER TABLE trades ADD COLUMN analysis_id TEXT;
```

**Acceptance:**
- `trading execute --analysis-id <uuid>` records the link
- `trading analyze AAPL --execute` automatically passes its own analysis UUID
- Query: `SELECT * FROM trades WHERE analysis_id = '<uuid>'` returns the executed trade

**Estimate:** 0.5d

---

### DEMO-EXEC-001-S05: `--execute` on analyze command

**What:** Wire `trading analyze AAPL --execute` to automatically run `trading execute` after analysis completes.

**Behaviour:**
1. Run full TradingAgents analysis → get decision + trade plan
2. Print plan summary to stdout
3. If decision is `BUY` and `--execute` is set: prompt or auto-execute based on `--yes`
4. Store `analysis_id` in trade record

**Acceptance:**
- `trading analyze AAPL --execute --yes` runs analysis then executes on IG demo without further prompts
- `trading analyze AAPL --execute` runs analysis then prompts `[y/N]` before executing
- `--dry-run` on analyze shows plan without executing
- Exit codes propagate: analysis failure → exit 1, execution rejection → exit 1

**Estimate:** 1d

---

## Dependencies

- `src/cli/commands/execute.ts` — existing, modified in S01–S03
- `src/cli/commands/analyze.ts` — modified in S05
- `scripts/py/analyze_stream.py` — analysis UUID exposed via SSE `analysis_id` field
- `src/lib/trade-calculator.ts` — plan values used in S03
- `src/lib/ig-client.ts` — order payload fields

---

## Exit Criteria

- S01: `trading execute AAPL --yes` executes without prompt
- S02: `trading execute AAPL --dry-run` shows plan + IG validation, no order placed
- S03: IG order stopDistance matches `plan.entry - plan.stopLoss` (verified in confirmation)
- S04: `trades` table has `analysis_id` column; execution queries link to analysis
- S05: `trading analyze AAPL --execute --yes` runs analysis + executes in one command

---

## Not in Scope

- Live account execution (demo only)
- Automated re-entry / trailing stops (human manages positions)
- Portfolio-level position tracking (exists separately in `holdings` table)