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

### 2026-04-13 — Statistical analysis (n=25 picks)
- Avg score: 71.5 — most picks (22/25) already score ≥65. Ranker suppression is an outlier case, not systematic.
- 7d win rate: 41.7%, avg 7d return: -1.92% — poor short-term.
- 30d win rate: 60.0%, avg 30d return: +2.32% — confirmed slow-win profile.
- High-conf (≥7, n=9): 30d win rate 55.6% — high confidence does not add meaningful edge over base rate.
- **Key insight**: the evaluation horizon mismatch is the real issue. Downstream recommendation scoring and ranker calibration use 7d outcomes, which penalize social_dd unfairly. The scanner works — but only at 30d.
- Confidence: high (n=25, consistent with prior 55% 30d finding)

### 2026-04-14 — P&L review (updated statistics, n=26)
- 30d win rate: 57.1% (12/21 wins), avg 30d return: +1.41% — confirmed improvement from prior 55%/+0.94% reading.
- 7d win rate: 44.0%, avg 7d return: -1.47% — poor at shorter horizon as expected.
- 1d win rate: 46.2%, avg 1d return: +0.66% — slight positive 1d signal (new observation).
- social_dd remains the **only scanner positive at 30d** across all strategies.
- Apr 3-9 mature recs: GME (Apr 8, score=56, conf=5) was the only social_dd pick. Sub-threshold, no recommendation generated. Score reflects weak fundamentals (-13.9% rev growth, insider selling) — appropriate.
- Confidence: high (n=26, consistent 30d outperformance confirmed across two analysis cycles)

## Pending Hypotheses
- [x] Does the ranker's "social_dd / social_hype → SPECULATIVE" grouping suppress social_dd scores? → **Partially false**: avg score is 71.5, suppression affects only 3/25 picks. Not the primary issue.
- [ ] Should social_dd get a separate ranker treatment from social_hype, given divergent 30d outcomes? → Still open. social_hype 7d win rate 18.2% vs social_dd 30d 57.1% — they are fundamentally different signals.
- [ ] Fix evaluation horizon: ranker and recommendation system should assess social_dd at 30d, not 7d. This may require a scanner-level `eval_horizon` config field.
- [ ] At what social score threshold (>75? >85?) does the setup reliably score ≥65 to generate recommendations? → Lower priority now that suppression is not the main issue.
