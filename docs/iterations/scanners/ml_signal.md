# ML Signal Scanner

## Current Understanding
Uses a trained ML model to predict short-term price movement probability. Current
threshold of 35% win probability is worse than a coin flip — the model needs
retraining or the threshold needs raising to 55%+ to be useful. Signal quality
depends heavily on feature freshness; stale features degrade performance.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does raising the threshold to 55%+ improve precision at the cost of recall?
- [ ] Would retraining on the last 90 days of recommendations improve accuracy?
