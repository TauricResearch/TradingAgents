# Brief: Markov Regime Detection Engine

**Date:** 2026-05-20
**Status:** Draft
**Session:** markov-regime-v1

---

## Objective

Build a Markov regime detection engine that classifies market state (bull/bear/sideways) per ticker, maintains a transition probability matrix, and generates directional signals for the trading pipeline.

---

## Background

Based on the "Hedge Fund Method" quant strategy. Core insight: markets exist in discrete states, and state transitions follow a Markov chain. By computing the transition matrix from historical price data, we can:
1. Classify today's state (bull/bear/sideways)
2. Compute probability distribution for tomorrow's state
3. Generate a trading signal: `P(bull) - P(bear)` → direction + magnitude

This is pure math. No indicators, no "feel." It outputs a signal score.

---

## Functional Requirements

### FR-1: State Classification

Given a ticker and a 20-bar lookback window:
- **Bull state:** cumulative return ≥ +5%
- **Bear state:** cumulative return ≤ -5%
- **Sideways state:** cumulative return between -5% and +5%

```typescript
type MarketState = 'bull' | 'bear' | 'sideways';

function classifyState(returns: number[]): MarketState {
  const cumulative = returns.reduce((sum, r) => sum + r, 0);
  if (cumulative >= 0.05) return 'bull';
  if (cumulative <= -0.05) return 'bear';
  return 'sideways';
}
```

### FR-2: Historical State Stream

For any ticker, generate a stream of daily states going back to the earliest available data.

```typescript
type DailyState = {
  ticker: string;
  date: string;        // YYYY-MM-DD
  state: MarketState;
  cumulativeReturn: number;  // 20-bar return for that day
};
```

### FR-3: Transition Matrix

Build a 3×3 transition probability matrix from historical state transitions:
- Rows: today's state (from)
- Columns: tomorrow's state (to)
- Values: `P(next_state | current_state)` — derived from frequency counts

```typescript
type TransitionMatrix = {
  bull_to_bull: number;
  bull_to_sideways: number;
  bull_to_bear: number;
  sideways_to_bull: number;
  sideways_to_sideways: number;
  sideways_to_bear: number;
  bear_to_bull: number;
  bear_to_sideways: number;
  bear_to_bear: number;
};
```

**Persistence diagonal:** The diagonal cells (e.g., `bull_to_bull`) represent state stickiness. Bull and bear markets tend to persist.

### FR-4: N-Day Forecast (Matrix Exponentiation)

For a 2-day forecast, multiply the matrix by itself. For N days, raise to Nth power.

```typescript
function nDayMatrix(matrix: TransitionMatrix, n: number): TransitionMatrix;
```

Note: Probabilities converge to stationary distribution as N increases → diminishing signal.

### FR-5: Signal Generation

Signal for day T = `P(bull | state_T) - P(bear | state_T)`

- Positive → go long (magnitude = signal strength)
- Negative → go short (magnitude = signal strength)
- Zero → neutral

```typescript
type RegimeSignal = {
  ticker: string;
  date: string;
  currentState: MarketState;
  pBull: number;
  pBear: number;
  pSideways: number;
  signal: number;           // pBull - pBear, range [-1, 1]
  signalDirection: 'long' | 'short' | 'neutral';
  signalMagnitude: number;  // absolute value, for position sizing
};
```

### FR-6: Walk-Forward Matrix Update

For daily use: recompute the full transition matrix each day from the complete history up to and including yesterday.

```typescript
async function updateRegimeData(ticker: string): Promise<RegimeSignal>;
```

---

## Implementation Architecture

### Dependencies
- `mathjs` — matrix operations (power, multiply, column access)

### Location
- `src/server/lib/markov/` — module root
- `src/server/lib/markov/state.ts` — FR-1, FR-2
- `src/server/lib/markov/matrix.ts` — FR-3, FR-4 (uses mathjs)
- `src/server/lib/markov/signal.ts` — FR-5, FR-6

### Data Layer

New SQLite table in `schema.sql`:

```sql
CREATE TABLE regime_states (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('bull', 'bear', 'sideways')),
  cumulative_return REAL NOT NULL,
  PRIMARY KEY (ticker, date)
);

CREATE TABLE regime_matrices (
  ticker TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  bull_to_bull REAL NOT NULL,
  bull_to_sideways REAL NOT NULL,
  bull_to_bear REAL NOT NULL,
  sideways_to_bull REAL NOT NULL,
  sideways_to_sideways REAL NOT NULL,
  sideways_to_bear REAL NOT NULL,
  bear_to_bull REAL NOT NULL,
  bear_to_sideways REAL NOT NULL,
  bear_to_bear REAL NOT NULL,
  PRIMARY KEY (ticker, as_of_date)
);
```

