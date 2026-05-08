---
date: 2026-05-07
tags: [playbook, testing, trade-calculator, calculator, verification]
---

# Trade Calculator Testing Playbook

## Purpose

Ensure all trade calculator functions produce mathematically correct and empirically verified output. A calculator error costs real money. Testing is not optional.

---

## The Two-Layer Test Strategy

| Layer | What | When | Data |
|-------|------|------|------|
| **Unit** | Pure functions with synthetic inputs | Every code change | Hand-crafted arrays |
| **Integration** | Full calculator with real price data | Before merge | `prices` table (live market data) |

Never ship calculator changes without both layers passing.

---

## Unit Tests: What to Verify

### 1. ATR (`calculateATR`)

**Test against a known external reference.**

```typescript
// Investopedia example (or TradingView, or manual spreadsheet)
const bars = [
  { date: "2026-01-01", open: 1.2480, high: 1.2500, low: 1.2450, close: 1.2480, volume: 1000 },
  { date: "2026-01-02", open: 1.2530, high: 1.2550, low: 1.2470, close: 1.2530, volume: 1000 },
]
const atr = calculateATR(bars, 1)
expect(atr).toBeCloseTo(0.008, 4) // max(0.0080, 0.0070, 0.0010) = 0.0080
```

**Critical:** Do not invent the expected value. Compute it manually or reference an authoritative source.

### 2. Swing Detection (`findSwingHighLow`)

**Test the algorithm, not your intuition about what the market "should" do.**

```typescript
// Clear AB move: drop to 50, rise to 100
const bars = [
  makeBar("2026-01-01", 80, 85, 75, 80),
  makeBar("2026-01-02", 65, 70, 50, 65),   // swing low
  makeBar("2026-01-03", 95, 100, 90, 95),  // swing high
  makeBar("2026-01-04", 80, 85, 75, 80),
]
const { swingLow, swingHigh } = findSwingHighLow(bars)
expect(swingLow).toBe(50)   // lowest low
expect(swingHigh).toBe(100) // highest high AFTER that low
```

**Common trap:** Expecting global max instead of max-after-min. The algorithm finds Point A (lowest low), then Point B (highest high after Point A).

### 3. Fibonacci Extensions (`fibonacciExtension`)

**Pure math — trivial to verify with a calculator.**

```typescript
const result = fibonacciExtension(50, 100, [1.382, 1.618])
// AB move = 50
// 138.2% = 100 + 50 * 1.382 = 169.1
// 161.8% = 100 + 50 * 1.618 = 180.9
expect(result[0]).toBeCloseTo(169.1, 4)
expect(result[1]).toBeCloseTo(180.9, 4)
```

### 4. Position Sizing (`calculateTradePlan`)

**Test the invariant, not the specific number.**

```typescript
const plan = calculateTradePlan({ ticker: "TEST", priceHistory: bars, accountBalance: 50000, riskPerTrade: 0.02 })

// Invariant 1: risk never exceeds target
expect(plan.riskAmount).toBeLessThanOrEqual(50000 * 0.02)

// Invariant 2: position size is integer
expect(Number.isInteger(plan.positionSize)).toBe(true)

// Invariant 3: targets are ordered
expect(plan.target2).toBeGreaterThan(plan.target1)
expect(plan.target1).toBeGreaterThan(plan.entry)
expect(plan.entry).toBeGreaterThan(plan.stopLoss)

// Invariant 4: R/R > 1 (reward exceeds risk)
const rr = (plan.target2 - plan.entry) / (plan.entry - plan.stopLoss)
expect(rr).toBeGreaterThan(1)
```

### 5. Edge Cases

| Case | Expected |
|------|----------|
| Empty history | Throw immediately |
| <22 days history | `insufficientHistory: true`, but still produce values |
| Zero risk | `positionSize: 0`, `riskAmount: 0` |
| Zero ATR | Use `estimateATR` fallback |
| Negative R/R | Should not happen — verify it doesn't |

---

