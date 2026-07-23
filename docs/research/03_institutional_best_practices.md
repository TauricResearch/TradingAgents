# 03 — Institutional Best-Practices Synthesis

Deliverable 4. Where [01](01_trader_statistics.md) counts and [02](02_pattern_report.md) finds combinations, this document draws the **design-relevant conclusions**: what does the documented practice of 146 elite traders — and the way institutions manage risk around them — tell us to build into a backtesting engine? Every claim traces to the KB or a cited external practice; nothing is invented orthodoxy.

## The meta-finding: convergence is on risk, divergence is on entry

The single clearest pattern across the whole KB is that **elite traders diverge wildly on how they enter and converge tightly on how they manage risk and exits.** Entry archetypes spread across 20 categories with no majority; but among traders who discuss exits mechanically, trailing exits (23/24), pyramiding winners (19/20), scaling out (16/21), and moving to breakeven (6/6) are near-universal, and every strong co-occurrence pattern ([02](02_pattern_report.md)) bundles a *defined stop* with the entry. The edge is idiosyncratic; the survival discipline is shared. **A backtesting engine should therefore treat risk/exit management as first-class, parameterized, and rigorously simulated, and treat entry logic as pluggable.** This is the through-line of the architecture ([06_hld.md](06_hld.md)).

## Seven best practices the evidence supports

**1. Risk is sized off volatility, not fixed lots.** The highest-support strong pattern (trend_following + volatility_normalized, support 12, lift 4.2) and the sizing distribution (volatility_normalized is the top disclosed model) say elite systematic traders scale by volatility/risk-parity. *Engine implication:* first-class ATR/vol-normalized position sizing (partially present — `fixed_risk_position_size` exists; vol-parity across a portfolio does not).

**2. The stop is defined by where the thesis dies, and it exists before entry.** Structure/swing and pattern-invalidation stops co-occur with chart-pattern entries; ATR stops with channel breakouts. Almost no elite trader in the KB runs without a pre-defined invalidation. *Engine implication:* our invalidation-consistency gate and ATR stop already encode this; the order-lifecycle work should let the stop be *submitted with* the entry as a bracket (T1).

**3. Winners are pyramided; losers are never averaged.** 19/20 disclosers pyramid; the Turtle rules (verified from the published PDF) add ≤4 units at ½N intervals; Baruch's memoir rule "never average losers" recurs as a psychology flag. Adding to winners and refusing to add to losers is a documented discipline, and its violation is a documented killer (LTCM, Niederhoffer). *Engine implication:* the order lifecycle must support scale-in on winners with the stop trailing the aggregate position (T1) — a capability the current single-entry broker lacks.

**4. Portfolio-level caps matter as much as per-trade risk.** Donchian + correlation/exposure filter (lift 8.2); disclosed portfolio-heat caps cluster at 12% (median). The CTAs manage a *book*, capping correlated exposure — not just per-trade risk. *Engine implication:* this is the strongest evidence for the portfolio layer (T3): multi-symbol runs with a correlation/heat cap, which the single-symbol engine cannot express today.

**5. Entries are gated by a regime/market-health read.** Range-breakout + market-health-index (support 9), relative-strength-rotation + market-health (lift 8.1), volatility-event + vol-regime filter (lift 7.0). Across cohorts, elite traders don't take every signal — they take signals *in the right environment*. *Engine implication:* our rule-based regime classifier and ADX chop filter already do a coarse version; the roadmap should wire regime state into strategy context (T6) so a strategy can condition on it, and validate it doesn't leak look-ahead.

**6. Trailing / sell-into-strength exits beat fixed targets for the trend and momentum cohorts.** Trailing (23/24 disclosers) and strength_into_exit (20 profiles) dominate fixed_targets (12). Letting winners run — with a trailing mechanism — is the documented majority behavior among those who exit mechanically. *Engine implication:* trailing stops are a named gap in the current broker ("future work"); this is high-value and evidence-backed (T1).

**7. The negative evidence is as instructive as the positive.** Every blow-up in the KB — LTCM (25× leverage, adding to losers), Niederhoffer (naked puts, no tail hedge, twice), Bruton (premium selling, hid unrealized losses), 3AC (leveraged directional, unmet margin calls), Livermore (violated his own rules, repeated bankruptcies) — is a **risk-management failure, not an entry-signal failure.** None blew up because their entry edge disappeared; they blew up because position sizing, leverage, or tail exposure was unbounded. *Engine implication:* the risk engine's hard, un-overridable gates (daily/drawdown/leverage/heat caps) are the most important realism feature, and the backtester should be able to *demonstrate* a strategy's tail behavior (Monte Carlo, drawdown waterfall, risk-of-ruin — partially present) rather than only its mean return.

## How institutions (not just individuals) manage this

Beyond individual traders, the institutional layer in the KB (CTAs, quant funds, market makers) shows practices worth encoding as engine capabilities or validation standards:
- **Volatility targeting at the fund level** (Winton/AQR/Aspect-style): scale gross exposure to hit a target annualized vol. A portfolio-engine feature (T3), and a more realistic sizing default than fixed-fractional.
- **Purged, out-of-sample validation discipline.** López de Prado (in the KB as a methodology authority) is the reference for backtest-overfitting controls — purged/embargoed CV, the deflated Sharpe ratio, and the probability of backtest overfitting (PBO). These are the anti-overfitting standard the validation methodology adopts ([12_validation_methodology.md](12_validation_methodology.md)).
- **Cost/impact realism.** Market makers earn the spread; anyone backtesting against them must model spread, commission, and market impact honestly or the results are fiction. Our flat-2bps slippage is the weakest realism link (T5).

## What we deliberately do NOT conclude

- We do **not** conclude "the best strategy is trend-following" or any single style. The KB shows *multiple* durable styles; the engine's job is to simulate any of them faithfully, not to pick one.
- We do **not** publish a "recommended risk %." The disclosure data (14%, median 2%, [01](01_trader_statistics.md) §5) does not support a population figure; the engine should make risk-per-trade a first-class, user-set parameter (it already is) and let the operator choose — with the caps as guardrails.
- We do **not** treat retail-course orthodoxy (fixed 1% risk, EMA-200 filters, "83% use a trend filter") as established — the verifiable data contradicts the prevalence of those specifics. The engine should support them as *options*, not bake them in as defaults claimed to be universal.

## Bridge to the architecture

The evidence points to a clear build order, developed in [13_roadmap.md](13_roadmap.md): make **risk/exit management first-class and richly simulated** (trailing stops, pyramiding, brackets, portfolio heat caps, honest costs), keep **entry logic pluggable** (the Strategy SDK, [10_strategy_sdk.md](10_strategy_sdk.md)), and hold the whole thing to an **overfitting-aware validation standard** ([12_validation_methodology.md](12_validation_methodology.md)). The two strategy packages most worth supporting first — systematic trend-following and momentum/growth-equity — are those with the best-documented, most-mechanical, highest-tier exemplars.
