# TCEHY (Tencent Holdings ADR) — Technical Analysis Report
**Analysis Date: 2026-05-31 | Last Trading Day: 2026-05-29 | Last Close: $54.60**

> ⚠️ Note: The `get_verified_market_snapshot` tool was not available in this environment. All figures below are sourced directly from `get_stock_data` and `get_indicators`. I have not independently verified them through a secondary tool, so consumers should treat single-decimal price levels as reported by these tools rather than as cross-validated figures.

---

## 1. Indicator Selection Rationale

For TCEHY, which is in a sustained, accelerating downtrend with elevated volume, I selected the following 8 complementary indicators:

| Indicator | Category | Why Selected |
|---|---|---|
| `close_10_ema` | Trend (fast) | Captures short-term momentum shifts and acts as the most immediate dynamic resistance in a downtrend |
| `close_50_sma` | Trend (medium) | Identifies medium-term trend direction; price action vs. 50 SMA shows the trend has been intact since December |
| `close_200_sma` | Trend (long) | Confirms the long-term regime and any potential death-cross dynamics |
| `macd` | Momentum | Quantifies trend momentum; useful for spotting divergence at potential bottoms |
| `macdh` | Momentum | Earliest visual cue for momentum loss/gain — picks up changes before MACD line crossovers |
| `rsi` | Momentum oscillator | Flags oversold conditions and bullish divergences — critical given how stretched price is |
| `boll_lb` | Volatility | The lower Bollinger Band identifies extreme oversold zones; price riding the lower band signals a strong trend |
| `atr` | Volatility (risk sizing) | Essential for sizing positions and placing stops in this volatile regime |
| `vwma` | Volume-confirmed trend | Confirms whether the downtrend is being supported by genuine volume or is driven by thin liquidity |

I deliberately excluded `boll` and `boll_ub` (redundant with `boll_lb` for an oversold-focused thesis) and `macds` (redundant given `macd` + `macdh` already cover signal-line context).

---

## 2. Price Action Overview

TCEHY has experienced a **substantial multi-month decline**:

- **Nov 13, 2025 high (intraday):** $85.01 — local peak of the period reviewed
- **May 29, 2026 close:** $54.60
- **Approximate decline from Nov peak:** ~36% over ~6.5 months
- **Recent month (May):** Began at $60.49 (May 1) → closed $54.60 (May 29) = ~9.7% drop in May alone
- **One notable dividend:** $0.677 paid on May 18, 2026 (small distortion, but does not explain the multi-month trend)

Two notable single-day events stand out:
- **March 10, 2026:** +$6.88 spike (66.23 → 73.11) on volume of 10.69M (~3x average) — a sharp short-term squeeze that fully retraced within a week.
- **May 13, 2026:** +$2.77 spike (57.63 → 60.40) on volume of 13.72M — also fully retraced within four sessions.

Both rallies were rejected, confirming **strong overhead supply**.

---

## 3. Trend Structure (Moving Averages)

| Date | Close | 10 EMA | 50 SMA | 200 SMA |
|---|---|---|---|---|
| 2026-05-01 | 60.49 | 61.33 | 64.24 | 73.83 |
| 2026-05-15 | 58.01 | 59.19 | 63.01 | 73.39 |
| 2026-05-29 | 54.60 | 56.40 | 60.85 | 72.77 |

**Observations:**
- **Bearish stack confirmed:** Price ($54.60) < 10 EMA ($56.40) < 50 SMA ($60.85) < 200 SMA ($72.77). This is a textbook bearish moving-average alignment.
- The **10 EMA is sloping down** (61.33 → 56.40 over the month) and price has remained below it for nearly all of May — every test of the 10 EMA has been rejected.
- The **50 SMA** dropped from $64.24 to $60.85 in May, showing the medium-term trend has rolled over. Price is now ~10% below the 50 SMA.
- The **200 SMA** is sloping down modestly (73.83 → 72.77). Price is ~25% below the 200 SMA — a deeply oversold structural condition, but also an indication of how powerful the trend is.
- A **death cross** (50 SMA crossing below 200 SMA) likely already occurred during this slide given the divergence in slopes.

**VWMA** at $57.76 vs. price $54.60 also confirms the price is below volume-weighted average — the down-volume is heavier than up-volume, validating distribution.

---

## 4. Momentum (MACD & RSI)

**MACD line:**
- May 1: −1.20 → May 29: −1.79
- The MACD line is **deepening into negative territory**, not improving.

**MACD histogram:**
- A brief flip to positive on **May 20 (+0.032)** suggested fleeting bullish momentum, but it has since collapsed back to **−0.241 on May 29** — a clear failed momentum bounce.
- The histogram is now **expanding to the downside again**, meaning bears have regained control.

