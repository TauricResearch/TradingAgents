---
date: 2026-06-02
updated_by: pi
status: Accepted
type: induced-requirement
---

# Decision: Fixed Schema for Strategy Entry/Exit Rules

**Date:** 2026-06-02
**Updated by:** pi
**Status:** Accepted
**Type:** Induced requirement — emerged from the Phase 1 schema design, not from the original brief.

## Context

The Strategy Intake Pipeline (`briefs/brief-strategy-intake-pipeline.md`, `briefs/epic-strategy-intake-phase1.md`) defines `entry_rules` and `exit_rules` as JSON text columns in the `strategies` table. This is pragmatic for Phase 1 storage but creates a latent defect for Phase 2 backtesting: the backtester must *parse and execute* these rules against price data. Freeform JSON cannot be parsed reliably — `{"rsi": "oversold"}` and `{"indicator": "rsi_14", "threshold": 30, "direction": "crosses_below"}` are both valid JSON but only one is executable.

**This is an induced requirement.** The original design choice (flexible JSON text fields) creates a dependency — a fixed schema — that must be resolved before Phase 1 captures any strategy, otherwise all captured strategies will require retroactive reformatting before Phase 2 can backtest them.

The core heuristic of the pipeline is: *"If you can't write it as a set of IF statements, it's not a strategy."* The rules schema must honour this by being parseable as IF statements.

## Decision

**Define a fixed, minimal schema for `entry_rules` and `exit_rules` before Phase 1 implementation starts.** The `strategies` table still stores JSON text, but the JSON must conform to one of the following shapes. Human input (`trading strategy add`) validates against the schema at entry. LLM extraction (`trading strategy extract`) is prompted to produce schema-conformant output.

### Entry Rules Schema

```typescript
type EntryRule =
  | ThresholdEntry    // Single indicator crossing a threshold
  | CrossEntry        // Two indicators crossing
  | CompositeEntry    // Multiple conditions combined via AND/OR
  | PatternEntry      // Price pattern recognition (stretch — Phase 2+)

interface ThresholdEntry {
  type: "threshold"
  indicator: Indicator
  direction: "above" | "below" | "crosses_above" | "crosses_below"
  value: number
}

interface CrossEntry {
  type: "cross"
  indicator_a: Indicator
  indicator_b: Indicator
  direction: "a_above_b" | "a_below_b" | "crosses_above" | "crosses_below"
}

interface CompositeEntry {
  type: "composite"
  operator: "AND" | "OR"
  conditions: EntryRule[]  // recursive, max depth 2
}

interface PatternEntry {
  type: "pattern"
  pattern: "doji" | "hammer" | "engulfing" | "morning_star" | "evening_star" | "inside_bar" | "outside_bar"
}

type Indicator =
  | { type: "sma"; period: number; source?: "close" | "hl2" | "hlc3" | "ohlc4" }
  | { type: "ema"; period: number; source?: "close" | "hl2" | "hlc3" | "ohlc4" }
  | { type: "rsi"; period: number }
  | { type: "macd"; fast: number; slow: number; signal: number }
  | { type: "bollinger"; period: number; deviations: number; field?: "upper" | "middle" | "lower" }
  | { type: "atr"; period: number }
  | { type: "volume"; period: number }
  | { type: "price"; field: "open" | "high" | "low" | "close" }
  | { type: "adx"; period: number }
  | { type: "stoch"; k_period: number; d_period: number }
```

### Exit Rules Schema

```typescript
type ExitRule =
  | TakeProfitExit
  | StopLossExit
  | TrailingStopExit
  | TimeExit
  | SignalReverseExit
  | CompositeExit

interface TakeProfitExit {
  type: "take_profit"
  method: "fixed_pct" | "atr_multiple" | "indicator"
  value: number                    // pct if fixed_pct, multiplier if atr_multiple
  indicator?: Indicator            // required if method = "indicator"
}

interface StopLossExit {
  type: "stop_loss"
  method: "fixed_pct" | "atr_multiple" | "swing_low" | "indicator" | "volatility"
  value: number                    // pct or multiplier
  indicator?: Indicator
}

interface TrailingStopExit {
  type: "trailing_stop"
  method: "atr_multiple" | "pct_from_high" | "moving_average"
  value: number                    // multiplier or pct
  period?: number                  // for moving_average method
}

interface TimeExit {
  type: "time"
  method: "fixed_days" | "end_of_day" | "end_of_week" | "end_of_month" | "specific_date"
  value: number | string           // days if fixed_days, ISO date if specific_date
}

interface SignalReverseExit {
  type: "signal_reverse"
  condition: EntryRule             // exit when the reverse of this entry condition is met
}

interface CompositeExit {
  type: "composite"
  operator: "AND" | "OR"
  conditions: ExitRule[]           // recursive, max depth 1
}
```

