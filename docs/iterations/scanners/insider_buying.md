# Insider Buying Scanner

## Current Understanding
Scrapes SEC Form 4 filings. CEO/CFO purchases >$100K are the most reliable signal.
Cluster detection (2+ insiders buying within 14 days) historically a high-conviction
setup. Transaction details (name, title, value) must be preserved from scraper output
and included in candidate context — dropping them loses signal clarity.

Default `min_transaction_value` was $25K but P&L data (178 recs, -2.05% 30d avg)
indicates the low threshold allows sub-signal transactions through. Raised to $100K
to align with the registered insider_buying-min-txn-100k hypothesis.

## Evidence Log

### 2026-04-11 — P&L review
- 178 recommendations over Feb–Apr 2026. Avg 30d return: -2.05%. 30d win rate: 29.4%.
- 1d win rate only 38.1%, suggesting price does not immediately react to filing disclosures.
- 7d win rate 46.3% — marginally better, but still below coin-flip at 30d.
- Sample files show most published recs had large transactions ($1M–$37M), but the
  scanner's $25K floor likely admits many smaller, noisier transactions in the raw feed.
- Broader market context (tariff shock, sell-off Feb–Apr 2026) likely suppressed all
  long signals, making it hard to isolate scanner quality from market conditions.
- Confidence: medium (market headwinds confound; need post-recovery data to isolate)

## Pending Hypotheses
- [ ] Does cluster detection (2+ insiders in 14 days) outperform single-insider signals?
- [x] Is there a minimum transaction size below which signal quality degrades sharply?
      → Raising threshold from $25K to $100K to test. Prior $25K baseline had -2.05% 30d avg.