**RSI:**
- May 1: 39.8 → May 29: **30.4**
- RSI is **right at the 30 oversold threshold**. Notably, RSI has been **chronically below 50 since early February** — a hallmark of strong bearish trends.
- However, despite price making new lows in late May, RSI on May 29 (30.4) is **higher than RSI on May 12 (30.97)** when price was $57.63. This is an early, tentative **bullish divergence** worth watching, but it is not yet confirmed by price action.

---

## 5. Volatility (Bollinger Lower Band & ATR)

**Bollinger Lower Band:**
- May 29 lower band: **$54.29** vs. close $54.60 — price is **kissing the lower band**.
- Throughout May, price has been "walking the lower band" (May 22 close $56.07 vs. lower band $56.42; May 28 close $54.62 vs. band $54.81). This is characteristic of a **strong, persistent downtrend** rather than a near-term reversal — in such conditions, oversold readings are unreliable timing signals.

**ATR:**
- Currently **$1.37**, which is ~2.5% of price.
- ATR has been **rising** since early May ($1.30 → $1.53 on May 22), then easing slightly to $1.37. Volatility is elevated relative to early May but stable.
- For risk management: a **2x ATR stop ≈ $2.74** of room.

---

## 6. Volume Confirmation (VWMA)

VWMA fell from $62.61 (May 1) to **$57.76 (May 29)**. Price ($54.60) trades meaningfully below VWMA, and the **two largest-volume sessions in May were down/reversal days** (May 13 squeeze rejected; May 21 −$1.83 on heavier flow). This indicates **distribution rather than accumulation**.

---

## 7. Synthesis & Actionable Insights

**Trend:** Decisively bearish across all timeframes (10 EMA, 50 SMA, 200 SMA all sloping down with price below each).

**Momentum:** Bearish, but with an early (unconfirmed) RSI bullish divergence at the 30 line.

**Volatility:** Price hugging the lower Bollinger Band — classic strong-downtrend behavior, not a reliable mean-reversion signal yet.

**Volume:** Distribution confirmed by VWMA above price and reversal days on heaviest volume.

### Trading Implications

- **Trend-following bias:** Remains short/avoid. Any short-term bounce toward the 10 EMA ($56.40) or the falling 50 SMA ($60.85) is more likely to be resistance than a base.
- **Counter-trend long thesis** would require: (a) RSI bullish divergence confirmation with a higher low in price, (b) MACD histogram crossing back above zero with follow-through, (c) close back above the 10 EMA on above-average volume. None of these are confirmed today.
- **Risk levels to watch:**
  - Immediate support: lower Bollinger Band ~$54.29; psychological $54.00.
  - Failure here likely opens a path toward $50 (no nearby technical floor between $54 and $50 in the data).
  - First meaningful resistance: 10 EMA $56.40, then $58.65 (May 20 swing high), then 50 SMA $60.85.
- **Position sizing:** With ATR at $1.37, expect daily ranges of ~2.5%. Stops on shorts logically sit above the 10 EMA + 1 ATR ≈ $57.80.

---

## 8. Summary Table

| Theme | Reading | Signal | Confidence |
|---|---|---|---|
| Long-term trend (200 SMA $72.77) | Price 25% below | **Bearish** | High |
| Medium-term trend (50 SMA $60.85) | Price 10% below, SMA falling | **Bearish** | High |
| Short-term trend (10 EMA $56.40) | Price below, EMA falling | **Bearish** | High |
| MACD ($-1.79) / Histogram ($-0.24) | Both negative, expanding lower | **Bearish momentum** | High |
| RSI (30.4) | At oversold; tentative bullish divergence vs. May 12 | **Caution — possible reversal setup, unconfirmed** | Low-Medium |
| Bollinger Lower Band ($54.29) | Price walking the band | **Strong downtrend; not yet a reversal** | High |
| ATR ($1.37; ~2.5%) | Elevated, stable | **Volatile — wide stops needed** | High |
| VWMA ($57.76) | Price below VWMA; distribution | **Bearish volume confirmation** | High |
| Key resistance | 10 EMA $56.40 → 50 SMA $60.85 | Sell zones | Medium-High |
| Key support | Lower BB $54.29 → $54.00 → open air to $50 | Watch for break | Medium |
| Overall stance | Trend, momentum, volume all bearish; oversold but no confirmed reversal | **Bearish / Avoid longs** | High |

The technical picture is unambiguously bearish at multiple timeframes. While oversold conditions and a tentative RSI divergence warrant monitoring for a counter-trend bounce, **no reversal has been confirmed**, and previous oversold rallies in this trend (March 10 squeeze, May 13 squeeze) were both fully retraced. Trend-followers should remain defensive; bottom-fishers should wait for explicit confirmation (close above 10 EMA + MACD histogram flip + RSI divergence completion).