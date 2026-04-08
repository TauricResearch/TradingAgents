# Pipeline Scoring & Ranking

## Current Understanding
LLM assigns a final_score (0-100) and confidence (1-10) to each candidate.
Score and confidence are correlated but not identical — a speculative setup
can score 80 with confidence 6. The ranker uses final_score as primary sort key.
No evidence yet on whether confidence or score is a better predictor of outcomes.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Is confidence a better outcome predictor than final_score?
- [ ] Does score threshold (e.g. only surface candidates >70) improve hit rate?
