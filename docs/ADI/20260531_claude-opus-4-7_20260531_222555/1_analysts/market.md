# ADI (Analog Devices, Inc.) — Technical Analysis Report
**As of 2026-05-29 (most recent trading day before 2026-05-31, a Sunday)**

## 1. Indicator Selection Rationale

For ADI's current market context — a stock that has experienced a powerful multi-month uptrend punctuated by a sharp recent volatility spike — I selected eight complementary indicators spanning trend, momentum, volatility, and confirmation:

| Indicator | Category | Why It's Suitable Here |
|---|---|---|
| close_200_sma | Long-term trend | Confirms the overarching bullish regime; useful for assessing how stretched price is from the long-term mean. |
| close_50_sma | Medium-term trend | Acts as the primary dynamic support during the rally; key reference for swing traders. |
| close_10_ema | Short-term trend | Captures the current momentum shift after the late-May sell-off and rebound. |
| macd | Momentum | Tracks underlying momentum strength; recently turning lower from peak readings. |
| macdh | Momentum (early signal) | Histogram is currently negative — early warning that momentum has rolled over even as MACD line stays positive. |
| rsi | Momentum / overbought-oversold | Recently came off extreme overbought (>80) levels; mid-range now, indicating cooling. |
| boll_ub | Volatility / breakout | Helps assess whether the late-April/early-May "riding the upper band" episode is exhausting. |
| atr | Volatility (risk management) | ATR has nearly doubled (from ~$10 to ~$15.5) in 6 weeks — critical for sizing stops in this regime. |

I deliberately excluded `boll` and `boll_lb` (redundant with `boll_ub` for the current setup) and `vwma` (volume-weighted trend already captured by SMAs in this single-name analysis), and `macds` (redundant given we have macd + macdh).

---

## 2. Price Action Overview

ADI has rallied from the **~$226–$232 range in early November 2025** to a peak of **$432.39 (close) on 2026-05-13** — a ~86% gain in roughly six months. Key inflection points from the OHLCV data:

- **Nov 24–28, 2025**: Breakaway gap higher from ~$230 to ~$263 on heavy volume (likely earnings/news catalyst — Nov 25 saw 7.5M shares vs. ~3M average).
- **Dec 2025 – early Jan 2026**: Steady advance to ~$300, brief consolidation around $270–$285.
- **Late Jan – Feb 2026**: Aggressive trend leg from $300 → $360 with a sharp acceleration on Feb 18 (+$8.83) and Feb 20 (+$9.70).
- **March 2026**: First meaningful pullback — peaked at $359.67 on Feb 25, then declined to $303.10 on Mar 30 (a ~16% drawdown).
- **April 2026**: V-shaped recovery; explosive rally from $303 to **$403.88 (Apr 23)** in ~3 weeks (+33%).
- **May 2026**: Push to all-time high of **$432.39 on May 13**, followed by a sharp two-day flush — May 20 dropped to $398.05 on the highest volume of the dataset (10.35M), May 21 closed at **$384.21** (intraday low $381.22). Recovery into May 26–29 saw price bounce back to **$413.85** (close, May 29) but with elevated volatility (May 27 high $433.50 was rejected, closing at $416.88).

---

## 3. Trend Structure (Moving Averages)

| Date | Close | 10-EMA | 50-SMA | 200-SMA |
|---|---|---|---|---|
| 2026-05-29 | **$413.85** | $411.86 | $373.62 | $297.59 |
| 2026-05-13 (peak) | $432.39 | $412.52 | $352.92 | $287.21 |
| 2026-04-01 | $320.58 | $314.79 | $323.55 | $266.15 |

- **Bullish stacking intact**: Price > 10-EMA > 50-SMA > 200-SMA. This is a textbook bullish alignment.
- The **50-SMA at ~$373.62** is the most relevant medium-term support. Price is ~10.8% above it — historically a stretched but not extreme premium for this stock.
- The **200-SMA at ~$297.59** is ~28% below current price, indicating the rally is significantly extended over the long-term mean.
- The **10-EMA ($411.86)** is now acting as a near-term magnet/support; the May 21 low of $381.22 broke below the 10-EMA briefly before reclaiming it.

---

## 4. Momentum (MACD & RSI)

**MACD** peaked at **20.33 on May 13** and has rolled over to **9.51 on May 29** — a ~53% drop in the MACD line in two weeks while price remains near highs. This is a **classic bearish momentum divergence forming**:
- May 13 close: $432.39, MACD: 20.33
- May 29 close: $413.85, MACD: 9.51 (price down ~4%, momentum down ~53%)

**MACD Histogram** flipped from positive (+1.38 on May 13) to **negative (-2.45 on May 29)**, with the deepest negative reading at **-5.51 on May 22**. The signal line has crossed above the MACD line — a bearish crossover already triggered around May 18–19.

