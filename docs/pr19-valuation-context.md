# PR19: Historical Valuation Context

## Purpose

PR19 adds a descriptive valuation layer for a single stock. It compares the latest cached daily valuation snapshot with the same instrument's own recent history; it does not compare companies, estimate intrinsic value, or create a buy/sell signal.

## Data

For A shares, the existing Tushare `daily_basic` call now retains roughly 400 calendar days of rows, producing up to 252 latest trading-day snapshots for the local cache. The calculation uses these fields when available:

- P/E (TTM)
- price-to-book
- price-to-sales (TTM)
- dividend yield

At least 20 valid daily observations are required for a metric to receive a historical percentile, low, median, and high. Missing, non-numeric, or non-finite values remain unavailable.

## Semantics

The percentile is the share of the cached same-stock observations less than or equal to the latest value. It describes the current position in this local historical sample, not whether a valuation is cheap, expensive, or actionable.

The Markdown report and local cockpit expose this layer independently from Financial Quality, Financial Health, trade signals, and risk review.