### Minimal Valid Examples

**Entry (threshold):**
```json
{
  "type": "threshold",
  "indicator": { "type": "rsi", "period": 14 },
  "direction": "crosses_below",
  "value": 30
}
```

**Entry (composite):**
```json
{
  "type": "composite",
  "operator": "AND",
  "conditions": [
    {
      "type": "threshold",
      "indicator": { "type": "sma", "period": 50 },
      "direction": "above",
      "value": 200
    },
    {
      "type": "threshold",
      "indicator": { "type": "rsi", "period": 14 },
      "direction": "crosses_below",
      "value": 30
    }
  ]
}
```

**Exit (stop_loss + take_profit):**
```json
{
  "type": "composite",
  "operator": "OR",
  "conditions": [
    {
      "type": "stop_loss",
      "method": "atr_multiple",
      "value": 2
    },
    {
      "type": "take_profit",
      "method": "fixed_pct",
      "value": 5
    }
  ]
}
```

### Backtesting Bridge

Phase 2 (`scripts/py/backtest_strategy.py`) reads `entry_rules` and `exit_rules` from the `strategies` table. The Python backtester parses the JSON into a rule tree and evaluates it against OHLCV data:

```
EntryRule → boolean         (given current bar and indicator state)
ExitRule  → boolean         (given current bar, entry price, and indicator state)
```

The `CompositeEntry` / `CompositeExit` types handle multi-condition strategies. The `Indicator` union handles all indicator computation (`indicator.ts` or Python equivalent).

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Freeform JSON (ad hoc) | Backtester cannot parse arbitrary shapes. `{"rsi": "oversold"}` is not executable. Requires a mini-DSL parser that grows unboundedly as users invent new shapes. |
| DSL string field (e.g. `"RSI(14) < 30 AND SMA(50) > SMA(200)"`) | Parser is its own project. Error messages are opaque. LLM extraction produces non-standard formatting. Validation requires a full expression evaluator. Over-engineered for Phase 1–2. |
| Single indicator only (`indicator_type`, `threshold`, `direction` columns) | Breaks composite strategies — most real strategies have 2–3 conditions. Adding columns per condition creates a sparse, denormalized schema that's worse than JSON. |
| No schema, defer to Phase 2 | Retroactive reformatting of Phase 1 data. All strategies captured before Phase 2 become non-backtestable without manual re-entry. This is the "do nothing" option, and it guarantees rework. |
| Python-side validation only | Allows invalid JSON into the database. CLI and LLM extraction produce unvalidated data. Detection delayed to backtest time, which is the worst possible moment to discover schema violations. |

## Consequences

**What became easier:**
- Phase 2 backtesting engine has a fixed, parseable input format — no heuristics, no guesswork
- LLM extraction prompt can include schema examples, producing conformant output at higher accuracy
- `trading strategy add` can validate entry_rules and exit_rules at input time with clear error messages
- All strategies captured before Phase 2 is built remain backtestable without reformatting
- Schema is versionable — if Phase 3 adds pattern recognition, `EntryRule` grows a `PatternEntry` variant

**What became harder:**
- CLI validation requires a TypeScript schema validator (type guards for each `EntryRule` / `ExitRule` variant)
- LLM extraction prompt must include schema examples — longer prompt, higher token cost
- Human users must input structured JSON rather than natural language — `trading strategy add` will need a guided prompt mode
- Adding a new indicator type requires updating the TypeScript type guard, the Python parser, and the LLM prompt — three places, not one

**Constraints this imposes:**
- `entry_rules` and `exit_rules` JSON in the `strategies` table MUST conform to this schema
- Phase 2 backtester MUST parse these exact shapes — no ad-hoc extensions
- New indicator types require a decision record before addition (schema stability)
- The schema is minimal by design — no volatility surface, no options Greeks, no order book depth. Add only when a real strategy requires it.

## Related

- Brief: `briefs/brief-strategy-intake-pipeline.md` — Section "Functional Requirements → R02" (LLM extraction must produce schema-conformant output)
- Epic: `briefs/epic-strategy-intake-phase1.md` — STRAT-001-S02 (CLI validation), STRAT-001-S04 (LLM extraction prompt)
- Table: `src/server/lib/schema.sql` — `strategies.entry_rules` and `strategies.exit_rules` columns
- Heuristic: "If you can't write it as a set of IF statements, it's not a strategy" — this schema is the IF statement format
