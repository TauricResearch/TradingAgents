---
name: market-regime-and-health
description: Frame technical evidence by trend, volatility, liquidity, and invalidation levels instead of indicator accumulation.
roles:
  - market_analyst
triggers:
  - price and volume data are available
  - technical indicators need regime context
output_schema:
  - trend_regime
  - volatility_regime
  - participation
  - invalidation_level
---

First establish the time horizon and use verified OHLCV as the sole source for
exact levels. Characterize trend, volatility, and participation with a small set
of complementary indicators. Explain why each selected indicator addresses a
different question; do not stack redundant oscillators.

For every technical conclusion, give an invalidation condition. Avoid calling a
support, resistance, breakout, or percentage move unless supplied prices and
dates directly support it. Technical evidence is conditional, not a forecast.
