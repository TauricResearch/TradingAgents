# 05 — Gap Analysis

Deliverable 6. Two comparisons: (A) our engine vs **TradingView's** strategy tester (the tool the operator uses daily), and (B) our engine vs **best-in-class** per capability from [04_framework_comparison.md](04_framework_comparison.md). Every gap is mapped to one of the **six architectural constraints** identified in the code inventory, so the roadmap ([13_roadmap.md](13_roadmap.md)) can prioritize by constraint.

## The six constraints (recap)

1. **Single-symbol, single-timeframe jobs** — no portfolio, no multi-TF view in replay.
2. **Bar-driven, no order lifecycle** — no limit/stop-entry orders; ticket `entry_price` ignored.
3. **No sub-minute/tick data** — 1m floor.
4. **GIL-bound single-process jobs** — CPU-serialized, per-instance.
5. **No funding/margin/liquidation, flat slippage** — no spread/impact model.
6. **No strategy SDK, no optimization** — LLM pipeline or rules stand-in; no grid/Bayesian/GA/meta-labeling.

## A. Ours vs TradingView (Pine Script strategy tester)

TradingView is a charting-first retail platform; its strategy tester is what the operator compares against. Where it is genuinely ahead of us, and where we already lead:

| Capability | TradingView | Ours | Gap → constraint |
|---|---|---|---|
| Order types in strategy | `strategy.entry/order/exit` with limit, stop, stop-limit, brackets, OCO-style exits | market-only, `entry_price` ignored | **Gap → C2** |
| Pyramiding | explicit `pyramiding=N` setting | not supported | **Gap → C2** |
| Bar-magnifier (intrabar fills on higher-TF tests) | yes (premium) — fills using a finer timeframe | intrabar stop/TP touch only, no sub-bar fills | **Gap → C2/C3** |
| Deep backtesting (long history) | yes (premium) | full-density, full history within vendor limits | **we lead** (full decision density, zero downsampling) |
| Commission & slippage inputs | configurable commission + slippage (ticks/%) | flat 2bps + 1bp + participation cap | partial — **Gap → C5** (no spread/impact, but we do model liquidity cap) |
| Multi-symbol portfolio test | no (one symbol per strategy) | no | **neither** — not a TV advantage |
| Optimization | limited (manual input scans; no built-in optimizer) | none | roughly even; both weak — **Gap → C6** |
| Risk/exit instrumentation | basic (fixed SL/TP, trailing via code) | R-multiples, breakeven, quality gates, cooldown, scratch-band | **we lead** |
| Reproducible artifacts / decision record | no (results are ephemeral in the tester) | every decision + equity point persisted, evidence record | **we lead** |
| Look-ahead safety | `barmerge`/repainting caveats; user must manage | warmup-safe indicators, documented | **we lead** |

**Reading:** TradingView's real advantages over us are **order types + pyramiding + bar-magnifier fills** (all constraint C2/C3), plus configurable commission/slippage granularity (C5). Everything else — depth of history, risk instrumentation, reproducibility, look-ahead discipline — we already match or lead. TradingView is *not* ahead on portfolio or optimization (it has neither). So "catch TradingView" is a narrow, well-defined target: **the order lifecycle.**

## B. Ours vs best-in-class, by capability

| Capability | Best-in-class | Our state | Gap severity | Constraint |
|---|---|---|---|---|
| Order lifecycle | NautilusTrader / Backtrader (full bracket/OCO/trailing/stop-entry) | market-only, entry_price ignored | **High** | C2 |
| Multi-asset portfolio | LEAN / Nautilus (asset-agnostic) | single-symbol, single-TF | **High** | C1 |
| Optimization | Freqtrade (Optuna), PyBroker (walk-forward), Backtesting.py (grid+SAMBO) | none | **High** | C6 |
| Overfitting guards | PyBroker (bootstrap CIs); *nobody* has purged-CV/deflated-Sharpe/PBO | none | **High (but so is everyone)** — chance to lead | C6 |
| Cost/impact realism | Nautilus / LEAN (fill+slippage+latency) | flat 2bps, participation cap | **Medium** | C5 |
| Funding/margin/liquidation | Freqtrade (crypto funding+leverage), LEAN/Nautilus (margin) | none | **Medium** | C5 |
| Multi-timeframe in one strategy | LEAN, Nautilus | BarReplay rejects >1 TF | **Medium** | C1 |
| Tick/sub-minute data | Nautilus (nanosecond), LEAN (tick) | 1m floor | **Low** (paid-feed dependent; explicit non-goal) | C3 |
| Analytics breadth | QuantStats (50+ metrics) | strong trade/R/MC/regime, missing ratio family | **Medium** | — (additive) |
| ML integration | Freqtrade FreqAI, PyBroker | unwired Q-prototype | **Low** | C6 |
| Strategy SDK/plugin | Backtrader/Nautilus/LEAN (subclass APIs) | none (LLM pipeline / rules) | **High** (unlocks the rest) | C6 |
| Throughput/parallelism | VectorBT (vectorized), Nautilus (Rust) | ~11 dec/s prod, GIL-bound | **Medium** | C4 |
| Risk instrumentation | — | R-ladder/breakeven/gates/cooldown | **we lead** | — |
| Reproducibility/artifacts | — | full-fidelity + streaming + recovery | **we lead** | — |
| Look-ahead discipline | Freqtrade (detectors) | warmup-safe indicators | **we lead/match** | — |

## Priority reading (feeds the roadmap)

Grouping the High-severity gaps by what unlocks the most:

1. **Strategy SDK (C6)** is the keystone — without a pluggable strategy unit, optimization has nothing to optimize and portfolio has nothing to allocate across. Build first.
2. **Order lifecycle (C2)** closes the *only* real TradingView gap and unlocks the two best-documented KB strategy packages (trend-following needs channel entries + pyramiding; momentum needs breakout entries) — see [02_pattern_report.md](02_pattern_report.md).
3. **Optimization + overfitting guards (C6)** — the field-wide hole. Native purged-CV / deflated-Sharpe / PBO would put us *ahead* of every surveyed framework, and it directly serves the honesty culture and the KB's negative-evidence lesson (every blow-up was a risk/validation failure).
4. **Portfolio + multi-TF (C1)** — needed for the CTA package's correlation caps and vol-targeting; larger lift, depends on 1 and 2.
5. **Cost/funding realism (C5)** — medium severity, independent, improves every result's credibility.

Constraints **C3 (tick data)** and **C4 (parallelism)** are deliberately lower priority: C3 is gated on paid feeds (explicit non-goal), and C4 is an optimization-era concern (process-pool per trial) rather than a correctness gap.

## The honest summary

Our engine is **narrow but deep**: best-in-class-adjacent on risk instrumentation, reproducibility, and look-ahead honesty; clearly behind on breadth (single-symbol, market-only, no optimization). The good news from the survey is that **the breadth gaps are well-trodden** — every capability we lack is implemented and documented in at least one open framework, so the architecture ([06_hld.md](06_hld.md)/[07_lld.md](07_lld.md)) is an integration-and-adaptation problem, not research. And the one place *no* framework is strong — statistical overfitting guards — is exactly where our honesty culture and KB evidence point us to lead.