### Price Data Dependency

Uses existing price feeds (EODHD or yfinance) via `intel-prices.ts`. No new data source required.

If price data is missing for a ticker: throw, do not estimate.

---

## Execution Workflow

### Step 1: Schema Extension
Add `regime_states` and `regime_matrices` tables to `schema.sql`.

### Step 2: State Classification Module
Implement `classifyState()` and `generateStateStream()` in `state.ts`. Test with synthetic data (known returns → known states).

### Step 3: Matrix Computation Module
Implement `buildTransitionMatrix()` and `nDayMatrix()` in `matrix.ts`. Verify rows sum to 1.0.

### Step 4: Signal Generation Module
Implement `computeSignal()` in `signal.ts`. Verify signal range [-1, 1].

### Step 5: Integration with Intel Prices
Wire `markov/signal.ts` to `intel-prices.ts` for live price fetching.

### Step 6: CLI Interface
Add `cli/commands/regime-check.ts`:
```bash
bun run cli regime AAPL
# Output: current state, matrix, signal score

bun run cli regime AAPL --forecast 2
# Output: 2-day probability distribution
```

### Step 7: HTTP Route (Optional)
`GET /api/regime/:ticker` for dashboard integration (Phase 2, not now).

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| State classification | Correct for known synthetic data | Unit test with 3 known cases |
| Matrix row sums | Exactly 1.0 (per row) | `Math.abs(sum - 1.0) < 1e-10` |
| Signal range | [-1, 1] for all inputs | Boundary test with extreme cases |
| Walk-forward update | Completes in <5s per ticker | Benchmark with 500 days of history |
| Persistence diagonal | Bull/bear > sideways for all tickers tested | Empirically verify on SPY, QQQ |
| CLI output | Valid JSON, no errors | `bun run cli regime AAPL` |

---

## Constraints

### Must Have
- TypeScript, Bun-compatible
- Reads price history from existing `intel-prices.ts`
- Stores state/matrix in SQLite (new tables)
- CLI interface for manual testing
- No external API calls beyond existing price feeds

### Should Have
- Configurable threshold (default +5%, -5%)
- N-day forecast capability

### Must Not Have (Phase 1)
- UI, dashboard, or HTTP routes
- Execution/ordering (signals only, no broker integration)
- Hidden Markov Model (FR-10 from video) — future phase
- Walk-forward backtesting framework — future phase

---

## Testing Plan

### Unit Tests

```typescript
// state.ts
classifyState([0.01, 0.01, ...20 times]) → 'bull'  // 20% return
classifyState([-0.01, -0.01, ...20 times]) → 'bear' // -20% return
classifyState([0.001, -0.001, ...20 times]) → 'sideways'  // ~0% return

// matrix.ts
const m = buildTransitionMatrix(states);
const rowSum = m.bull_to_bull + m.bull_to_sideways + m.bull_to_bear;
Math.abs(rowSum - 1.0) < 1e-10  // true

// signal.ts
const sig = computeSignal(m, 'bull');
// If bull_to_bull = 0.8, bull_to_bear = 0.1, bull_to_sideways = 0.1
// signal = 0.8 - 0.1 = 0.7
assert(sig.signal === 0.7);
assert(sig.signalDirection === 'long');
```

### Integration Test

```bash
# Requires price data for AAPL
bun run cli regime AAPL
# Expect: { ticker: "AAPL", state: "bull|bear|sideways", signal: <-1 to 1> }
```

### Edge Cases

| Input | Expected |
|-------|----------|
| <20 days of history | Throw: "Insufficient history for state classification" |
| Missing price for date | Throw: "Missing price for date T" |
| All same state transitions | Matrix still sums to 1.0 (e.g., always bull→bull) |
| Zero transitions in a category | P = 0, matrix row still sums to 1.0 |

---

## Related

- **Video source:** "I Re-Created A Quant Trading Strategy With Claude Code" (Rowan's hedge fund method)
- **EODHD brief:** `briefs/eodhd-pricing-brief.md` — price data source
- **Future phase:** Hidden Markov Model state discovery (data-driven thresholds)
- **Future phase:** Walk-forward backtesting framework

---

## Not in Scope

- UI/dashboard visualization (PineScript or TS chart)
- Execution layer (broker integration)
- Hidden Markov Model for state discovery
- Walk-forward backtesting
- Multi-ticker batch regime computation (Phase 2)
- Alert integration (regime signals → alerts)

---

*Scottish Enlightenment Note: We build the signal engine first. The question "what do we do with the signal?" is a separate brief. Let the machine learning the matrix before asking it to trade.*