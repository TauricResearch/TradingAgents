# 12 — Validation Methodology (Anti-Overfitting & Look-Ahead)

Deliverable 12. The place the gap analysis says we can **lead the field** ([05](05_gap_analysis.md): only PyBroker ships bootstrap CIs; *nobody* ships purged CV / deflated Sharpe / PBO). This is also the discipline the KB's negative evidence demands — [03](03_institutional_best_practices.md): every documented blow-up was a risk/validation failure, and our methodology authority (López de Prado, in the KB) is the reference for backtest-overfitting controls. This document defines the standard T3's optimizer must meet.

## Part 1 — Look-ahead audit (correctness before cleverness)

An optimizer that overfits an unbiased backtest is a research problem; an optimizer built on a look-ahead-leaking backtest produces confident fiction. The engine's structural guarantees, and the checklist every new track must pass:

**Already structural (must be preserved, per [07](07_lld.md) invariants):**
- `BarReplay.snapshot_at(i)` exposes bars ≤ i only; fills at i+1 (the decision never sees its fill bar).
- Indicators are warm-up-disciplined; recursive indicators seeded from series start; `indicator_mode` recorded.

**Checklist for each new track:**
1. **Multi-TF (T4):** a higher-TF bar is visible only after its close — assert the merge never exposes a forming HTF bar. Test: at a timestamp mid-HTF-bar, the HTF snapshot's last bar closed strictly before now.
2. **Order fills (T2):** limit/stop fills use only the current bar's OHLC; gap-through fills at the open (pessimistic), never at a within-bar price the strategy couldn't have reached.
3. **Cost/funding (T5):** funding and spread series are sliced with the same as-of rule as bars (no future funding rate leaks into a past accrual).
4. **Corpus context:** `HistoricalCorpus.as_of(ts)` returns records at or before ts (already enforced, data.py:62) — extend the assertion to any new context feed.
5. **Optimization (T3):** the fitting window and the evaluation window never overlap after purge+embargo (Part 2).

## Part 2 — Overfitting protocol

### Purged & embargoed cross-validation
Standard K-fold leaks in time series because adjacent train/test samples share information (a trade opened in-sample can close in-test). Following López de Prado:
- **Purge:** drop training samples whose label/holding window overlaps the test window.
- **Embargo:** additionally drop a small buffer of training samples immediately after the test window (serial correlation).
The split helper in `validation.py` ([07](07_lld.md) T3) implements purge+embargo; the walk-forward driver uses it so no fitted parameter set is ever scored on data that informed it.

### Deflated Sharpe Ratio (DSR)
A Sharpe ratio selected as the best of N trials is upward-biased. DSR adjusts the observed Sharpe for (a) the number of trials, (b) return skew and kurtosis, (c) sample length — yielding the probability the true Sharpe exceeds zero given the selection process. `deflated_sharpe(sharpe, n_trials, skew, kurt, n_obs)` returns that probability; **the optimizer records `n_trials` honestly** (every grid point / random draw counts) so the deflation denominator is real, not gamed.

### Probability of Backtest Overfitting (PBO)
Via combinatorially-symmetric cross-validation (CSCV): partition the trial matrix into train/test combinations, and measure how often the in-sample-best configuration underperforms the test-set median. PBO is the fraction of combinations where that happens. **PBO near 0.5 means the selection has no out-of-sample edge** — the optimizer surfaces PBO next to the "best" params so a high-PBO result is visibly untrustworthy, not silently shipped.

### Reporting standard (enforced, not advisory)
Every optimization result carries, and the UI shows:
- `n_trials` (the real selection count),
- out-of-sample (walk-forward test) performance as the **headline**, in-sample as secondary,
- `deflated_sharpe` and `pbo` alongside the objective,
- a plain-language verdict band (e.g. "PBO 0.52 — no evidence of out-of-sample edge; do not deploy").

This mirrors the existing engine culture: expectancy/avg-R is already the headline over raw return, scratch trades are excluded honestly, and provenance travels with results. DSR/PBO extend that honesty to the *parameter-selection* step.

## Part 3 — A-priori constants policy (unchanged, restated)

The repo's standing rule: strategy constants are chosen a-priori and documented, never curve-fit to a single window, and validation is reported honestly. T3 does not weaken this — it makes tuning **explicit and measured** instead of implicit:
- Any parameter the optimizer tunes must be a *declared* `Param` with a justified range ([10](10_strategy_sdk.md)), not an arbitrary sweep.
- The tuned set is recorded in the run record ([08](08_data_schema.md) `strategy_params`) so any result is reproducible and the search that produced it is auditable.
- Defaults remain the a-priori values (`rules_v1` defaults = today's shipped constants); optimization is opt-in and its output is always accompanied by DSR/PBO.

## Part 4 — What "validated" means for this engine

A strategy result is presentable as evidence of edge only when: (1) it passed the look-ahead checklist for every capability it used; (2) its headline number is out-of-sample (walk-forward test, purged/embargoed); (3) its DSR probability is high and PBO is low, with `n_trials` disclosed; and (4) it survives Monte Carlo (already present) and its drawdown/tail behavior is reported (T6 Ulcer/CVaR). Anything short of that is labeled — exactly as the current engine labels deterministic-rules runs "mechanics only, not an edge measurement."

## Non-goals

- We do not implement live-trading validation here (separate subsystem).
- We do not claim DSR/PBO *prove* edge — they bound the probability that a selected result is spurious. The honest framing ("no evidence of out-of-sample edge" vs "proof of profitability") is itself part of the standard.
