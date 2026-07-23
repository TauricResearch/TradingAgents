# 04 — Backtesting Framework Comparison

Deliverable 5. Desk study of ten open-source backtesting frameworks plus our own engine, across 17 dimensions. Machine-readable matrix: [data/frameworks.csv](data/frameworks.csv). Per-framework source notes with citations live in the S5 research files (scratch).

## Method and honesty caveats

- **Desk study only.** Sourced from official docs, GitHub repos/source, and reputable articles (accessed 2026-07-23). Nothing was installed or executed. **No throughput/speed figure here is a benchmark** — every performance claim is labeled a vendor/community claim in the matrix, because we did not run any framework.
- **Our own row is filled from the code inventory** (the S0 capability audit), not marketing — and its one performance figure (~11 decisions/s on a 1-vCPU Cloud Run instance) *is* measured, and labeled as such.
- Star counts, release dates, and adoption numbers reflect page state on the access date and are community/vendor signals, not audited.
- Where a framework's docs didn't confirm a dimension, the matrix says so ("not documented") rather than guessing.

## The landscape in one view

The ten frameworks sort into four functional classes, and no single one is "best" — they optimize for different jobs:

| Class | Frameworks | What they optimize for |
|---|---|---|
| **Production event-driven** | NautilusTrader, QuantConnect LEAN, Backtrader | Realistic order lifecycle, multi-asset, backtest→live parity |
| **Vectorized research-at-scale** | VectorBT, PyBroker, Backtesting.py | Speed over many parameter sets; single-asset or array-of-assets |
| **Crypto-native bot stacks** | Freqtrade, Jesse | Unified backtest→live for one asset class, with funding/leverage |
| **Equity-research / analytics** | Zipline-reloaded, QuantStats | Factor research (Zipline) / performance tearsheets (QuantStats) |

## Dimension-by-dimension, who leads

- **Order lifecycle realism:** NautilusTrader (full bracket/OCO/post-only/reduce-only, nanosecond fidelity) and Backtrader (market/limit/stop/stoplimit/trailing/OCO/bracket) lead. LEAN emulates bracket/OCO. Our engine is at the bottom here: **market-only, next-bar-open, and it ignores the ticket's `entry_price`** — no limit or stop-entry order exists.
- **Multi-asset / portfolio:** LEAN (equities/options/futures/FX/crypto) and NautilusTrader (asset-agnostic multi-venue) lead; VectorBT handles asset arrays. Our engine is **single-symbol, single-timeframe** — the widest gap.
- **Margin / funding / liquidation:** Freqtrade models crypto futures funding+leverage natively; LEAN and Nautilus have margin accounts. Ours has none (spot-only, no funding/liquidation).
- **Cost realism:** Nautilus (fill/slippage/latency models) and LEAN (per-market fee+slippage+fill models) lead. **A recurring weakness across the whole field:** *no* surveyed framework ships a market-impact model, and the crypto bar-loop engines (Freqtrade, Jesse) model no slippage at all. Our flat-2bps slippage is mid-pack for bar engines, weak versus Nautilus/LEAN.
- **Optimization:** Freqtrade (Optuna hyperopt), Jesse (Optuna+MC), Backtesting.py (grid+SAMBO), VectorBT (grid at scale), PyBroker (walk-forward), LEAN (grid+walk-forward) all have something. **Ours has none** — our "walk-forward" is stability windowing with nothing to fit.
- **Overfitting guards — the field-wide hole:** **PyBroker is the only framework with native statistical guards** (walk-forward retraining + BCa-bootstrap confidence intervals on Sharpe/profit-factor/drawdown). Freqtrade ships look-ahead and recursive-bias *detectors*. **Nobody** implements purged/embargoed cross-validation, the deflated Sharpe ratio, or the probability of backtest overfitting (PBO) out of the box. This is the clearest place to *exceed* the field, and it aligns with our KB methodology authority (López de Prado).
- **ML integration:** Freqtrade's FreqAI (built-in retraining) and PyBroker (built around model training) lead. Ours has an unwired tabular-Q prototype.
- **Analytics/reporting:** **QuantStats is the reference** — 50+ metrics and HTML tearsheets. It gives us a concrete porting list (§ below). LEAN and Backtrader have solid built-ins. Ours is strong on trade-level and R-multiple analytics + Monte Carlo + regime/agent attribution, but lacks the standard ratio family QuantStats covers.
- **Live bridge:** LEAN (broad brokerages), Nautilus (multi-venue), Freqtrade/Jesse (crypto), Backtrader (IB/Oanda) all bridge to live. Ours has a gated paper loop, not an engine-level bridge (out of scope by design).
- **License reality for us:** Backtrader (GPL-3.0), Freqtrade (GPL-3.0), Backtesting.py (AGPL-3.0) are copyleft; VectorBT and PyBroker carry Commons Clause restrictions on commercial resale. **Only LEAN, Zipline-reloaded, NautilusTrader (LGPL), Jesse (MIT), and QuantStats (Apache-2.0) are cleanly reusable** — relevant if we ever borrow code rather than ideas. (We are evolving our own engine, so this mainly bounds what we could vendor.)

## What our engine already does *well* relative to the field

The comparison is not one-sided. Our engine leads or matches on:
- **Honest fill pessimism** — stop-checked-before-TP intrabar, next-bar-open entries. Many bar-loop competitors (Freqtrade, Jesse) are less conservative or undocumented on same-bar fill priority.
- **R-multiple + trade-quality accounting** — R-based ladders, breakeven-after-TP1, planned-R:R gates, stop-out cooldown, scratch-band win rate. This is more opinionated risk instrumentation than most competitors ship.
- **Full-fidelity artifacts + streaming** — every decision and equity point persisted, live SSE progress, interrupted-run recovery. Operationally ahead of the research libraries.
- **Look-ahead-safe indicator discipline** — warmup-respecting, documented. Freqtrade is the only competitor shipping explicit lookahead detectors.

So the gap is **not** "our engine is primitive" — it is specifically **breadth** (single-symbol, market-only orders, no optimization) versus our existing **depth** (risk instrumentation, honesty, operational robustness).

## Analytics porting list (from QuantStats, our clearest analytics gap)

Metrics QuantStats computes that our engine currently lacks — candidates for the analytics track ([06_hld.md](06_hld.md) T6): **Omega ratio, tail ratio, CVaR / expected shortfall, Ulcer Index & UPI, gain-to-pain ratio, common-sense ratio, information ratio, adjusted Sortino, Kelly criterion, payoff/profit ratios, rolling versions of Sharpe/Sortino/volatility.** We already have Sharpe/Sortino/Calmar/profit-factor/expectancy/max-drawdown/R-multiples/Monte-Carlo — so this is additive, not a rebuild.

## Bridge to the gap analysis

The dimension leaders above define "best-in-class" per capability; [05_gap_analysis.md](05_gap_analysis.md) measures our engine against them and against TradingView's strategy tester, and maps every gap onto the six architectural constraints from the code inventory.