## Integration Tests: What to Verify

### 1. Real Data Cross-Check

Fetch a known ticker from the `prices` table and verify:

```typescript
const plan = calculateTradePlan({ ticker: "AAPL", priceHistory: aaplBars, accountBalance: 50000, riskPerTrade: 0.02 })

// Verify entry = last close
expect(plan.entry).toBeCloseTo(aaplBars[aaplBars.length - 1].close, 2)

// Verify stop = entry - 2*ATR
expect(plan.stopLoss).toBeCloseTo(plan.entry - 2.0 * plan.atr14, 2)

// Verify ATR is reasonable (not 0, not >50% of price)
expect(plan.atr14).toBeGreaterThan(0)
expect(plan.atr14).toBeLessThan(plan.entry * 0.5)
```

### 2. Monotonicity

Double the account → position should increase (or stay same):

```typescript
const plan50k = calculateTradePlan({ ...base, accountBalance: 50000 })
const plan100k = calculateTradePlan({ ...base, accountBalance: 100000 })
expect(plan100k.positionSize).toBeGreaterThanOrEqual(plan50k.positionSize)
```

### 3. Risk Scaling

Higher risk percentage → higher risk amount:

```typescript
const plan1pct = calculateTradePlan({ ...base, riskPerTrade: 0.01 })
const plan2pct = calculateTradePlan({ ...base, riskPerTrade: 0.02 })
expect(plan2pct.riskAmount).toBeGreaterThanOrEqual(plan1pct.riskAmount)
```

---

## The Rounding Precision Trap

**The bug that integration tests catch:**

The calculator rounds `entry` and `stopLoss` to 2 decimals for display. But `riskAmount` is computed from raw (unrounded) values. If a test recomputes `positionSize * (roundedEntry - roundedStop)`, it will not exactly match `plan.riskAmount`.

**Fix:** Test the invariant (`riskAmount ≤ targetRisk`) not the exact recomputed value. Document the rounding behavior in comments.

---

## When Tests Fail

### Step 1: Check your expectation

The calculator is more likely correct than your mental model. Verify your expected value with:
- A spreadsheet
- TradingView
- A manual calculation on paper

### Step 2: Check the code

If the expectation is correct, find the bug:
- Off-by-one in ATR (using wrong prior close?)
- Wrong swing window (too short? too long?)
- Inverted risk formula (dividing by stop instead of risk?)

### Step 3: Add a regression test

Once fixed, add the failing case as a regression test so it never breaks again.

---

## Test Commands

```bash
# Unit tests only (fast, synthetic data)
just test-trade-calc

# Integration tests (real price data from DB)
just test-trade-calc-integration

# All trade calculator tests
bun test tests/trade-calculator.test.ts tests/trade-calculator-integration.test.ts
```

---

## Checklist Before Merge

- [ ] Unit tests pass (19 tests)
- [ ] Integration tests pass (3 tests)
- [ ] At least one test uses real `prices` table data
- [ ] ATR verified against external reference
- [ ] Position sizing invariant proven: `riskAmount ≤ account * riskPerTrade`
- [ ] Edge cases covered: empty history, insufficient history, zero risk
- [ ] `just check` passes (biome + tsc + db-gate)

---

## Anti-Patterns

### ❌ Testing with only synthetic data

Synthetic bars (flat, linear, perfect AB) validate the formula but not real-world behavior. Always add an integration test with actual market data.

### ❌ Testing exact decimal values

Financial calculations involve rounding. Test invariants and ranges, not exact pennies. Exception: when cross-referencing a known external calculation.

### ❌ Skipping edge cases

What happens when the user has £0? When the stock is halted (ATR=0)? When there are only 5 days of history? These aren't hypothetical — they happen.

---

## References

- `tests/trade-calculator.test.ts` — unit test examples
- `tests/trade-calculator-integration.test.ts` — integration test examples
- `server/lib/trade-calculator.ts` — calculator implementation
- `playbooks/cli-design-playbook.md` — CLI framework standards
