---
date: 2026-05-15
updated_by: ses_adb903
tags: [brief, WATCH-001, screening, enrichment]
---

# Brief: WATCH-001 Pattern-Level Enrichment

**Date:** 2026-05-15
**Status:** Done
**Closed:** 2026-05-20
**Epic ID:** WATCH-001
**Source:** `docs/time-benchmark-takeaways.md` (from TIME benchmark paper, arXiv:2602.12147)

---

## Objective

Enhance WATCH-001 screening enrichment with pattern-level time series features derived from STL decomposition. These features enable more nuanced screening rules than raw fundamental ratios alone.

---

## Background

The TIME benchmark paper (arXiv:2602.12147) demonstrates that:

1. **Pattern-level evaluation** reveals model capabilities that dataset-level metrics obscure
2. **STL decomposition** (Seasonal and Trend decomposition using Loess) produces interpretable, structured features
3. **Feature vector** of 7 structural features characterizes intrinsic temporal patterns per variate

These features can be computed from historical price data (OHLCV) and used to weight screening priority.

---

## Proposed Features

Based on the TIME paper's methodology, compute these from `prices` table for watchlist candidates:

| Feature | Source | Description | Screening Use |
|---------|--------|-------------|---------------|
| `trend_strength` | STL trend component | Ratio of trend variability to total | High trend = momentum candidate |
| `trend_linearity` | STL trend component | Linear regression R² on trend | Linear trends = predictable |
| `seasonality_strength` | STL seasonal component | Ratio of seasonal to total variability | Seasonal stocks = cyclical candidate |
| `seasonality_stability` | STL seasonal component | ACF between consecutive cycles | Stable vs erratic seasonality |
| `residual_acf1` | STL remainder | First-order autocorrelation of remainder | Forecast difficulty |
| `spectral_entropy` | Raw prices | Spectral entropy (FFT-based) | Difficulty scoring |
| `stationarity` | ADF test | p-value < 0.05 = stationary | Non-stationary = trending |

---

## Implementation

### R08: Pattern Feature Computation

- [ ] **R08.1:** Add pattern feature columns to `watchlist_enrichment` table:
  ```sql
  ALTER TABLE watchlist_enrichment ADD COLUMN trend_strength REAL;
  ALTER TABLE watchlist_enrichment ADD COLUMN trend_linearity REAL;
  ALTER TABLE watchlist_enrichment ADD COLUMN seasonality_strength REAL;
  ALTER TABLE watchlist_enrichment ADD COLUMN seasonality_stability REAL;
  ALTER TABLE watchlist_enrichment ADD COLUMN spectral_entropy REAL;
  ALTER TABLE watchlist_enrichment ADD COLUMN is_stationary INTEGER;
  ```
- [ ] **R08.2:** `compute-pattern-features.ts` script that:
  1. Reads OHLCV from `prices` table (last 252 trading days minimum)
  2. Applies STL decomposition
  3. Computes 7 features
  4. Stores in `watchlist_enrichment` keyed by ticker + fetch_date
- [ ] **R08.3:** Update `screen enrich --pattern --ticker <ticker>` to compute pattern features alongside fundamentals
- [ ] **R08.4:** Update screening engine to use pattern features in rule conditions:
  ```typescript
  type ScreenCondition = {
    // ... existing fields ...
    field: // ... existing | "trend_strength" | "seasonality_strength" | "spectral_entropy" | ...
  }
  ```
- [ ] **R08.5:** Dashboard shows pattern indicators per candidate (sparkline + trend/seasonality badges)

---

## Verification

| Requirement | Verification |
|-------------|-------------|
| R08.1 | `ALTER TABLE` succeeds; pattern columns exist |
| R08.2 | `compute-pattern-features.ts AAPL` populates 7 pattern columns |
| R08.3 | `trading screen enrich --pattern --ticker AAPL` runs without error |
| R08.4 | Screening rule with `field: "seasonality_strength"` matches candidates correctly |
| R08.5 | Dashboard shows pattern badges on prospects view |

---

## Dependencies

- `src/server/lib/schema.sql` — ALTER TABLE for pattern columns
- `src/server/lib/screening-data.ts` — extend EnrichmentRow type
- `src/server/lib/screening-engine.ts` — extend ScreenCondition field types
- `src/cli/commands/screen.ts` — add `--pattern` flag to enrich subcommand
- `scripts/compute-pattern-features.ts` — new script for STL computation

**Note:** STL decomposition can be done in Python (`statsmodels.tsa.seasonal.STL`) or via a Node.js library. Prefer Python for consistency with yfinance usage in existing enrichment code.

---

## Exit Criteria

- Pattern features computed from price data for any watchlist candidate
- Screening rules can reference pattern features alongside fundamental ratios
- Dashboard displays pattern indicators per candidate
- `just check` green

---

## Not in Scope

- Real-time pattern computation (daily batch is sufficient)
- Multi-variate pattern analysis (univariate only for now)
- Model selection based on pattern features (future work)