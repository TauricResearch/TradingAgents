# Reddit DD Scanner

## Current Understanding
Scans r/investing, r/stocks, r/wallstreetbets for DD posts. LLM quality score is
computed and used for filtering — posts scoring >=80 are HIGH priority, 60-79 are
MEDIUM, and <60 are skipped. This quality filter is the key differentiator from
the reddit_trending scanner.

The quality_score filter (>=60) is working: social_dd is the ONLY strategy with
positive 30d returns (+0.94% avg) and 55% 30d win rate across all tracked strategies.
This is confirmed by P&L data spanning 608 total recommendations.

## Evidence Log

### 2026-04-11 — P&L review
- 26 recommendations. 30d avg return: +0.94% (only positive 30d avg among all strategies).
- 30d win rate: 55%. 7d win rate: 44%. 1d win rate: 46.2%.
- The positive 30d return despite negative 1d/7d averages suggests DD-based picks
  need time to play out — the thesis takes weeks, not days, to materialize.
- Compare with social_hype (reddit_trending, no quality filter): -10.64% 30d avg.
  The quality_score filter alone appears to be the separator between signal and noise.
- The code already implements the quality filter correctly (>=60 threshold).
- Confidence: high (26 data points, consistent pattern vs. sister scanner)

## Pending Hypotheses
- [ ] Does filtering by LLM quality score >80 (HIGH only) further improve outcomes vs >60?
- [ ] Does subreddit weighting change hit rates (r/investing vs r/wallstreetbets)?
