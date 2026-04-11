# Pipeline Scoring & Ranking

## Current Understanding
LLM assigns a final_score (0-100) and confidence (1-10) to each candidate.
Score and confidence are correlated but not identical — a speculative setup
can score 80 with confidence 6. The ranker uses final_score as primary sort key.

P&L data provides first evidence on score vs. outcome relationship: overall 30d
win rate is only 33.8% despite most recommendations having final_score >= 65.
This suggests the LLM is systematically overconfident — scores in the 65-85 range
do not reliably predict positive outcomes. Strategy identity (which scanner sourced
the candidate) is a stronger predictor than score within that strategy.

## Evidence Log

### 2026-04-11 — P&L review
- 608 total recommendations, 30d win rate 33.8%, avg 30d return -2.9%.
- Score distribution in sample files: most recs scored 65-92. Win rate at 30d is
  33.8% overall — scores in this range are not predictive of positive outcomes.
- Strategy is a stronger predictor than score: social_dd (55% 30d win rate) vs.
  social_hype (15.4% 30d win rate) despite similar score distributions.
- Confidence calibration: scores of 85+ with confidence 8-9 still resulted in
  negative 30d outcomes for insider_buying (-2.05% avg). High confidence scores
  are overconfident across most strategies.
- Exception: minervini picks had 100% 1d win rate (4 data points), suggesting
  score+confidence may be better calibrated for rule-based scanners vs. narrative-based.
- Confidence: medium (need more data to isolate score effect from strategy effect)

## Pending Hypotheses
- [ ] Is confidence a better outcome predictor than final_score?
- [ ] Does score threshold (e.g. only surface candidates >70) improve hit rate?
- [ ] Does per-strategy score normalization help (e.g. social_dd score of 70 > insider score of 85)?
