# Reddit Trending Scanner

## Current Understanding
Tracks mention velocity across subreddits. 50+ mentions in 6 hours = HIGH priority.
20-49 = MEDIUM. Mention count should appear in context ("47 mentions in 6hrs").
Signal is early-indicator oriented — catches momentum before price moves.

P&L data shows this is among the worst-performing strategies: -10.64% avg 30d return,
13.6% 1d win rate. The root cause is that LOW and MEDIUM priority candidates (any
ticker with 1-49 raw mentions) add noise without signal. Only HIGH priority (>=50
mentions) candidates have a plausible momentum thesis. Scanner now skips LOW and
MEDIUM priority candidates.

## Evidence Log

### 2026-04-11 — P&L review
- 22 recommendations, 1d win rate 13.6%, 7d win rate 16.7%, 30d win rate 15.4%.
- Avg 30d return: -10.64%. Second worst strategy after news_catalyst (-17.5%).
- Contrast with social_dd (+0.94% 30d): the absence of a quality filter is the
  key differentiator. reddit_trending emits any ticker with raw text mentions.
- The raw text mention count (computed via `result.upper().count(ticker)`) is
  susceptible to false matches (short tickers appear in unrelated words).
- Primary fix: skip MEDIUM and LOW priority candidates — only emit tickers with
  >=50 mentions. This restricts output to genuinely viral tickers.
- Confidence: high (clear signal from 22 recs all losing, vs. DD scanner positive)

## Pending Hypotheses
- [ ] Does mention velocity (rate of increase) outperform raw mention count?
- [ ] Do HIGH priority (>=50 mention) picks specifically outperform MEDIUM (20-49)?
