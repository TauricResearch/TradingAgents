# Research: Dark Pool / Block Trade Flow

**Date:** 2026-04-16
**Mode:** autonomous

> **Auto-implementation skipped:** Data availability ❌ — no free real-time dark pool feed exists; FINRA ATS data has 1-2 week delay, making it unusable for next-day discovery.

## Summary

Dark pool order flow (off-exchange block trades) does predict short-term returns in academic literature, but the signal requires real-time directional data (bid/ask side classification) that is only available via paid vendors (Unusual Whales, FlowAlgo, ~$50-200/mo). The free FINRA ATS Transparency data lags by 1-2 weeks, making it useless for a daily scanner. Without a data source, implementation is blocked regardless of signal quality.

## Sources Reviewed

- **Buti, Rindi & Werner (2022), Financial Management**: Dark pool retail order imbalance predicts future returns; effect is non-linear and context-dependent (regime-filtered by volatility)
- **Zhu (2012), NY Fed**: Price discovery in dark pools impaired above a critical imbalance threshold; strong-signal traders prefer exchanges, moderate-signal traders use dark pools
- **Unusual Whales docs**: Real-time dark pool prints classified bullish/bearish by bid/ask side; tiered by size ($5k, $15k, $30k+); subscription required
- **OptionsTradingOrg practitioner guide**: Block filter = trades >10,000 shares or >$200K; volume surge filter = dark pool volume >2-3x 30d average; confirmation = dark pool buy + OTM call sweeps on ask side
- **FINRA ATS Transparency**: Free, covers all ATS/dark pool volume by ticker — but data lags 1-2 weeks; not suitable for discovery

## Fit Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ❌ | No free real-time feed; FINRA ATS lags 2 weeks; paid vendors ($50-200/mo) required |
| Complexity | moderate | Would need API client for Unusual Whales + directional classification logic |
| Signal uniqueness | low overlap | No existing dark pool scanner; closest is `options_flow` which uses public options data |
| Evidence quality | backtested | Zhu (2012) and Buti et al. (2022) provide academic evidence; practitioner signal logic well-documented |

## Recommendation

**Skip (data blocker)** — The signal has genuine predictive content backed by academic evidence, but implementation requires a paid data vendor subscription. If Unusual Whales or FlowAlgo API access becomes available, this is a high-priority scanner to build.

## Signal Logic (for future reference if data becomes available)

- **Entry signal**: Dark pool print volume > 2x 30-day rolling average AND classified as bullish (ask-side fill)
- **Confirmation**: Same-day or prior-day OTM call sweep on the ask side
- **Priority**: CRITICAL if both conditions met + repeat prints over 3+ days; HIGH if single large bullish print; MEDIUM if volume surge without directional confirmation
- **Context format**: `"Dark pool: {volume:,} shares ({pct_of_daily:.0f}% of daily vol) | {bullish_pct:.0f}% bullish flow | {confirmation}"`
- **Suggested thresholds**: `min_dark_pool_volume_multiple: 2.0`, `min_bullish_pct: 55`, `min_block_size: 10000`
- **Data source needed**: Unusual Whales API (or equivalent) at `unusualwhales.com`
