# Social DD Scanner

## Current Understanding
Identifies speculative momentum setups driven by high social sentiment scores and
elevated short interest (potential short squeeze). Despite a speculative surface-level
profile, early P&L data shows 55% 30d win rate and the only scanner positive at 30d
(+0.94% avg 30d return). This DIVERGES from `social_hype` (14.3% 7d win rate) —
`social_dd` likely includes more fundamental corroboration (short interest, OBV, MACD)
versus pure social sentiment. Current ranker prompt groups them together, which may be
incorrect. Setups currently score below 65 and are filtered by the score threshold.

## Evidence Log

### 2026-04-12 — Fast-loop (2026-04-08 run)
- Single appearance: GME, score=56, conf=5, risk_level=speculative.
- Thesis: Social DD score 75/100 + 15.7% short interest + bullish MACD crossover.
- Score sub-threshold (56 < 65). Negative signals in thesis: weak fundamentals (-13.9% revenue growth), insider selling $330k.
- **Critical context from scoring.md P&L review**: social_dd historically shows 55% 30d win rate, +0.94% avg 30d — the only scanner positive at 30d. This suggests the scanner has real edge but requires a longer holding period than 1-7 days.
- Current ranker prompt groups social_dd with social_hype as "SPECULATIVE" — this may cause social_dd to be systematically under-scored, suppressing a legitimate slow-win strategy.
- 0 mature recommendations from discovery pipeline (no recommendation generated from this appearance).
- Confidence: medium (outcome data from scoring.md gives P&L context, but very few appearances in discovery pipeline)

## Pending Hypotheses
- [ ] Does the ranker's "social_dd / social_hype → SPECULATIVE" grouping suppress social_dd scores, causing us to miss 30d winners?
- [ ] Should social_dd get a separate ranker treatment from social_hype, given divergent 30d outcomes?
- [ ] At what social score threshold (>75? >85?) does the setup reliably score ≥65 to generate recommendations?
