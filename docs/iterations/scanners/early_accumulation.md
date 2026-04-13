# Early Accumulation Scanner

## Current Understanding
Detects quiet accumulation patterns: rising OBV, price above 50/200 SMA, low ATR
(low volatility), and bullish MACD crossover — without requiring a strong near-term
catalyst. Designed for slow-grind setups rather than explosive moves. The absence of
an immediate catalyst structurally limits the LLM's score assignment, since the ranker
rewards urgency and specificity. This may cause systematic under-scoring relative to
true edge.

## Evidence Log

### 2026-04-12 — Fast-loop (2026-04-12 run)
- Single appearance: FRT (Federal Realty Investment Trust), score=60, conf=6, risk_level=low.
- Thesis: +1.55% daily price move, OBV 12.3M rising, MACD crossover, ATR 1.7% (low risk).
- Score sub-threshold (60 < 65). Key weakness per thesis: "lack of immediate catalysts" and overbought Stochastic (88.7).
- Pattern observation: early_accumulation may be structurally score-capped by ranker's catalyst-weighting. A score of 60 with conf=6 on a low-risk setup may represent miscalibration rather than poor edge.
- 0 mature recommendations (no recommendation generated from this appearance).
- Confidence: low (single data point, no outcome data)

## Pending Hypotheses
- [ ] Does early_accumulation systematically score 55-65 due to ranker penalizing "no catalyst"? If so, the scoring.md penalty logic may need adjustment.
- [ ] Do early_accumulation setups produce better 30d returns than 7d returns (slow-grind nature)?
- [ ] Is the overbought Stochastic reading a reliable short-term timing filter to delay entry?
