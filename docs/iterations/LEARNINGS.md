# Learnings Index

**Last analyzed run:** 2026-04-14

| Domain | File | Last Updated | One-line Summary |
|--------|------|--------------|-----------------|
| options_flow | scanners/options_flow.md | 2026-04-12 | Premium filter confirmed applied; CSCO cross-scanner confluence detected; 45.1% 7d win rate (94 recs) |
| insider_buying | scanners/insider_buying.md | 2026-04-14 | Staleness suppression filter added (PAGS/ZBIO/HMH 3-4 day repeats confirmed); 45.9% 7d, negative avg returns |
| minervini | scanners/minervini.md | 2026-04-12 | Best performer: 100% 1d win rate (n=3), +3.68% avg; 7 candidates in Apr 6-12 week |
| analyst_upgrades | scanners/analyst_upgrades.md | 2026-04-12 | 51.6% 7d win rate (marginal positive); cross-scanner confluence with options_flow is positive signal |
| earnings_calendar | scanners/earnings_calendar.md | 2026-04-12 | Appears as earnings_play; 38.1% 1d, 37.7% 7d — poor; best setups require high short interest |
| pipeline/scoring | pipeline/scoring.md | 2026-04-14 | news_catalyst 0% 7d now explicit in ranker criteria; insider staleness filter implemented; 41.9% overall 7d win rate |
| early_accumulation | scanners/early_accumulation.md | 2026-04-12 | Sub-threshold (score=60); no catalyst → structurally score-capped by ranker |
| social_dd | scanners/social_dd.md | 2026-04-14 | 57.1% 30d win rate (+1.41% avg 30d, n=26) — only scanner positive at 30d; eval horizon mismatch persists |
| volume_accumulation | scanners/volume_accumulation.md | — | No data yet |
| short_squeeze | scanners/short_squeeze.md | 2026-04-14 | 60% 7d win rate (n=11), best 7d performer; BUT 30% 30d — short-term signal only, degrades at 30d |
| earnings_beat | scanners/earnings_beat.md | 2026-04-14 | New PEAD scanner: recent EPS beats ≥5% surprise; 15% annualized academic edge; distinct from earnings_calendar |

## Research

| Title | File | Date | Summary |
|-------|------|------|---------|
| OBV Divergence Accumulation | research/2026-04-14-obv-divergence.md | 2026-04-14 | OBV rising while price flat/down = multi-week institutional accumulation; qualitative 68% win rate; implemented as obv_divergence scanner |
| Short Interest Squeeze Scanner | research/2026-04-12-short-interest-squeeze.md | 2026-04-12 | High SI (>20%) + DTC >5 as squeeze-risk discovery; implemented as short_squeeze scanner |
| 52-Week High Breakout Momentum | research/2026-04-13-52-week-high-breakout.md | 2026-04-13 | George & Hwang (2004) validated: 52w high crossing + 1.5x volume = 72% win rate, +11.4% avg over 31d; implemented as high_52w_breakout scanner |
| PEAD Post-Earnings Drift | research/2026-04-14-pead-earnings-beat.md | 2026-04-14 | Bernard & Thomas (1989): 18% annualized PEAD; QuantPedia: 15% annualized (1987-2004); implemented as earnings_beat scanner (distinct from earnings_calendar's upcoming-only scope) |
| reddit_dd | scanners/reddit_dd.md | — | No data yet |
| reddit_trending | scanners/reddit_trending.md | — | No data yet |
| semantic_news | scanners/semantic_news.md | — | No data yet |
| market_movers | scanners/market_movers.md | — | No data yet |
| technical_breakout | scanners/technical_breakout.md | — | No data yet |
| sector_rotation | scanners/sector_rotation.md | — | No data yet |
| ml_signal | scanners/ml_signal.md | — | No data yet |
