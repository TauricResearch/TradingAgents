---
date: 2026-05-30
updated_by: pi
tags: [brief, markov, regime, hmm]
---

# Brief: Markov Regime Engine — Phase 2 (Stationary, Walk-Forward, HMM)

**Date:** 2026-05-30
**Status:** Draft
**Phase 1:** `briefs/2026-05-20-brief-markov-regime.md` (complete — Steps 1–6, 8)
**Source:** Pham The Anh — "The Quant Secret Weapon: Win Trades Like Clockwork With Markov Chains" (Towards AI / Medium, May 2026)

---

## Objective

Upgrade our Phase 1 observable Markov Chain regime engine from a signal generator to a validated, institution-grade regime detection pipeline. Phase 1 gave us daily regime signals. Phase 2 answers the question Phase 1 cannot: **does this signal actually work, and what regimes are we missing?**

Three deliverables, ordered by dependency:

| # | Deliverable | What it gives us |
|---|---|---|
| A | Stationary distribution | Long-run regime baseline for strategy calibration |
| B | Walk-forward backtest | Empirical proof the signal has predictive power (or doesn't) |
| C | Hidden Markov Model | Data-driven regime discovery — no hand-labeled thresholds |

---

## Operational Heuristic

**"The observable Markov Chain gives you a regime map. The Hidden Markov Model builds that map in real time from noisy signals, without requiring a single manually labeled data point."** — Pham The Anh

And before either can be trusted: **"The walk-forward structure ensures the transition matrix is estimated only from data available at each point in time, preventing lookahead bias. This is the difference between a realistic backtest and one that is guaranteed to disappoint in live trading."**

---

## Background: What Phase 1 Delivered vs. What's Missing

Phase 1 (`src/server/lib/markov/`) implemented Steps 1–6 and 8 of the 10-step framework:

| Step | Description | Phase 1 Status |
|------|-------------|----------------|
| 1 | Define States (Bull/Bear/Sideways, ±5% 20-bar) | ✅ `state.ts` |
| 2 | Compute Today's State | ✅ `classifyState()` |
| 3 | Markov Property (only current state matters) | ✅ implicit |
| 4 | Transition Matrix (MLE from frequency counts) | ✅ `matrix.ts` |
| 5 | Persistence / Stickiness (diagonal) | ✅ `getPersistence()` |
| 6 | N-Day Forecast (P^n via matrix exponentiation) | ✅ `nDayMatrix()` |
| 7 | **Stationary Distribution** (π = πP) | ❌ **Missing** |
| 8 | Signal Generation (P(bull) - P(bear)) | ✅ `signal.ts` |
| 9 | **Walk-Forward Backtesting** | ❌ **Missing** |
| 10 | **Hidden Markov Model** (Baum-Welch + Viterbi) | ❌ **Missing** |

The article is explicit about this hierarchy: Steps 1–6 are the **first-pass model**. Steps 7 and 9 are the **validation layer** that tells you whether to deploy. Step 10 is the **strategic upgrade** — the direction institutional regime-switching models have moved.

### The article's key critique of observable-only Markov Chains

> "You labeled each day as Bull, Bear, or Sideways using rolling returns. But the regime was never directly observable. You reverse engineered it from price. That is not the same thing. A bear regime that has not yet shown up in prices because institutional positioning is quietly shifting beneath the surface is completely invisible to your state labels."

**What HMMs fix:** In an HMM, the true regime is a hidden state. What we observe are returns (and optionally volatility, credit spreads, VIX term structure). Each hidden state generates returns from its own distribution. The model learns both the regime transitions *and* the return distributions simultaneously — without hand-labeled thresholds.

### Multi-dimensional regime space (beyond price-only)

The article explicitly lists four regime types, only one of which Phase 1 implements:

| Regime Type | Indicator | Phase 1 | Phase 2 (HMM) |
|-------------|-----------|---------|---------------|
| Price trend | 20-bar cumulative return | ✅ | Learn latent states from returns alone |
| **Volatility** | Rolling realized volatility | ❌ | Emission variable #2 |
| **Liquidity** | Bid-ask spread, order book depth | ❌ | Potential emission (data-dependent) |
| **Credit** | Credit spreads, cross-asset correlations | ❌ | Potential emission (data-dependent) |

The HMM phase should start with returns-only emission (Gaussian HMM) and leave multi-dimensional emissions as a stretch goal — the article's own Python implementation uses only returns.

---

## Functional Requirements

### FR-A: Stationary Distribution

Compute the long-run equilibrium distribution π where π = π × P.

```typescript
type StationaryDistribution = {
  bull: number;    // long-run proportion of bull days
  sideways: number;
  bear: number;
};

function findStationaryDistribution(m: TransitionMatrix): StationaryDistribution;
```

**Mathematical basis:** Solve (P^T - I)π = 0, with the constraint Σπᵢ = 1. This is a linear system solved via `mathjs.lusolve()` or equivalent.

**Use case:** If the stationary distribution says bear regimes are 12% of all days, a strategy that goes short 40% of the time is structurally misaligned. The stationary distribution is the calibration baseline.

**Edge cases:**
- Singular matrix (reducible chain) → fall back to uniform [1/3, 1/3, 1/3]
- Single-state chain → return [1, 0, 0]
- Verify result sums to 1.0 within 1e-10

### FR-B: Walk-Forward Backtest

Reproduce the article's Part 4 walk-forward structure in TypeScript.

```
For each day T from lookback_window to end of history:
  1. Build transition matrix using ONLY data up to day T (no future data)
  2. Generate signal for day T
  3. Apply signal to day T+1 returns
  4. Advance one day, repeat
```

```typescript
type WalkForwardResult = {
  returns: number[];           // daily strategy returns
  signals: number[];           // raw signal values per day
  cumulativeReturns: number[]; // cumulative equity curve
  sharpe: number;              // annualized Sharpe ratio
  maxDrawdown: number;         // maximum drawdown
  annualReturn: number;        // annualized return
  regimeDistribution: { bull: number; sideways: number; bear: number };
  tradeCount: number;          // number of non-zero signals
  winRate: number;             // percentage of profitable days when positioned
};

function walkForwardBacktest(
  ticker: string,
  lookbackWindow?: number,  // default: 252 trading days (1 year)
  config?: StateConfig,
): WalkForwardResult;
```

**Constraints:**
- No data leakage: matrix at day T uses only data up to T
- Configurable lookback window (shorter = adapts faster, noisier; longer = more stable, lags)
- Threshold for neutral position: |signal| < 0.1 → flat
- Position sizing: signal / 0.3, clamped to [-1, 1]

**Success criteria:** The backtest must produce a Sharpe ratio that can be compared against buy-and-hold. The article's own implementation shows this framework on SPY — we should reproduce comparable metrics.

### FR-C: Hidden Markov Model (Returns-Only)

Implement a Gaussian HMM for 3-state regime discovery using `hmmlearn` via the existing Python bridge (`scripts/py/`). This is the article's Part 6 implementation.

**Why Python and not TypeScript:** The article uses Python's `hmmlearn` library (GaussianHMM). Reimplementing Baum-Welch + Viterbi in TypeScript is a research project in itself. The pragmatic path is a Python script called from Bun via subprocess, matching our existing bridge architecture (`scripts/py/analyze_stream.py`).

```python
# scripts/py/markov_hmm.py — new bridge script
from hmmlearn import hmm
import numpy as np
import json

def fit_market_hmm(returns, n_states=3, n_iter=1000):
    X = np.array(returns).reshape(-1, 1)
    model = hmm.GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=n_iter,
        random_state=42,
    )
    model.fit(X)
    hidden_states = model.predict(X)

    # Sort states by mean return (bull=highest, bear=lowest)
    state_means = {s: np.mean([r for i, r in enumerate(returns) if hidden_states[i] == s])
                   for s in range(n_states)}
    sorted_states = sorted(state_means, key=state_means.get, reverse=True)
    state_map = {old: new for new, old in enumerate(sorted_states)}
    labeled = np.array([state_map[s] for s in hidden_states])

    return {
        "transition_matrix": model.transmat_.tolist(),
        "state_means": [float(returns[labeled == i].mean()) for i in range(n_states)],
        "state_vols": [float(returns[labeled == i].std()) for i in range(n_states)],
        "labeled_states": labeled.tolist(),
        "log_likelihood": float(model.score(X)),
    }
```

**Bridge contract (JSON lines):** Same pattern as `analyze_stream.py` — receive JSON on stdin, emit JSON lines on stdout.

```typescript
// TypeScript side (src/server/lib/markov/hmm.ts)
type HmmResult = {
  transitionMatrix: number[][];  // 3×3 learned transition matrix
  stateMeans: number[];          // mean return per regime
  stateVols: number[];           // volatility per regime
  labeledStates: number[];        // 0=bull, 1=bear, 2=sideways per day
  logLikelihood: number;         // model fit quality
};

async function fitHmm(ticker: string, returns: number[]): Promise<HmmResult>;
async function hmmSignal(ticker: string, lookback?: number): Promise<RegimeSignal>;
```

**Critical implementation notes from the article:**
1. **Baum-Welch finds local maxima, not global.** Always run from multiple random starts (≥5) and keep the model with the highest log likelihood. Single initialization frequently produces suboptimal regime assignments.
2. **GaussianHMM covariance_type="full"** — the article uses full covariance, not diagonal.
3. **State sorting:** After fitting, sort states by mean return so state 0 = bull, state 1 = sideways, state 2 = bear. Otherwise regime labels are arbitrary.

### FR-D: Bayesian Transition Estimation

Replace the MLE point-estimate transition matrix with a Dirichlet-Multinomial Bayesian posterior. This is the article's limitation #3 ("insufficient data for reliable estimation") solved mathematically.

**Why:** The MLE estimator `P̂ = count / total` is a point estimate with no uncertainty measure. Rare transitions (e.g., bear→bull has only 12 observations) produce estimates that look confident when they shouldn't. A Dirichlet prior on each row of the 3×3 matrix gives a full posterior distribution — and, crucially, a measure of *how much to trust the signal*.

**Mathematics (closed-form, no MCMC):**

The Dirichlet is the conjugate prior for the multinomial. After observing transition counts `c = [c₁, c₂, c₃]` from a given state, the prior `Dirichlet(α₁, α₂, α₃)` updates to:

```
Posterior = Dirichlet(α₁ + c₁, α₂ + c₂, α₃ + c₃)
```

With a flat prior `Dirichlet(1, 1, 1)` (no prior opinion), the posterior mean with shrinkage is:

```
E[pⱼ] = (1 + cⱼ) / (3 + Σc)
```

With an informative prior `Dirichlet(20, 5, 5)` (believing bull persists 2/3 of the time), estimates are pulled toward the prior when data is thin and toward the MLE as data accumulates.

**The signal-level payoff:**

Current signal: `signal = P(bull) - P(bear)` — a point estimate.
Bayesian signal: `P(signal > 0)` — the posterior probability that the direction is correct.

```typescript
type BayesianSignal = {
  signalMean: number;        // E[P(bull) - P(bear)]
  signalConfidence: number;  // P(signal > 0) — probability direction is correct
  signalVariance: number;    // Var[P(bull) - P(bear)]
  credibleInterval: [number, number]; // 95% credible interval on signal
};

function bayesianTransitionMatrix(
  counts: number[][],    // 3×3 transition counts
  priorAlphas?: number[], // Dirichlet prior alphas, default [1,1,1]
): {
  posteriorMean: TransitionMatrix;    // shrinkage estimate (replaces MLE)
  posteriorVariance: number[][];      // variance per cell
  effectiveSampleSize: number[][];    // αᵢⱼ + countᵢⱼ (how much data behind each cell)
};

function bayesianSignal(
  counts: number[][],
  currentState: MarketState,
  priorAlphas?: number[],
): BayesianSignal;
```

**How this feeds the stated objective:** We maintain a set of candidate stocks. For each, we accumulate regime state observations over time. The Bayesian model naturally grows more confident as observations accumulate — `P(signal > 0)` starts near 0.5 (coin flip) and converges toward 0 or 1 as the transition counts build. This is the mathematical expression of "watch them over a period until we can be confident a purchase would be worthwhile." The same machinery applies to exits — when `P(bear | current)` rises and the confidence on that probability is high, the exit signal fires with conviction.

**Edge cases:**
- Zero observed transitions from a state → posterior equals prior (shrinkage toward flat or informative)
- All transitions from one state → posterior concentrates (high confidence, low variance)
- Prior specification: default flat `[1,1,1]`, optional informative from stationary distribution

### FR-E: CLI Extension

Extend `src/cli/commands/regime.ts` with new flags:

```bash
trading regime AAPL --backtest        # walk-forward backtest with metrics
trading regime AAPL --hmm             # fit HMM and compare with observable states
trading regime AAPL --stationary      # show stationary distribution
trading regime AAPL --compare         # side-by-side: observable vs HMM regimes
trading regime AAPL --bayesian        # posterior transition matrix with confidence
trading regime AAPL --confidence      # P(signal > 0) for current signal
```

---

## Implementation Architecture

### New files

```
src/server/lib/markov/
  stationary.ts         # FR-A: stationary distribution
  backtest.ts            # FR-B: walk-forward backtest
  hmm.ts                 # FR-C: TypeScript side of HMM bridge
  bayesian.ts            # FR-D: Dirichlet-Multinomial Bayesian estimation

scripts/py/
  markov_hmm.py          # FR-C: Python HMM fitting via hmmlearn
```

### Modified files

```
src/server/lib/markov/index.ts   # Re-export new modules
src/cli/commands/regime.ts        # Add --backtest, --hmm, --stationary, --compare, --bayesian, --confidence flags
```

### Schema additions

```sql
-- Walk-forward backtest results (one row per backtest run)
CREATE TABLE IF NOT EXISTS regime_backtests (
  ticker TEXT NOT NULL,
  run_date TEXT NOT NULL DEFAULT (datetime('now')),
  lookback_window INTEGER NOT NULL,
  sharpe REAL NOT NULL,
  max_drawdown REAL NOT NULL,
  annual_return REAL NOT NULL,
  trade_count INTEGER NOT NULL,
  win_rate REAL NOT NULL,
  bull_pct REAL NOT NULL,
  sideways_pct REAL NOT NULL,
  bear_pct REAL NOT NULL,
  PRIMARY KEY (ticker, run_date)
);

-- HMM fitted models (one row per HMM fit)
CREATE TABLE IF NOT EXISTS regime_hmm_models (
  ticker TEXT NOT NULL,
  fit_date TEXT NOT NULL DEFAULT (datetime('now')),
  n_states INTEGER NOT NULL DEFAULT 3,
  log_likelihood REAL NOT NULL,
  bull_mean REAL NOT NULL,
  bull_vol REAL NOT NULL,
  bear_mean REAL NOT NULL,
  bear_vol REAL NOT NULL,
  sideways_mean REAL NOT NULL,
  sideways_vol REAL NOT NULL,
  transition_matrix_json TEXT NOT NULL,  -- JSON array of arrays
  PRIMARY KEY (ticker, fit_date)
);
```

### Python dependency

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
hmm = ["hmmlearn>=0.3.0"]
```

`hmmlearn` is the standard library for HMMs in Python — it's what the article uses, it's scipy-dependent (already in the tree), and it has zero additional system dependencies beyond numpy/scipy.

---

## Execution Workflow

### Phase A: Stationary Distribution (small, self-contained)

1. Implement `findStationaryDistribution()` in `stationary.ts`
2. Unit tests: known matrix → known stationary distribution
3. Wire into `regime.ts` CLI with `--stationary` flag
4. Compute for SPY, AAPL, QQQ — document long-run regime proportions
5. **Time estimate:** 1 session

### Phase B: Walk-Forward Backtest (moderate, validation-critical)

1. Implement `walkForwardBacktest()` in `backtest.ts`
2. Re-use existing `generateStateStream()` and `buildTransitionMatrix()`
3. Daily loop: slice states[0..T], build matrix, compute signal, record return
4. Store results in `regime_backtests` table
5. CLI: `trading regime AAPL --backtest` outputs metrics table
6. **Time estimate:** 2 sessions

### Phase C: Hidden Markov Model (larger, strategic)

1. Add `hmmlearn` to `pyproject.toml`
2. Write `scripts/py/markov_hmm.py` — JSON-lines bridge
3. Write `src/server/lib/markov/hmm.ts` — TypeScript wrapper
4. Multi-start fitting (5 random seeds → pick max log-likelihood)
5. Store fitted models in `regime_hmm_models` table
6. CLI: `trading regime AAPL --hmm` outputs learned regimes vs. labeled
7. CLI: `trading regime AAPL --compare` side-by-side comparison
8. **Time estimate:** 3 sessions

### Phase D: Bayesian Transition Estimation (small, high-leverage)

1. Implement `bayesianTransitionMatrix()` and `bayesianSignal()` in `bayesian.ts`
2. Unit tests: known counts → known posterior mean and variance
3. Test shrinkage: 0 observations → posterior equals prior; 1000 observations → MLE recovery
4. Test confidence: `P(signal > 0)` ≈ 0.5 with flat prior and no data; converges correctly
5. Wire into `regime.ts` with `--bayesian` and `--confidence` flags
6. Compute confidence intervals for SPY, AAPL, QQQ — identify which signals are actually reliable
7. **Time estimate:** 1 session

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Stationary distribution | Correct for known matrices | Unit test with manually verified π |
| Walk-forward Sharpe | Comparable to buy-and-hold ± meaningful difference | Compare against `trading benchmark` output |
| Walk-forward no lookahead | Matrix at T uses only data ≤ T | Audit: log matrix build dates vs. signal dates |
| HMM log-likelihood | Multiple starts produce different values | Verify multi-start picks max likelihood |
| HMM regime separation | Bear vol > Bull vol (stylized fact) | Verify learned emission parameters |
| HMM vs. observable | HMM regimes differ from ±5% labels | Side-by-side comparison on SPY |
| CLI output | Valid JSON for `--json`, readable for TTY | Test both modes |
| Python bridge | No Rich, no ANSI, JSON lines only | Same contract as `analyze_stream.py` |
| Bayesian posterior mean | Equals prior when no data; recovers MLE with large N | Unit test with 0, 10, 1000 observations |
| Bayesian signal confidence | P(signal > 0) → 0 with flat prior + no data | Verify starts at 0.5 and converges |
| Dirichlet conjugacy | Closed-form — no sampling or iteration needed | Verify posterior computed in O(1) per cell |

---

## Constraints

### Must Have
- TypeScript, Bun-compatible (server-side)
- Python bridge via subprocess (HMM only)
- All matrix ops use `mathjs` (existing dependency)
- Re-use existing `state.ts`, `matrix.ts`, `signal.ts` — do not fork or duplicate
- Walk-forward: zero data leakage (verify with audit log)
- HMM: multi-start fitting (≥5 random seeds)
- CLI: `--json` flag for machine-readable output
- Follows existing brief conventions

### Should Have
- Stationary distribution and walk-forward working before HMM
- Bayesian estimation implemented after walk-forward validates the signal exists
- Walk-forward configurable lookback (shorter = adaptive, longer = stable)
- HMM result comparison vs. observable states in CLI
- Bayesian confidence feeding into position sizing (`signalToPositionSize` scaled by `P(signal > 0)`)

### Complementary Feature: Legendre Polynomial Trend Extraction (Phase 3+)

From Alexzap, "Nonlinear Feature Extraction for Financial Time Series Prediction Using Causal Legendre Polynomials" (Towards AI, May 2026). The core insight: Legendre polynomials on a rolling causal window decompose price into orthogonal shape descriptors with less lag than moving averages.

| LP coefficient | What it captures | Regime application |
|---|---|---|
| a₀ | Local level | Where price sits in recent range |
| a₁ | Local slope | Momentum — richer than raw cumulative return |
| a₂ | Local curvature | Acceleration/deceleration — is the trend strengthening or fading? |

**How it fits:** The current state classifier uses raw 20-bar cumulative return. LP coefficients would give a richer, numerically-stable alternative: classify on a₁ (slope) with a₂ (curvature) providing a confidence modifier. This is purely a feature-engineering enhancement to `state.ts` — it doesn't change the Markov framework or the transition matrix architecture. Reserve for after Phase 2 walk-forward validation confirms the regime signal has merit.

**Not to adopt from the article:** The crossover trading strategy (LP fast/slow trend crossover) is a dressed-up 1970s MA crossover. Its reported 171% out-of-sample CAGR on a 14-month AAPL window is almost certainly overfitting. The extraction method is sound; the strategy is not.

### Complementary Feature: Kelly Position Sizing (Phase 4, post-signal-validation)

From Farid Soroush, "Kelly Criterion vs. Mean-Variance Optimization: A Practical Portfolio Allocation Study" (May 2025). The standard finding: Full Kelly maximizes geometric growth but produces intolerable drawdowns. **Fractional Kelly (0.5×)** balances growth and risk — "maintains high Sharpe while drastically reducing drawdowns."

**How it fits our pipeline:** Markov does *selection* (which stocks have a confident signal?). Kelly does *sizing* (how much of each?). They compose cleanly:

```
Markov regime signal → filter to high-confidence candidates
Bayesian P(signal > 0) → confidence modifier per candidate  
Historical returns μ, Σ → Kelly weight computation
Position size = 0.5 × Kelly_weight × P(signal > 0)
```

**Why it suits a small investor:** Kelly thrives on concentration — its mathematical edge comes from sizing up on conviction, not spreading thin. Institutions can't concentrate; you can. But Fractional Kelly is not optional — the article confirms full Kelly is "practically difficult to tolerate." Half-Kelly with Bayesian confidence scaling is the right formula.

**When:** Reserve for after Phase 2 validates the Markov signal has edge. Kelly allocation on an unvalidated signal is mathematical theatre.

### Complementary Note: Development Philosophy

From Emma Kirsten, "Beating Buy-and-Hold With a Simple Calendar-Based Strategy" (Coding Nexus, Dec 2025). The specific strategy (month-end TLT flows) is bond-specific and not applicable to our equity pipeline. But the development philosophy is worth internalising:

- **Start with market structure, not technical patterns.** The edge should come from institutional behaviour, reporting cycles, or market mechanics — not from fitting indicators to price.
- **Simple rules are easier to stress-test.** Transparent logic exposes fragility early. Complex models hide it.
- **Vectorised thinking forces clarity.** Our Markov pipeline shares this virtue — the transition matrix is a clear, explicit model with no hidden state.

These are principles, not deliverables. Already reflected in how we approach the Markov engine.

### Must Not Have (Phase 2)
- Multi-dimensional HMM (volatility, credit, liquidity as emission variables) — stretch only
- Full Bayesian HMM (MCMC via PyMC/Stan) — Phase 3 at earliest
- Execution/ordering from HMM signals — signals only
- Dashboard/UI for HMM results
- Real-time HMM re-fitting (batch only)
- Position sizing beyond existing `signalToPositionSize()` (except Bayesian confidence scaling in Phase D)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| hmmlearn not installable | Low | Medium | Test install in venv first; fallback to statsmodels `MarkovRegression` if needed |
| Baum-Welch converges to degenerate regime | Medium | High | Multi-start fitting + visual inspection of regime assignments |
| Walk-forward Sharpe ≈ 0 (no edge) | Medium | High | That's useful information — document honestly, consider threshold tuning or dropping the strategy |
| Python bridge JSON parsing errors | Low | Medium | Same battle-tested pattern as `analyze_stream.py` |
| HMM states don't map cleanly to bull/bear/sideways | Medium | Low | Sort by mean return; if regimes are unclear, that's a finding not a bug |

---

## Related

- **Phase 1 Brief:** `briefs/2026-05-20-brief-markov-regime.md` — completed observable Markov Chain implementation
- **Source Article:** [The Quant Secret Weapon: Win Trades Like Clockwork With Markov Chains](https://medium.com/@pta.forwork/the-quant-secret-weapon-win-trades-like-clockwork-with-markov-chains-32dc1f4ee9b3) — Pham The Anh, Towards AI, May 2026
- **Author's HMM Series:** [Market Regime Detection using HMM — Part 1](https://medium.com/@pta.forwork/market-regime-detection-using-hidden-markov-models-in-quantitative-trading-part-1-214e6c77bc2e), [Part 2](https://medium.com/@pta.forwork/market-regime-detection-using-hidden-markov-models-in-quantitative-trading-part-2-09601beacde8)
- **Author's GitHub:** [theanh97](https://github.com/theanh97) — DRL trading, statistical arbitrage, HMM regime detection repos
- **Existing Markov Module:** `src/server/lib/markov/` (state.ts, matrix.ts, signal.ts, regime-data.ts, index.ts)
- **Existing CLI:** `src/cli/commands/regime.ts`
- **Existing Schema:** `src/server/lib/schema.sql` (regime_states, regime_matrices tables)
- **Python Bridge Reference:** `scripts/py/analyze_stream.py` — subprocess + JSON-lines contract pattern
- **Strategy Pipeline:** `briefs/brief-strategy-intake-pipeline.md` — Phase 2 backtesting could feed into this
- **Conventions:** `playbooks/conventions-playbook.md`

---

*Scottish Enlightenment Note: Phase 1 built the engine. Phase 2 asks the question Phase 1 couldn't: "does it actually work?" Walk-forward backtesting is Hume's empiricism applied to trading — we don't believe the signal works because the math is elegant; we believe it because the backtest shows it. And the HMM is our concession that observable states are a map, not the territory. The hidden regimes are the territory.*
