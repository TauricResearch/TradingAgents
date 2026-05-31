# SOXX (iShares Semiconductor ETF) — Technical Analysis Report
**As of: 2026-05-29 (last trading day before 2026-05-31)**

> Note: A `get_verified_market_snapshot` tool was attempted but is not available in this environment. All figures below are sourced directly from `get_stock_data` and `get_indicators` outputs.

---

## 1. Indicator Selection Rationale

For a high-momentum, high-volatility ETF that has just experienced a parabolic move, I selected eight complementary indicators across four categories:

| Category | Indicator | Why it's relevant here |
|---|---|---|
| Trend (long) | **close_200_sma** | Confirms the prevailing primary uptrend and gauges distance from long-term mean. |
| Trend (medium) | **close_50_sma** | Acts as the dynamic structural support during the rally. |
| Trend (short) | **close_10_ema** | Captures the steepening near-term momentum and pullback entries. |
| Momentum | **macd** | Tracks momentum strength and detects loss of thrust. |
| Momentum | **macdh** | Signal-line divergence flags fade earliest — important after a vertical move. |
| Momentum (oscillator) | **rsi** | Critical for spotting overbought conditions during a parabolic phase. |
| Volatility | **boll_ub** | Tells whether price is "riding the band" (strong trend) vs. mean-reverting. |
| Volatility | **atr** | Sizing/stop placement essential given recent expansion in true range. |

I deliberately omitted `boll`/`boll_lb` (redundant with `boll_ub` for current overbought analysis), `macds` (covered by `macdh`), and `vwma` (less informative than ATR/Bollinger in this regime).

---

## 2. Price Action — The Big Picture

SOXX has staged an extraordinary 7-month rally from late-November 2025 lows. Key checkpoints from the data:

- **2025-11-21 low close: 270.27** (capitulation low after a violent November selloff).
- **2026-01-29 close: 360.91** — ETF rallied ~33% to mid-January, then suffered an 11% pullback into 2026-02-04 (close 330.18).
- **2026-03-30 close: 309.79** — second meaningful pullback / shakeout (~14% from Feb high).
- **2026-04-08 → 2026-05-29: a near-vertical advance.** Close rose from **347.76 (Apr 7)** to **569.08 (May 29)** — roughly **+63% in ~7 weeks**, including a single-day gap from **506.87 → 482.36 → 520.30 → 532.76** in early May.
- **All-time high close in this window: 570.09 on 2026-05-26.**
- Last 3 sessions (May 27–29) saw a flat/digestive pattern: **563.98 → 569.47 → 569.08**, with intraday high 584.50 on May 27 — possible exhaustion candle.

---

## 3. Trend Structure (Moving Averages)

| Date (2026-05-29) | Value | Distance vs. Close (569.08) |
|---|---|---|
| 10 EMA | 544.07 | Price **+4.6%** above |
| 50 SMA | 437.63 | Price **+30.0%** above |
| 200 SMA | 335.90 | Price **+69.4%** above |

**Observations:**
- All three MAs are aligned bullishly (10 EMA > 50 SMA > 200 SMA), and all are sloping up. This is textbook stage-2 uptrend.
- **The 200 SMA is rising at ~$1.50/day**, while the 50 SMA is rising at ~$4.6/day — momentum is accelerating, not just sustaining.
- However, the **gap between price and the 200 SMA (~70%) is historically extreme.** Prior local tops (Jan 29 close 360.91 vs. ~260-area 200 SMA back then ≈ +39%, and Feb 25 at 367.77 vs ~315 ≈ +17%) were far less stretched. Mean reversion risk is elevated.
- The 10 EMA at 544 is the first dynamic support to watch on a pullback. A break of 10 EMA does not invalidate the trend, but a break of the **50 SMA at ~438** would be a structural change.

---

## 4. Momentum (MACD & RSI)

**MACD line (2026-05-29): 34.68** — extremely elevated, near multi-month highs.
**MACD histogram (2026-05-29): +1.71**, having just **flipped back positive on 2026-05-26** after a ~5-session negative stretch (May 19–22 readings of -3.25 to -1.92).

- This is a **bullish re-cross** of the signal line on May 26 — momentum reasserted after a brief consolidation. The histogram is, however, smaller than its early-May peaks (+5.80 on 2026-05-11), indicating **slightly weaker thrust than earlier in the move** despite higher prices — a subtle negative momentum divergence worth monitoring.

**RSI (2026-05-29): 72.74** — overbought.

