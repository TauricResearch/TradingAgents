# Reddit DD Scanner

## Current Understanding
Scans r/investing, r/stocks, r/wallstreetbets for DD posts. LLM quality score is
computed but not used for filtering — using it (80+ = HIGH, 60-79 = MEDIUM, <60 = skip)
would reduce noise. Subreddit weighting matters: r/investing posts are more reliable
than r/pennystocks. Post title and LLM score should appear in candidate context.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does filtering by LLM quality score >60 meaningfully reduce false positives?
- [ ] Does subreddit weighting change hit rates?
