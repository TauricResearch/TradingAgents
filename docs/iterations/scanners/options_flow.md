# Options Flow Scanner

## Current Understanding
Scans for unusual options volume relative to open interest using Tradier API.
Call/put volume ratio below 0.1 is a reliable bullish signal when combined with
premium >$25K. The premium filter is configured but must be explicitly applied.
Scanning only the nearest expiration misses institutional positioning in 30+ DTE
contracts — scanning up to 3 expirations improves signal quality.

P&L data shows options_flow is underperforming at 30d (-2.86% avg, 29% win rate)
despite theoretically strong signal characteristics. Signal quality at 7d is
near-neutral (46.1% win rate), suggesting options flow predicts near-term moves
better than longer-term ones.

## Evidence Log

### 2026-04-11 — P&L review
- 94 recommendations. 1d avg return: +0.03% (near flat). 7d avg: -0.91%. 30d avg: -2.86%.
- 7d win rate 46.1% is best of the poor strategies — nearly coin-flip, meaning the
  direction signal has some validity but not enough edge to overcome transaction costs.
- 30d win rate drops to 29% — options flow signal appears to decay rapidly after ~1 week.
- Sample recommendations show P/C ratios of 0.02–0.48 (wide range); unclear if lower
  P/C ratios (more bullish skew) predict better outcomes within this strategy.
- Hypothesis: the 7-day decay in win rate suggests options flow should be treated as
  a short-horizon signal, not a basis for multi-week holds.
- Confidence: medium

## Pending Hypotheses
- [ ] Does scanning 3 expirations vs 1 meaningfully change hit rate?
- [ ] Is moneyness (ITM vs OTM) a useful signal filter?
- [ ] Does P/C ratio below 0.1 (vs 0.1–0.5) predict significantly better 7d outcomes?
