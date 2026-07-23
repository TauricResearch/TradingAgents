# 15 — Final Recommendation

Deliverable 15, the capstone of the research package. What to build, what to skip, why each enhancement improves realism/robustness/research-productivity, and the open questions for the operator. This document is the executive read; every claim traces to a numbered deliverable.

## The one-paragraph version

Study of 146 verified elite traders shows they **diverge on entry and converge on risk/exit discipline** — every documented blow-up (LTCM, Niederhoffer, 3AC, Bruton, Livermore) was a risk-management or validation failure, not a bad entry signal. Survey of ten backtesting frameworks shows our engine is **narrow but deep**: best-in-class-adjacent on risk instrumentation, reproducibility, and look-ahead honesty; behind only on *breadth* — single-symbol, market-only orders, no optimization. The recommendation is therefore **not** to rebuild: it is to **evolve the engine in place** along six additive tracks, in an order that (1) makes risk/exit management and strategy logic first-class and pluggable, (2) closes the single real TradingView gap (order lifecycle), and (3) invests in the one capability *no* surveyed framework has — statistical overfitting guards — as our differentiator.

## What to build (and why it helps)

| Priority | Build | Improves | Because |
|---|---|---|---|
| 1 | **Strategy SDK + registry** (P0/T1) | research productivity | entry logic is idiosyncratic across the KB ([03](03_institutional_best_practices.md)) → it must be pluggable; and nothing else (optimization, portfolio) is possible without a strategy unit to act on. The keystone. |
| 2 | **Order lifecycle** — limit/stop-entry/bracket/trailing/pyramiding (P1/T2) | realism | the *only* real gap vs TradingView ([05](05_gap_analysis.md) §A); the two best-documented, highest-tier KB strategy packages (trend-following, momentum) literally cannot be expressed without channel/stop entries and pyramiding ([02](02_pattern_report.md)). |
| 3 | **Optimization + overfitting guards** — purged CV, deflated Sharpe, PBO (P2/T3 + [12](12_validation_methodology.md)) | robustness | the field-wide hole: only PyBroker has bootstrap CIs, *nobody* has purged-CV/deflated-Sharpe/PBO ([04](04_framework_comparison.md)/[05](05_gap_analysis.md)). This is where we can be **better than every surveyed framework**, and it directly answers the KB's central lesson (blow-ups are validation failures). |
| 4 | **Portfolio + multi-timeframe** (P3/T4) | realism + breadth | the systematic-CTA class — the most audited, tier-A cohort — trades a *book* with correlation caps and vol-targeting ([02](02_pattern_report.md) Donchian+correlation lift 8.2; [03](03_institutional_best_practices.md) BP4). Single-symbol can't express it. |
| 5 | **Cost/funding realism** (P4/T5) | realism | flat-2bps slippage is our weakest link; market makers earn the spread, so credible relative-value/crypto tests must model spread+impact+funding ([03](03_institutional_best_practices.md) institutional). |
| 6 | **Analytics additions** (P5/T6) | research productivity | reporting parity with QuantStats (Omega/MAR/Ulcer/tail/CVaR/rolling) and the ability to *show* tail behavior, not just mean return ([03](03_institutional_best_practices.md) BP5). |

## What to skip (and why)

- **Tick/sub-minute data** — gated on paid microstructure feeds; the bar engine is honest at 1m. Revisit only on a purchased feed. ([06](06_hld.md) non-goals)
- **A vectorized core rewrite** — incompatible with the event-driven order lifecycle, stop-before-TP pessimism, and per-decision evidence record that are our *strengths*. If sweep speed ever binds after process-pooling, add a vectorized *pre-screen*, never replace the faithful engine. ([11](11_performance_recommendations.md) R5)
- **Distributed multi-node execution** — a process pool on one adequately-sized instance covers foreseeable optimization load; distribute only on measured demand. ([11](11_performance_recommendations.md) R4)
- **Live-execution parity** — a separate safety-gated subsystem; the backtester's job is faithful simulation.
- **Baking in retail orthodoxy** — the verifiable data contradicts "1% risk / 83% trend filter" as universal ([01](01_trader_statistics.md) §7); support these as *options*, never as defaults claimed to be universal.

## Expected gains, stated honestly

These are **qualitative** improvements in the credibility and reach of what the engine can evaluate — not promised performance numbers (the engine simulates; it doesn't create edge):

- **Realism:** strategies can finally be expressed as their authors traded them (resting orders, pyramids, trailing exits, portfolio caps, real costs) — so a backtest result means "this is how the strategy would have behaved," not "this is how a market-only proxy of it behaved."
- **Robustness:** every optimized result carries out-of-sample-as-headline, deflated Sharpe, and PBO with disclosed trial counts — so a result is presentable as evidence of edge *only* when it survives the overfitting gauntlet, and is otherwise labeled untrustworthy rather than shipped.
- **Research productivity:** pluggable strategies + parameter search + richer analytics turn the engine from "run one hand-coded configuration" into "test a strategy family and know which survivors are real."

## Open questions for the operator

1. **Build cadence.** ~65 planning person-days total ([14](14_backlog.md)); P0→P1→P2 (~37 pd) is the differentiating core. Build the core and pause for reassessment, or commit to the full six-track program up front?
2. **Optimization compute.** P2 needs cores the current 1-vCPU prod box lacks ([11](11_performance_recommendations.md) R4). Bigger instance (config change, cheap) or a separate worker service (scalable, infra work)? Affects P2 timing.
3. **Multi-symbol data.** P3 assumes we can source aligned history for the symbols we'd run as a portfolio; today the data layer is BTC/gold-centric. Which symbol universe should the portfolio layer target first?
4. **RL/regime.** The Q-learning prototype is unwired ([05](05_gap_analysis.md)). Integrate it as a strategy under the new SDK (P5.3/P5.4), or formally retire it?
5. **Strategy seeding.** Should we ship reference implementations of the two evidence-backed packages (a `trend_following_v1` Donchian/ATR/pyramid strategy and a `momentum_v1` breakout/health-filter strategy) as first users of the SDK — turning the research directly into runnable strategies?

## Bottom line

The research validates a clear, low-risk path: **evolve, don't rebuild.** Our engine already does the hard, honest things (look-ahead safety, R-accounting, reproducibility) that most frameworks skip; the work is to add the breadth the field has already proven how to build, in an order that front-loads the keystone (Strategy SDK) and the two things that most differentiate us — a real order lifecycle (catches TradingView) and validated optimization (beats the field). The full deliverable set (this package, [README.md](README.md)) gives the evidence, the design, and the sequenced backlog to start P0 whenever the operator is ready.
