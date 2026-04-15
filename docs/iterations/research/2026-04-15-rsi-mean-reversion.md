# Research: RSI(2) Mean Reversion Oversold Bounce

**Date:** 2026-04-15
**Mode:** autonomous

## Summary

Larry Connors' 2-period RSI mean-reversion strategy surfaces stocks in uptrends (price
above 200-day SMA) that have pulled back sharply enough to register RSI(2) < 10. The
200-day SMA filter is the critical guard against catching falling knives — without it,
the plain RSI < 30 rule fails in persistent downtrends. Academic evidence from Lehmann
(1990) and Alpha Architect confirms weekly losers revert at 0.86–1.24% per week, with
contrarian strategies generating >2% per month in abnormal returns. This is the only
contrarian signal not represented anywhere in the current momentum-heavy pipeline.

## Sources Reviewed

- **QuantifiedStrategies (search results)**: RSI(2) strategy with 75–79% win rate over
  25-year backtest (2000–2025); lower RSI at entry → higher subsequent returns; profit
  factor ≈ 2.08 at best settings.
- **Medium / FMZQuant — Larry Connors RSI2**: Exact rule: price above 200d SMA AND
  RSI(2) < 10 → buy; exit when RSI(2) > 90. Tested on DIA and individual equities.
  Described as "fairly aggressive short-term" with entry on close.
- **StockCharts ChartSchool — RSI(2)**: Entry RSI(2) ≤ 5 (aggressive) or ≤ 10; exit
  on move above 5-day SMA or RSI(2) > 90. Volume filter: 20-day avg volume > 40k.
  Warns: "RSI(2) can remain oversold a long time in a bear" → SMA200 filter mandatory.
- **Alpha Architect — Short-Term Return Reversal (Lehmann 1990)**: Weekly losers
  generate +0.86% to +1.24% per week in the subsequent week; contrarian strategies
  (buy losers, sell winners) produce >2%/month abnormal returns. Effect is strongest
  for liquid, actively-traded stocks.
- **Alpha Architect — Combining Reversals + Momentum**: Reversal and momentum coexist
  at the 1-month horizon — reversal is dominant among low-turnover stocks, momentum
  among high-turnover. Filtering to high-liquidity names (min avg volume) reduces noise.
- **WebSearch aggregate**: Connors 25-year backtest CAGR 8.2%, max drawdown 16%;
  performance degrades in prolonged bear markets (2008, Mar 2020) — SMA200 filter
  critical; best results when SPY itself is not in freefall.

## Cross-Reference: Existing Pipeline

- **No existing mean-reversion scanner.** All current scanners (minervini,
  high_52w_breakout, technical_breakout, obv_divergence, short_squeeze, insider_buying,
  options_flow, earnings_beat) are momentum- or event-driven. The RSI oversold bounce
  is fully orthogonal.
- **technical_breakout** (scanners/technical_breakout.md): targets resistance breakouts,
  opposite signal direction. No overlap.
- **obv_divergence**: detects flat price + rising OBV (accumulation). Partial overlap
  in that both can flag a beaten-down stock, but OBV divergence requires volume evidence
  of buying; RSI oversold can fire on pure price action.
- **No prior research file** on mean reversion or RSI.

## Fit Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅ | yfinance OHLCV + `download_ohlcv_cached` fully integrated; RSI(2) computable from close prices, 200d SMA from same data |
| Complexity | trivial/moderate | RSI(2) is a 6-line calculation; same code pattern as `high_52w_breakout` which already uses `download_ohlcv_cached` |
| Signal uniqueness | low overlap | Only contrarian scanner in the entire pipeline; orthogonal to all momentum signals |
| Evidence quality | backtested | Connors 25-year backtest, 75–79% win rate; Lehmann (1990) academic paper; Alpha Architect reversal review |

All four auto-implement thresholds pass → **implement**.

## Recommendation

**Implement** — Pipeline gap: zero mean-reversion coverage. RSI(2) with SMA200 trend
filter is one of the most replicated mean-reversion signals in quant literature, data
is fully available, and implementation is trivial following the `high_52w_breakout`
template. Expected holding period: 3–7 days (exit when RSI(2) > 90 or closes above
5-day SMA).

## Proposed Scanner Spec

- **Scanner name:** `rsi_oversold`
- **Data source:** `tradingagents/dataflows/data_cache/ohlcv_cache.py` via
  `download_ohlcv_cached` (same as `high_52w_breakout`)
- **Signal logic:**
  1. Load 1-year OHLCV for full universe
  2. Compute RSI(2) from last 3 closes: avg_gain/avg_loss over 2 periods
  3. Compute 200-day SMA from close series
  4. **Filter:** price > 200d SMA (uptrend guard) AND RSI(2) < `max_rsi` (default 10)
     AND close > `min_price` (default $5) AND avg_vol_20d > `min_avg_volume` (default 100k)
  5. Sort by RSI(2) ascending (most oversold first)
- **Priority rules:**
  - CRITICAL if RSI(2) < 5 (extreme oversold, highest expected bounce)
  - HIGH if RSI(2) < 8
  - MEDIUM if RSI(2) < 10
- **Context format:**
  `"RSI(2) oversold at {rsi:.1f} | Price ${price:.2f} above 200d SMA ${sma200:.2f}
  (+{pct:.1f}%) | 3–7d mean-reversion bounce setup"`