- RSI has been above 70 on May 26 (74.6), May 27 (72.0), May 28 (72.9), and May 29 (72.7). It also spent most of early May overbought (peaking at 81.50 on May 6, 79.63 on May 11).
- RSI has **made lower highs** (81.5 → 79.6 → 74.6 → 72.7) while price has made **higher highs** (506.87 → 532.76 → 570.09). This is a classic **bearish RSI divergence forming on the daily timeframe**.
- In strong trends, RSI can stay overbought for weeks; this divergence is a **warning, not a sell signal** until confirmed by price weakness.

---

## 5. Volatility (Bollinger Upper Band & ATR)

**Bollinger Upper Band (2026-05-29): 584.30**
**Close (2026-05-29): 569.08** — price is just below the upper band, having tagged/exceeded it on multiple days during the rally.

- The upper band has expanded rapidly from **488 on May 1 → 584 on May 29** (+19.7% in a month), confirming a true volatility breakout regime, not noise.
- Price is "riding" the upper band — typical of strong impulsive moves. A close back inside the band (i.e., below ~584) is normal; a close back below the **20-day midline (~454, implied from band data)** would signal regime change.

**ATR (2026-05-29): 20.50**

- ATR has nearly doubled since early May (12.68 on May 4 → 20.50 on May 29). Daily expected range is now ~$20, or ~3.6% of price.
- For risk management: a 1×ATR stop = ~$20; 2×ATR = ~$41. Position sizing should be reduced relative to 6 weeks ago.
- High ATR + overbought RSI is a classic "blow-off" combination — large opportunity but large reversal risk.

---

## 6. Synthesis — What the Tape is Saying

**Bullish evidence (still in control):**
- All MAs aligned and rising; price above 10 EMA.
- MACD histogram just flipped positive (May 26) after a clean reset.
- Price riding the upper Bollinger band — strong-trend behavior.
- Higher highs and higher lows intact since April 8.

**Cautionary evidence (mounting):**
- RSI bearish divergence over 4 weeks (lower RSI peaks vs. higher price peaks).
- MACD histogram peaks shrinking (May 11: +5.80 → May 29: +1.71) despite new highs.
- Price ~70% above the 200 SMA — historically unsustainable stretch.
- ATR doubled in a month — volatility expansion typically precedes turbulence.
- May 27 candle: high of 584.50 but close of 563.98 → upper-wick rejection at the Bollinger band.

**Most probable scenario:** The trend remains intact, but the easy upside has been consumed. Expect a **2–3 ATR ($40–$60) corrective pullback** toward the 10 EMA (~544) or even the rising 20-day band midline (~454) before the next leg. A close below the **10 EMA with rising volume** would be the first actionable confirmation that the parabolic phase is ending.

**Key actionable levels:**
- **Immediate resistance:** 584 (Bollinger upper band, May 27 high).
- **Short-term support:** 544 (10 EMA), then 530 (May 11 close / consolidation).
- **Trend support:** 438 (50 SMA) — a break here flips the trend structure.
- **Long-term anchor:** 336 (200 SMA).

---

## 7. Summary Table

| Theme | Indicator | Value (2026-05-29) | Reading | Implication |
|---|---|---|---|---|
| Long-term trend | 200 SMA | 335.90 | Price +69% above | Trend strongly up, but extended |
| Medium-term trend | 50 SMA | 437.63 | Price +30% above, slope up | Bullish, key invalidation level |
| Short-term trend | 10 EMA | 544.07 | Price +4.6% above | First dynamic support |
| Momentum | MACD | 34.68 | Elevated, rising | Bullish |
| Momentum | MACD Histogram | +1.71 | Just flipped positive 5/26 | Fresh bull confirmation, weakening peaks |
| Momentum | RSI | 72.74 | Overbought + bearish divergence | Caution, not yet a sell |
| Volatility | Bollinger Upper | 584.30 | Price riding band | Strong trend regime |
| Volatility | ATR | 20.50 | Doubled in 1 month | Use wider stops, smaller size |
| Recent close | — | 569.08 | All-time high zone | Prone to reversion |
| Bearish divergences | RSI peaks: 81.5 → 79.6 → 74.6 → 72.7 vs. higher price highs | — | Warning building | Watch for trigger |

---

**Bias:** Constructive but late-cycle. Trend-followers stay long with trailing stop near the 10 EMA (~544) using 1.5× ATR. New longs at these levels are unfavorable risk/reward; better entries on a pullback to the 10 EMA or the rising 50 SMA. Aggressive traders may scale-out partial profits into the upper Bollinger band (~584) given the RSI/MACD divergences.