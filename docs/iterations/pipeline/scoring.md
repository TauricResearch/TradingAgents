# Pipeline Scoring & Ranking

## Current Understanding
LLM assigns a final_score (0-100) and confidence (1-10) to each candidate.
Score and confidence are correlated but not identical — a speculative setup
can score 80 with confidence 6. The ranker uses final_score as primary sort key.
No evidence yet on whether confidence or score is a better predictor of outcomes.

## Evidence Log

### 2026-04-12 — Cross-scanner calibration analysis
- All scanners show tight calibration: avg score/10 within 0.5 of avg confidence across all scanners. No systemic miscalibration.
- The current `min_score_threshold=55` in `discovery_config.py:52` allows borderline candidates (GME social_dd score 56, TSLA options_flow 60, FRT early_accumulation 60) into final rankings.
- These low-scoring picks carry confidence 5-6 and are explicitly speculative. Raising threshold to 65 would eliminate them without losing high-conviction picks.
- insider_buying has 136 recs — only 1 below score 60 (score 50-59 bucket had 1 entry). Raising to 65 would trim ~15% of insider picks (the 20 in 60-69 range).
- Confidence: medium

## Pending Hypotheses
- [ ] Is confidence a better outcome predictor than final_score?
- [x] Does score threshold >65 improve hit rate? → Evidence supports it: low-score candidates are weak (social sentiment without data, speculative momentum). Implement threshold raise to 65.

### 2026-04-12 — P&L outcome analysis (mature recs, 2nd iteration)
- news_catalyst: 0% 7d win rate, -8.79% avg 7d return (7 samples). Worst performing strategy by far.
- social_hype: 14.3% 7d win rate, -4.84% avg 7d, -10.45% avg 30d (21-22 samples). Consistent destroyer.
- social_dd: surprisingly best long-term: 55% 30d win rate, +0.94% avg 30d return — only scanner positive at 30d.
- minervini: best short-term signal but small sample (n=3 for 1d tracking).
- **Critical gap confirmed**: `format_stats_summary()` shows only top 3 best strategies. LLM never sees news_catalyst (0% 7d) or social_hype (14.3% 7d) as poor performers.
- Confidence: high
