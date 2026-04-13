# Short Squeeze Scanner

## Current Understanding
Identifies stocks with structurally high short interest (>15% of float by default, CRITICAL at >30%)
where short sellers are vulnerable to forced covering on any positive catalyst. The scanner uses
Finviz for discovery (screener filters) + Yahoo Finance for exact SI% and days-to-cover (shortRatio)
verification.

Key distinction: High SI alone predicts *negative* long-term returns on average (academic consensus).
However, first real P&L data (n=10) shows 60% 7d win rate and +2.15% avg 7d — best 7d performer in
the pipeline. This may reflect that discovery-pipeline filtering (technical confirmation, enrichment)
already adds the catalyst signal needed to convert squeeze-risk into a directional trade. Cross-scanner
confluence (short_squeeze + options_flow or earnings_calendar) remains a stronger signal than either
alone and is the primary confluence hypothesis under test.

## Evidence Log

### 2026-04-13 — P&L review (first real outcome data)
- 10 tracked recommendations, 5/10 1d wins (50% win rate), 6/10 7d wins (60% win rate).
- Avg 7d return: +2.15%. This makes short_squeeze the **best 7d performer** among scanners with ≥5 samples.
- Outperforms analyst_upgrade (50% 7d), insider_buying (46.4% 7d), options_flow (45.6% 7d).
- The scanner is producing positive outcomes as a standalone signal, not only as a cross-scanner modifier.
- However, ranker prompt says "Focus on days to cover" but context string only shows SI%. DTC value is available in Yahoo Finance (`shortRatio`) but was not being fetched or passed through — gap confirmed.
- Confidence: medium (small sample n=10; 30d data will be more conclusive; DTC gap has been fixed)

### 2026-04-13 — Code fix: days_to_cover surfaced in context
- Added `days_to_cover` extraction (`shortRatio` from Yahoo Finance) to `finviz_scraper.py`.
- Applied `min_days_to_cover` filter (previously accepted as parameter but never enforced).
- Updated `short_squeeze.py` context string to include DTC value so ranker can use "days to cover" criterion.
- Confidence: high (this is a clear context gap between ranker criteria and available data)

## Pending Hypotheses
- [ ] Does short_squeeze + options_flow confluence produce better 7d win rate than either scanner alone?
- [ ] Does short_squeeze + earnings_calendar (SI>20%) produce better outcomes than earnings alone? (See earnings_calendar.md pending hypothesis)
- [ ] Is there a volume threshold (e.g., market cap <$2B small-cap) that sharpens the signal?
- [ ] Does DTC >5 (now surfaced in context) predict better outcomes than DTC 2-5 within the scanner?
- [ ] Does standalone short_squeeze (no cross-scanner confluence) continue to outperform at 7d as sample grows?
