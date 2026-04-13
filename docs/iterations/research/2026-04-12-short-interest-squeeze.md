# Research: Short Interest Squeeze Scanner

**Date:** 2026-04-12
**Mode:** autonomous

## Summary

Stocks with high short interest (>20% of float) and high days-to-cover (DTC >5) face elevated squeeze
risk when a positive catalyst arrives — earnings beat, news, or unusual options activity. Academic
literature confirms that *decreases* in short interest predict positive future returns (14.6% annualized
for distressed firms), while raw high SI alone is actually a negative long-term indicator. The edge
here is not buying high-SI blindly, but using high SI + catalyst as a squeeze-risk scanner: a
discovery tool that surfaces stocks where short sellers are structurally vulnerable.

## Sources Reviewed

- QuantifiedStrategies (short squeeze backtest): Short squeeze strategies alone backtested poorly —
  rarity and randomness of squeezes prevent a reliable standalone edge
- Alpha Architect (DTC & short covering): DTC is a better predictor of poor returns than raw SI;
  long-short strategy using DTC generated 1.2% monthly return; short covering (SI decrease) signals
  informed belief change
- QuantPedia / academic: SI decrease in distressed firms predicts +14.6% annualized risk-adjusted
  return; short sellers are informed traders whose exit signals conviction shift
- Scanz / practitioner screeners: Consensus thresholds — SI% of float > 10% (moderate), >20%
  (high), DTC > 5 (high squeeze pressure)
- tosindicators.com: "Upcoming earnings with high short interest" scan is a common institutional
  approach — validates the earnings_calendar pending hypothesis
- earnings_calendar.md (internal): Pending hypothesis that SI > 20% pre-earnings produces better
  outcomes; APLD (30.6% SI, score=75) was the strongest recent earnings setup
- social_dd.md (internal): GME scan (15.7% SI, score=56) showed 55% 30d win rate — best 30d
  performer in pipeline

## Fit Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅ | `get_short_interest(return_structured=True)` in `finviz_scraper.py` fully integrated |
| Complexity | trivial | Wrap existing function, map to `{ticker, source, context, priority}` format |
| Signal uniqueness | low overlap | No existing standalone short-interest scanner; social_dd uses SI as one factor among many |
| Evidence quality | qualitative | Academic support for DTC as predictor; practitioner consensus on thresholds |

## Recommendation

**Implement** — The data source is already integrated and the signal fills a genuine gap. The scanner
should NOT simply buy high-SI stocks (negative long-term returns). Instead, it surfaces squeeze
candidates for downstream ranker scoring: stocks where short sellers are structurally vulnerable and
any catalyst could force rapid covering. The ranker then assigns final conviction based on cross-
scanner signals (options flow, earnings, news). This directly addresses the earnings_calendar pending
hypothesis (SI > 20% pre-earnings).

## Proposed Scanner Spec

- **Scanner name:** `short_squeeze`
- **Data source:** `tradingagents/dataflows/finviz_scraper.py` → `get_short_interest(return_structured=True)`
- **Signal logic:**
  - Fetch Finviz tickers with SI > 15% of float, verified by Yahoo Finance
  - CRITICAL: SI >= 30% (extreme squeeze risk — one catalyst away from violent covering)
  - HIGH: SI >= 20% (high squeeze potential — elevated squeeze risk)
  - MEDIUM: SI >= 15% (moderate squeeze potential — worth watching)
  - Context string includes: SI%, DTC if available, squeeze signal label
- **Priority rules:**
  - CRITICAL if `short_interest_pct >= 30` (extreme_squeeze_risk)
  - HIGH if `short_interest_pct >= 20` (high_squeeze_potential)
  - MEDIUM otherwise (moderate_squeeze_potential)
- **Context format:** `"Short interest {SI:.1f}% of float — {signal_label} | squeeze risk if catalyst arrives"`
- **Strategy tag:** `short_squeeze`
