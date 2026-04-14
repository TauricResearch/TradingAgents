# Research: OBV Divergence as Multi-Week Accumulation Signal

**Date:** 2026-04-14
**Mode:** autonomous

## Summary
On-Balance Volume (OBV) divergence — price flat or falling while OBV trends up — is an established
signal for detecting multi-week institutional accumulation. Academic evidence on volume-price
causality is mixed at the mean, but commercial backtests consistently show divergence strategies
outperforming simple momentum in qualitative studies. The signal is distinct from the existing
`volume_accumulation` scanner (which detects single-day spikes) and uses already-integrated price
and volume data, making it straightforward to implement.

## Sources Reviewed
- **ArrowAlgo OBV Guide**: OBV divergence strategy: price lower low + OBV higher low = 68% win
  rate, 12% avg annual return (4-year backtest on individual stocks). Breakout confirmation:
  Sharpe 1.4. No standalone significance without price structure confirmation.
- **Vestinda OBV Backtesting**: OBV + Ichimoku reversal on RIOT: 25% win rate but 64% annual ROI
  (high-reward lottery approach); OBV + Ichimoku on BAC: 46% win rate, 5.5% annual ROI,
  35% outperformance vs. buy-and-hold. Confirms OBV is better as a filter than a trigger.
- **StockCharts ChartSchool**: Canonical OBV definition (Granville 1963). Rising OBV during
  sideways/declining price = quiet accumulation. Bullish divergence entry: price at lower low,
  OBV at higher low. Failure modes: volume spikes from news events, standalone unreliability.
- **NinjaTrader OBV Blog**: Three strategies (trend-following, divergence, breakout confirmation).
  Key: OBV crossing above EMA = bullish entry. No hard win-rate stats.
- **ScienceDirect volume-return causality study**: Lagged volume coefficient insignificant at the
  mean (OLS), but quantile regressions show higher predictive power when informed trading is
  elevated. Suggests OBV works better in high-conviction accumulation regimes.
- **TradingAgents codebase**: OBV calculation already exists in `technical_analyst.py:298-348`
  for per-stock analysis, not for scanning. Reuse is straightforward.

## Fit Evaluation
| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅ | Price + volume history via `y_finance.py`; scan cache already built by `volume_accumulation` scanner (shared `"default"` cache key) |
| Complexity | moderate | OBV computation is a simple loop (~30 lines); divergence detection requires loading cached history per ticker; bulk scan is feasible within scanner timeout |
| Signal uniqueness | low overlap | `volume_accumulation` detects single-day 2x+ spikes with same-day direction filter; OBV divergence detects sustained multi-week buying pressure during price consolidation — complementary, not redundant |
| Evidence quality | qualitative | Commercial backtests: 68% win rate (divergence), Sharpe 1.4 (breakout); academic: mixed — volume-return causality illusive at mean but stronger in high-conviction regimes (ScienceDirect 2025) |

## Recommendation
**Implement** — meets all four auto-implement thresholds. Signal is complementary to existing
`volume_accumulation` scanner, reuses cached data, and has qualitative-level evidence (same tier as
`short_squeeze` at time of implementation). Weak academic backing is a known limitation; the
signal should be treated as a discovery filter and validated with `/iterate` performance data.

## Proposed Scanner Spec
- **Scanner name:** `obv_divergence`
- **Data source:** `tradingagents/dataflows/alpha_vantage_volume.py` (`download_volume_data` +
  `_records_to_dataframe`); reuses the `"default"` volume cache shared with `volume_accumulation`
- **Signal logic:**
  1. Load 90d daily price+volume history from the shared cache
  2. Compute OBV: cumulative sum, add volume if close > prev_close, subtract if close < prev_close
  3. Bullish divergence: `price_change_pct (lookback_days ago) ≤ max_price_change_pct (default 2%)`
     AND `obv_pct_gain ≥ min_obv_pct_gain (default 8%)`, where obv_pct_gain is the OBV change
     over the lookback period normalized by `avg_daily_volume × lookback_days`
  4. Filter out stocks where price fell >5% (likely distribution, not accumulation)
- **Priority rules:**
  - HIGH if `obv_pct_gain ≥ 20%` AND `price_change_pct ≤ 0` (clear divergence, price unchanged or down)
  - MEDIUM if `obv_pct_gain ≥ 8%` (mild divergence during consolidation)
- **Context format:** `"OBV divergence: price {price_change_20d:+.1f}% over {lookback}d, OBV +{obv_pct_gain:.1f}% of avg vol — multi-week accumulation signal"`
