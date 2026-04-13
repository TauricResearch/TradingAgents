# Minervini Scanner

## Current Understanding
Implements Mark Minervini's SEPA (Specific Entry Point Analysis) criteria: stage 2
uptrend, price above 50/150/200 SMA in the right order, 52-week high proximity,
RS line at new highs. Historically one of the highest-conviction scanner setups.
Works best in bull market conditions; underperforms in choppy/bear markets.

## Evidence Log

### 2026-04-12 — P&L review
- 7 tracked recommendations; 3/3 1-day wins measured, avg +3.68% 1d return.
- No 7d/30d data yet (too recent), but early 1d signal is strongest of all scanners.
- Recent week (Apr 6-12): 7 candidates produced — ALB (×2), AA (×2), AVGO (×2), BAC. Consistent quality signals.
- AA reappeared Apr 8 (score=68) then Apr 12 (score=92) — second appearance coincided with Morgan Stanley upgrade catalyst, showing scanner correctly elevated conviction when confluence added.
- Confidence calibration: Good (cal_diff ≤ 0.8 across all instances).
- Confidence: medium (small sample size, market was volatile Apr 6-12 due to tariff news)

### 2026-04-12 — Fast-loop (2026-04-08 to 2026-04-12)
- minervini was top-ranked in 3 of 5 runs — highest hit-rate at #1 position of any scanner this week.
- AVGO ranked #1 on Apr 10 and Apr 11 (score 85, conf 8 both days) — persistent signal.
- Apr 2026 is risk-off (tariff volatility), yet Minervini setups are still leading. Contradicts bear-market underperformance assumption.
- Apr 12 AA thesis was highly specific: RS Rating 98, Morgan Stanley Overweight upgrade, earnings in 4 days, rising OBV. Good signal clarity.
- Confidence: high

## Pending Hypotheses
- [ ] Does adding a market condition filter (S&P 500 above 200 SMA) improve hit rate? Early evidence (Apr 2026 volatile market, still producing top picks) suggests filtering by market condition may hurt recall.
- [ ] Does a second appearance of the same ticker (persistence across days) predict higher returns than first-time appearances?
- [ ] Do earnings-nearby Minervini setups (within 5 days) underperform? Apr 12 AA has earnings in 4 days — flag for tracking.
