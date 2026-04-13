# Short Squeeze Scanner

## Current Understanding
Identifies stocks with structurally high short interest (>15% of float by default, CRITICAL at >30%)
where short sellers are vulnerable to forced covering on any positive catalyst. The scanner uses
Finviz for discovery (screener filters) + Yahoo Finance for exact SI% verification.

Key distinction: High SI alone predicts *negative* long-term returns on average (academic consensus).
The scanner is a squeeze-risk flag, not a directional buy signal. Value comes from cross-scanner
confluence: a stock appearing here AND in options_flow or earnings_calendar is significantly stronger
than either signal alone.

## Evidence Log

_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does short_squeeze + options_flow confluence produce better 7d win rate than either scanner alone?
- [ ] Does short_squeeze + earnings_calendar (SI>20%) produce better outcomes than earnings alone? (See earnings_calendar.md pending hypothesis)
- [ ] Is there a volume threshold (e.g., market cap <$2B small-cap) that sharpens the signal?
