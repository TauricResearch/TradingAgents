I have a comprehensive dataset. Note that `get_verified_market_snapshot` is not available in this environment — I'll rely on `get_stock_data` and `get_indicators` outputs as my source of truth and cite specific dates/values rather than invent reconciled numbers.

# AMD Technical Analysis Report — As of 2026-05-31

## 1. Executive Summary

Advanced Micro Devices (AMD) is in the midst of an **explosive parabolic uptrend** that began in early April 2026 and accelerated dramatically from late-April onward. The stock has more than doubled in roughly six weeks (from ~$200 in late March to $516.10 close on 2026-05-29). All trend indicators are aligned bullishly, momentum is at multi-month extremes, but several short-term overheating signals (RSI pinned near 75–81, price riding the upper Bollinger Band, ATR almost doubling) suggest the risk/reward of fresh long entries is deteriorating. This is a "trend-following — but trail stops aggressively" tape rather than a "fresh chase" setup.

---

## 2. Indicator Selection Rationale

For a momentum-driven, post-breakout, high-volatility regime, I selected 8 complementary indicators:

| Indicator | Category | Why chosen for AMD here |
|---|---|---|
| close_10_ema | Moving Avg (short) | Tracks the steep momentum & defines tactical pullback zones |
| close_50_sma | Moving Avg (medium) | Anchors the prevailing intermediate uptrend / dynamic support |
| close_200_sma | Moving Avg (long) | Confirms long-term regime (golden-cross context) |
| MACD | Momentum/Trend | Quantifies momentum thrust vs prior baselines |
| MACD Histogram | Momentum (early signal) | Spots momentum *deceleration* before crossover |
| RSI | Momentum/Oscillator | Flags overbought extremes; divergence early-warning |
| Bollinger Upper Band | Volatility/Breakout | Identifies "riding the band" vs mean-reversion risk |
| ATR | Volatility | Sizing & stop placement in a now-violent tape |

(I omitted `boll_lb` and `boll` because the action is firmly on the upper band side; `vwma` was deprioritized since price/volume are both confirming — adding little incremental info beyond MACD.)

---

## 3. Trend Structure

**Long-term (200 SMA)**: Rising steadily — 2026-04-01: $196.43 → 2026-05-29: $237.58. Price ($516.10) sits **~117% above the 200 SMA**, an unusually wide premium that reflects the parabolic move.

**Medium-term (50 SMA)**: Inflected sharply higher — 2026-04-01: $212.28 → 2026-05-29: $328.15. The slope steepened markedly after May 6. Price is **~57% above the 50 SMA** — extreme stretch.

**Short-term (10 EMA)**: 2026-05-01: $324.49 → 2026-05-29: $476.48. The 10 EMA is now $40+ below close, but it is the *only* moving average within reasonable striking distance and is the realistic level for a tactical pullback.

**Stack**: Price > 10 EMA > 50 SMA > 200 SMA — textbook bullish alignment.

---

## 4. The Parabolic Phase: Key Dated Events

From the OHLCV data:
- **2026-05-05 close**: $355.26
- **2026-05-06**: Gap up — opened $409.49, closed $421.39 on **87.7M volume** (vs ~30–40M typical). This was the catalyst breakout day.
- **2026-05-08**: Closed $455.19 (high of $456.29) on 58.1M volume.
- **2026-05-15 → 2026-05-19**: A brief consolidation/pullback to $414.05 close (low of $393.36 intraday on 5/19) — held above the 10 EMA zone.
- **2026-05-22**: Reaccelerated, closed $467.51.
- **2026-05-26**: Hit intraday high $506.96, closed $503.89.
- **2026-05-28**: New intraday high $527.20, closed $518.09.
- **2026-05-29 close**: $516.10 (down marginally from prior day).

---

## 5. Momentum (MACD & RSI)

**MACD line** climbed from 19.02 (2026-04-21) → peak 52.85 (2026-05-14) → 49.86 (2026-05-29). It briefly cooled in the 5/19–5/22 dip (43.3) and is now re-expanding — but **lower than its May 14 peak even though price is higher**. This is an early *bearish momentum divergence* warning to monitor (not yet confirmed).

**MACD Histogram** went deeply negative on 5/19–5/22 (-2.18 to -2.29), then flipped back positive (+2.95 on 5/29). Momentum has re-accelerated, but the prior peak histogram of +11.37 (5/11) is far above current readings — confirming the divergence concern.

**RSI** has been overbought for most of May:
- 5/06: 81.18, 5/11: 81.09, 5/08: 80.78
- Cooled to 63.81 on 5/19 (only "neutral" reading recently)
- Back to 75.98 on 5/29.

