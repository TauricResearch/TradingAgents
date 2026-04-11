# Minervini Scanner

## Current Understanding
Implements Mark Minervini's SEPA (Specific Entry Point Analysis) criteria: stage 2
uptrend, price above 50/150/200 SMA in the right order, 52-week high proximity,
RS line at new highs. Historically one of the highest-conviction scanner setups.
Works best in bull market conditions; underperforms in choppy/bear markets.

Early P&L evidence supports the high-conviction thesis: 100% 1d win rate and
+3.68% avg 1d return across 4 data points. No 7d/30d data available yet.
The market condition filter hypothesis remains untested.

## Evidence Log

### 2026-04-11 — P&L review
- 4 recommendations. 1d win rate: 100%. Avg 1d return: +3.68%.
- No 7d or 30d data (positions still open or too recent at time of statistics cut).
- 4 data points is too small to draw conclusions but the signal is encouraging.
- Context: these 4 picks occurred during the broader Feb–Apr 2026 downturn,
  suggesting the Stage 2 uptrend filter is effective at avoiding stocks in decline.
- Confidence: low (4 data points insufficient for statistical significance)

## Pending Hypotheses
- [ ] Does adding a market condition filter (S&P 500 above 200 SMA) improve hit rate?
- [ ] Do RS Rating thresholds (>80 vs >90) meaningfully differentiate outcomes?
