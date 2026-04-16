# Research: Dark Pool / Block Trade Flow

**Date:** 2026-04-16
**Mode:** autonomous

## Summary

Dark pool order flow (off-exchange block trades) predicts short-term returns in academic literature. A free, scrapable data source exists: `meridianfin.io/darkpool` surfaces daily FINRA ATS anomalies with Z-scores pre-computed, no auth required, plain HTML table. Data lags 1 day (FINRA ATS settlement). Signal: tickers with dark pool % anomaly (Z-score ≥ 2.0) are experiencing unusual institutional off-exchange accumulation — a pre-move signal distinct from any existing scanner.

## Sources Reviewed

- **Buti, Rindi & Werner (2022), Financial Management**: Dark pool retail order imbalance predicts future returns; effect is non-linear and regime-dependent
- **Zhu (2012), NY Fed**: Strong-signal traders prefer lit exchanges; moderate-signal traders route to dark pools — so a dark pool surge suggests informed but not fully certain buying
- **Unusual Whales docs**: Real-time prints with bid/ask classification; subscription required — not used here
- **OptionsTradingOrg practitioner guide**: Volume surge >2-3x 30d average + dark pool % >40-50% of daily volume = actionable signal
- **meridianfin.io/darkpool**: Free, daily, FINRA-based; shows Ticker, Off-Exchange Vol, Dark Pool %, Z-score, Date; 8 top anomalies per day; scrapable with `requests` + `BeautifulSoup`; no auth needed
- **FINRA ATS Transparency (raw)**: Free CSV downloads but require joining multiple venue files and rolling baseline computation — Meridian does this work for us

## Fit Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅ | `meridianfin.io/darkpool` — free HTML table, 1-day lag, no auth, `requests`+BS4 sufficient |
| Complexity | moderate | ~2-4h: HTTP scraper + BS4 parser + scanner class + config entry |
| Signal uniqueness | low overlap | No dark pool scanner exists; `options_flow` uses options chains not off-exchange prints |
| Evidence quality | backtested | Zhu (2012) and Buti et al. (2022) academic backing; volume surge threshold validated by practitioners |

## Recommendation

**Implement** — all four thresholds pass. Signal has academic backing, data is free and scrapable, complexity is moderate, no overlap with existing scanners.

## Proposed Scanner Spec

- **Scanner name:** `dark_pool_flow`
- **Pipeline:** `edge` (off-exchange institutional flow = information advantage)
- **Data source:** Scrape `https://meridianfin.io/darkpool` daily with `requests` + `BeautifulSoup`
- **Signal logic:**
  1. Fetch the anomaly table (up to 8 rows, all pre-filtered by Meridian's Z-score engine)
  2. Filter: Z-score ≥ `min_z_score` (default 2.0)
  3. Filter: dark pool % ≥ `min_dark_pool_pct` (default 40.0%)
  4. Return all passing tickers as candidates
- **Priority rules:**
  - CRITICAL if Z-score ≥ 4.0
  - HIGH if Z-score ≥ 3.0
  - MEDIUM otherwise
- **Context format:** `"Dark pool anomaly: {dark_pool_pct:.1f}% off-exchange | Z-score {z_score:.2f} | Vol: {off_exchange_vol:,}"`
- **Config parameters:**
  ```python
  "dark_pool_flow": {
      "enabled": True,
      "pipeline": "edge",
      "limit": 8,
      "min_z_score": 2.0,        # Minimum FINRA ATS anomaly Z-score
      "min_dark_pool_pct": 40.0, # Minimum % of daily volume off-exchange
      "source_url": "https://meridianfin.io/darkpool",
  }
  ```
- **Limitation:** 1-day lag (FINRA ATS settlement); no bid/ask directionality; only ~8 tickers/day surfaced