RSI staying in the 70–80 zone in a strong uptrend is normal — but combined with MACD divergence, it argues the trend is *mature*, not nascent.

---

## 6. Volatility Regime

**ATR** has nearly doubled in one month: 2026-05-01: $15.80 → 2026-05-29: $26.03. Daily true ranges of $25+ are now baseline. Implications:
- A standard 1×ATR stop = ~$26; a 2×ATR stop = ~$52.
- Position sizes should be cut roughly in half versus April-era sizing to keep dollar risk constant.
- Whipsaw risk is high; intraday swings of 4–6% are routine.

**Bollinger Upper Band**: 2026-05-29 = $539.11. Close ($516.10) is just below the upper band. AMD has been "riding the band" since 5/06 — characteristic of strong trends, but means any close that fails to make a new high while bands widen is a mean-reversion warning.

---

## 7. Volume Confirmation (from OHLCV)

- 5/06 breakout: **87.7M** (massive)
- 5/08 thrust: 58.1M
- 5/22 acceleration: 34.8M
- 5/26 new high: 38.5M
- 5/27 reversal day (close $495.54 below open $508.00): 27.6M
- 5/28 outside-up day: 31.4M
- 5/29: 30.7M

Volume on the *initial* breakout was huge, but recent up-days are coming on average volume — another subtle sign of buyer exhaustion at the margin.

---

## 8. Levels That Matter

| Level | Price | Type |
|---|---|---|
| Recent intraday high | $527.20 (5/28) | Resistance |
| Bollinger Upper Band | $539.11 (5/29) | Volatility cap |
| Prior swing high (consolidation) | $469.22 (5/11) | Tactical support |
| 10 EMA | $476.48 (5/29) | First defense / pullback target |
| Breakout origin / gap base | ~$420 (5/06 area) | Major support — break = trend damage |
| 50 SMA | $328.15 (5/29) | Major support if trend resets |

---

## 9. Actionable Insights

**For trend-followers already long**: Hold, but **trail a stop** to either (a) the 10 EMA (~$476) or (b) below the 5/19 swing low ($393.36). A close below $420 (gap origin) would substantially damage the technical structure.

**For new entries**: Chasing here is unfavorable. Risk to a logical stop (10 EMA, ~$40 away) is large in absolute dollar terms, and the MACD/RSI divergence flags raise the odds of at least a multi-day cooling phase. Wait for either (i) a pullback to the 10 EMA with bullish reversal candle, or (ii) a tight 2–3 day consolidation that resolves higher on volume.

**For mean-reversion / fade traders**: Set-up is *brewing* but not yet confirmed. Need to see (a) a clean lower high, (b) MACD histogram turning negative, and (c) a daily close below the 10 EMA before short attempts.

**Sizing**: With ATR at $26, a 2-ATR stop = ~$52, or ~10% of price. Size positions accordingly — full-sized April positions would now carry double the dollar volatility.

---

## 10. Key Risks to the Bullish Thesis

1. **Bearish MACD divergence forming** (lower MACD high vs higher price high).
2. **Volume not expanding** on most recent push to highs (5/27–5/29 ~28–31M vs 87M on 5/06).
3. **Extreme stretch from 50 SMA (+57%) and 200 SMA (+117%)** — historically prone to mean reversion.
4. **5/27 bearish daily candle** (open $508, close $495.54) — first warning shot.
5. **ATR doubling** = greater odds of a violent reversal day.

---

## Summary Table

| Dimension | Reading | Signal | Conviction |
|---|---|---|---|
| Long-term trend (200 SMA) | Rising; price 117% above | Bullish | High |
| Medium trend (50 SMA) | Steep slope; price 57% above | Bullish but stretched | High |
| Short-term (10 EMA at $476.48) | Price above; first support | Bullish | High |
| MACD line (49.86 on 5/29) | Positive but below 5/14 peak | Bullish, weakening | Medium |
| MACD Histogram (+2.95) | Re-expanding from negative | Cautiously bullish | Medium |
| RSI (75.98 on 5/29) | Overbought, in trend zone | Bullish trend / OB warning | Medium |
| Bollinger Upper Band ($539) | Riding the band | Strong trend / extension risk | Medium |
| ATR ($26.03) | Doubled in 30 days | Volatility expansion — risk-management critical | High |
| Volume confirmation | Strong on 5/06 breakout, average since | Mild non-confirmation | Medium |
| Net bias | **Trend = up; entries = unfavorable; trail stops** | **Hold longs / no fresh chase** | High |

---

*Note on verification: The `get_verified_market_snapshot` tool was not available in this environment. All numerical claims above are sourced directly from `get_stock_data` and `get_indicators` outputs with explicit dates; I have not invented reconciled values.*