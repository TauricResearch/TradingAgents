# Earnings Calendar Scanner

## Current Understanding
Identifies stocks with earnings announcements in the next N days. Pre-earnings
setups work best when combined with options flow (IV expansion) or insider activity.
Standalone earnings calendar signal is too broad — nearly every stock has earnings
quarterly.

## Evidence Log

### 2026-04-12 — P&L review (earnings_play strategy, 65 tracked recs)
- Note: appears in statistics.json as "earnings_play" not "earnings_calendar". The scanner feeds this strategy.
- Win rates: 38.1% 1d, 37.7% 7d, 46.2% 30d. Avg returns: -0.33% 1d, -2.05% 7d, -2.8% 30d.
- The 30d win rate (46.2%) is better than 7d (37.7%) — unusual pattern suggesting the binary earnings event resolves negatively short-term but some recover.
- Recent runs: 4 candidates (APLD, SLP, FBK, FAST) all scored 60-75 — consistently lowest-scoring scanner in recent runs. APLD (score=75, high short interest 30.6%) is the strongest type of earnings_play setup.
- Avg scores in recent runs: 67 — below the 70 average for other scanners. The ranker is appropriately skeptical of this scanner.
- Confidence: high (65 samples with clear trend)

## Pending Hypotheses
- [ ] Does requiring options confirmation alongside earnings improve signal quality?
- [ ] Does short interest >20% pre-earnings produce better outcomes than <10%? APLD (30.6% SI) scored highest in recent runs — worth tracking.
