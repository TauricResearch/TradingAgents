# Research: Post-Earnings Announcement Drift (PEAD)

**Date:** 2026-04-14
**Mode:** autonomous

## Summary

PEAD is one of finance's most-studied anomalies: stocks that beat earnings estimates
continue drifting upward for days to weeks after the announcement. QuantPedia backtests
(1987–2004) show 15% annualized returns; the effect is strongest in small-to-mid caps
with >10% EPS surprise. Our pipeline has an `earnings_calendar` scanner that predicts
upcoming earnings but nothing that captures the drift *after* a beat — this is the gap.

## Sources Reviewed

- **QuantPedia — Post-Earnings Announcement Effect**: Combined EAR+SUE strategy generates
  ~12.5% abnormal returns p.a. (1987–2004); optimal hold ~60 trading days; effect strongest
  in small caps; most returns on long side; -11.2% max drawdown observed.
- **Ball & Brown (1968) / Bernard & Thomas (1989)**: Foundational PEAD literature;
  B&T (1989) documented ~18% annualized abnormal returns; magnitude has declined since
  but effect persists — particularly in small caps.
- **DayTrading.com PEAD guide**: Drift persists through approximately day 9 before
  plateauing; 5–20 day hold periods are optimal for tactical implementations.
- **SSRN / Philadelphia Fed (PEAD.txt, 2021)**: NLP-enhanced PEAD achieves 8.01%
  drift over 1-year window; suggests signal is durable when combined with text signals.
- **QuantConnect price+earnings momentum**: Combined momentum strategy showed mixed results
  (Sharpe -0.27) when using *price* momentum alongside earnings growth — not the same as
  surprise-based PEAD.
- **Alpha Architect — 13F data quality warning**: 13F-based institutional signals have 45-day
  lag and data quality issues — screened out as alternative. PEAD is clearly superior for
  short-horizon plays.
- **Finnhub API docs / finnhub-python**: `earnings_calendar(from_date, to_date)` returns
  `epsActual` and `epsEstimate` for all US stocks in the window. Surprise detection requires
  only a lookback call — no extra data sources needed.

## Fit Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅ | `finnhub_api.get_earnings_calendar()` already integrated; returns `epsActual` + `epsEstimate`; lookback call detects recent beats |
| Complexity | moderate | ~3h: query past-14d earnings calendar, filter for beats, compute surprise%, sort by magnitude |
| Signal uniqueness | low overlap | `earnings_calendar` scanner = UPCOMING earnings; PEAD scanner = RECENT beats + drift capture; different timing and signal |
| Evidence quality | backtested | QuantPedia: 15% annualized returns (1987–2004); Bernard & Thomas (1989); 60+ years of academic literature |

## Recommendation

**Implement** — All auto-implement thresholds pass.

Key implementation notes:
- Focus on small-to-mid cap stocks where PEAD effect is strongest (B&T 1989)
- Minimum 5% surprise threshold to filter noise
- CRITICAL at >20% surprise, HIGH at 10–20%, MEDIUM at 5–10%
- Hold horizon: 7–14 days (primary drift window per DayTrading.com)
- Declining US large-cap PEAD mitigated by: small-cap bias + significant surprise filter

## Known Failure Modes

- US large-cap PEAD has declined since 1989 (more efficient pricing); strategy most
  effective for small/mid caps and significant surprises (>10%)
- SUE reversal after 3 quarters (price reverts on next earnings); this is beyond our
  30d evaluation window so not immediately harmful
- Overlapping earnings: same ticker may appear in `earnings_calendar` (upcoming) and
  `earnings_beat` (recent); ranker should treat these as separate signals

## Proposed Scanner Spec

- **Scanner name:** `earnings_beat`
- **Strategy:** `pead_drift`
- **Pipeline:** `events`
- **Data source:** `tradingagents/dataflows/finnhub_api.py` → `get_earnings_calendar(from_date, to_date, return_structured=True)`
- **Signal logic:**
  - Query past `lookback_days` (default 14) of earnings calendar
  - Compute `surprise_pct = (epsActual - epsEstimate) / abs(epsEstimate) * 100`
  - Filter: `surprise_pct >= min_surprise_pct` (default 5.0%)
  - Filter: `epsEstimate != 0` and both fields not None
  - Sort by `surprise_pct` descending
- **Priority rules:**
  - CRITICAL if `surprise_pct >= 20`
  - HIGH if `surprise_pct >= 10`
  - MEDIUM otherwise
- **Context format:** `"Earnings beat Xd ago: actual $A vs est $B (+Z% surprise) — PEAD drift window open"`