**RSI** trajectory:
- Apr 23 peak: **80.37** (overbought, classic blow-off)
- May 13: 73.74 (still overbought)
- May 21 low: **44.66** (rapid mean reversion)
- May 29: **56.19** (neutral)

The RSI cooling from 80+ to mid-50s without breaking the 40 floor is constructive — it has digested overbought conditions without breaking the uptrend's momentum floor. However, the failure to push back above 60 on the May 26–29 rebound suggests buyers are losing conviction.

---

## 5. Volatility Regime

**ATR has expanded dramatically:**
- April 1: **$10.13**
- May 1: $11.30
- May 29: **$15.45** (+52% in 8 weeks)

This is a major risk-management signal. The recent two-day range of May 20 ($383.85 low) to May 13 ($435.72 high) = ~$52, which is ~3.4x ATR. **Volatility regime has shifted higher**, requiring wider stops and smaller position sizes.

**Bollinger Upper Band** at **$436.09 on May 29**. Price action notes:
- Apr 23 close ($403.88) actually exceeded the upper band ($400.50) — a strong breakout signal.
- May 13 high ($435.72) tagged the upper band ($436.33) and was rejected.
- Current price ($413.85) is ~5% below the upper band, in the upper half of the band — consistent with an uptrend that is consolidating, not yet breaking down.

---

## 6. Synthesis & Actionable Insights

**Bullish factors:**
1. All major MAs in bullish alignment (10-EMA > 50-SMA > 200-SMA).
2. Long-term trend strongly intact — 200-SMA rising steadily (from $266 to $297 in two months).
3. RSI cooled from overbought without breaking down — healthy consolidation.
4. May 21 selloff to $381.22 was bought aggressively (May 26 closed back at $419.94, +9% in two sessions).

**Bearish/Cautionary factors:**
1. **MACD bearish divergence** — momentum peaked May 13, has fallen sharply while price held up.
2. **MACD histogram flipped negative** — momentum deceleration confirmed.
3. **Volatility (ATR) up 52%** — large two-way swings; May 27 saw an intraday range from $433.50 → $407.78 (rejected breakout).
4. Price extended ~28% above 200-SMA — historically prone to mean reversion.
5. Recent price action (May 20–29) shows a series of failed pushes above $420; potential **lower high pattern** forming if $420–$425 is not reclaimed.

**Actionable Trading Insights:**
- **Key support zones**: (a) 10-EMA at ~$412 (immediate), (b) 50-SMA at ~$374 (critical medium-term), (c) prior breakout zone $380 (May 21 low).
- **Key resistance**: $432–$436 (May 13 high & Bollinger upper band).
- **Stop-loss sizing**: With ATR at $15.45, a 1.5x ATR stop = ~$23 wide; 2x ATR = ~$31. Position sizes should be reduced vs. the April regime when ATR was $10.
- **Trade thesis**: The trend is up, but momentum is fading and volatility is elevated. This is **not a high-conviction trend-following entry zone**. A pullback toward the 50-SMA (~$374) would offer a more attractive risk/reward if the bullish structure holds. Aggressive longs near current levels carry asymmetric downside given divergence + ATR expansion.

---

## 7. Summary Table

| Dimension | Reading | Signal | Comment |
|---|---|---|---|
| Long-term trend (200-SMA $297.59) | Price 28% above | **Bullish but stretched** | Steady upward slope intact |
| Medium-term trend (50-SMA $373.62) | Price 10.8% above | **Bullish** | Primary dynamic support |
| Short-term trend (10-EMA $411.86) | Price slightly above | **Neutral-Bullish** | Tested as support May 21 |
| MACD line (9.51) | Positive but falling fast from 20.33 peak | **Bearish divergence** | Momentum deceleration |
| MACD histogram (-2.45) | Negative for ~6 sessions | **Bearish** | Signal line cross confirmed |
| RSI (56.19) | Down from 80.37 on Apr 23 | **Neutral** | Healthy reset, not oversold |
| Bollinger Upper Band ($436.09) | Price 5% below | **Resistance overhead** | May 13 rejection at the band |
| ATR ($15.45) | Up 52% from April | **Elevated risk** | Wider stops required |
| Recent price ($413.85) | Below May 13 high $432.39 | **Consolidation / lower high risk** | Watch $420–$425 reclaim |

**Overall Bias**: Trend remains up, but momentum and volatility signals counsel **caution at current levels**. Better risk/reward likely on a pullback toward the $374–$385 zone (50-SMA / prior breakout). Avoid chasing into resistance at $432–$436 without a momentum re-acceleration confirmed by MACD histogram turning back positive.