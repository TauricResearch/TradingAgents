# Insider Buying Scanner

## Current Understanding
Scrapes SEC Form 4 filings. CEO/CFO purchases >$100K are the most reliable signal.
Cluster detection (2+ insiders buying within 14 days) historically a high-conviction
setup. Transaction details (name, title, value) must be preserved from scraper output
and included in candidate context — dropping them loses signal clarity.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does cluster detection (2+ insiders in 14 days) outperform single-insider signals?
- [ ] Is there a minimum transaction size below which signal quality degrades sharply?
