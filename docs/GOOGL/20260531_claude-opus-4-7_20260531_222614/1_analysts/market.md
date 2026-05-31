I have all the data needed. Note: the verified market snapshot tool was unavailable, so I'll rely on `get_stock_data` and `get_indicators` outputs as the source of truth and flag this in the report.

# GOOGL (Alphabet Inc.) — Technical Analysis Report
**As of close: Friday, May 29, 2026 (current date: 2026-05-31, weekend)**

> ⚠️ Tool note: The `get_verified_market_snapshot` tool was unavailable in this session. All exact values below are sourced directly from `get_stock_data` and `get_indicators` outputs, dated where applicable.

---

## 1. Macro Picture & Price Action Narrative

GOOGL has been in an **explosive uptrend**, with the standout event being the **April 30, 2026 gap up**: the stock opened at $374.07 vs. prior close of $349.94 (a ~+9.9% one-day move, with intraday high $385.84 and close $384.80 on enormous volume of ~72M shares). This took price from a measured uptrend into a parabolic phase that peaked at an intraday high of **$408.61 on May 18, 2026** (close $396.94).

Since that peak, price has consolidated/pulled back into a **$378–$402 range**, ending the week at **$380.34 on May 29** — its weakest close in roughly a month. The most recent session (May 29) was a -2.5% down day on heavy volume (~44.4M shares vs. mid-20Ms recently), indicating distribution.

The wider context (from Nov 2025): the stock has rallied from ~$280 to a peak above $408, an approximately **+45% run in ~6 months**, with the late-April/early-May leg being the most aggressive segment.

---

## 2. Indicator-by-Indicator Read

### Trend (close_50_sma, close_200_sma, close_10_ema)

| Date | Close | 10 EMA | 50 SMA | 200 SMA |
|---|---|---|---|---|
| 2026-04-21 | 332.29 | 327.80 | 308.10 | 273.80 |
| 2026-04-30 | 384.80 | 349.10 | 313.80 | 279.85 |
| 2026-05-15 | 396.78 | 390.69 | 332.74 | 291.06 |
| 2026-05-29 | 380.34 | 387.48 | 347.57 | 299.70 |

- **Long-term trend (200 SMA = $299.70):** Strongly positive. Price is ~27% above the 200 SMA — bullish but indicates the stock is structurally extended.
- **Medium-term (50 SMA = $347.57):** Rising sharply and acting as the dynamic support floor of the rally. Price remains comfortably above it (~$33 cushion). A reasonable mean-reversion target if momentum fully unwinds.
- **Short-term (10 EMA = $387.48):** Crucial — **price closed at $380.34, BELOW the 10 EMA for the first time meaningfully in this leg**. The 10 EMA itself rolled over from a peak of $391.83 on 5/18 to $387.48 on 5/29 — the first short-term momentum loss since the April breakout.

**Verdict:** Long/medium uptrend intact; short-term momentum has cracked.

### Momentum (MACD, MACD Histogram, RSI)

| Date | MACD | MACD Hist | RSI |
|---|---|---|---|
| 2026-05-08 (peak) | 22.19 | +4.40 | **84.03** |
| 2026-05-13 | 20.94 | +1.59 | 75.58 |
| 2026-05-18 | 19.38 | -0.29 | 70.30 |
| 2026-05-22 | 13.62 | -3.54 | 57.49 |
| 2026-05-29 | 9.64 | **-3.90** | 52.90 |

- **MACD line:** Still positive (+9.64) but has fallen from +22.19 on 5/8 — a ~56% decline in momentum strength in three weeks. The line itself remains above zero, so the broader trend is intact, but **directional momentum is decaying fast**.
- **MACD Histogram:** Flipped negative on 5/18 and has expanded into deeper negative territory (-3.90 on 5/29). This is a **bearish crossover already in progress** — MACD line is below its signal line.
- **RSI:** Hit a deeply overbought **84.03 on May 8**, then fell sharply. Now at **52.90**, a near-neutral reading — meaning the overbought condition has been worked off, but momentum is also no longer trending up. There is no oversold opportunity here.

**Verdict:** Momentum unambiguously decelerating; not yet in oversold territory.

### Volatility (Bollinger Upper Band, ATR)

| Date | Close | Boll UB | ATR |
|---|---|---|---|
| 2026-04-29 | 349.94 | 363.90 | 8.22 |
| 2026-04-30 | 384.80 | 373.43 | 10.19 |
| 2026-05-08 | 400.80 | 410.66 | 9.46 |
| 2026-05-18 | 396.94 | 426.37 | 10.02 |
| 2026-05-29 | 380.34 | 404.35 | 9.50 |

- **Bollinger Upper Band:** Peaked at $426.37 on 5/18 and has now compressed to $404.35. Price closed *inside* the bands and well below the upper band — the "riding the band" condition that defined early May has fully broken.
- **ATR:** Surged from ~7.9 in late April to over 10.2 around May 18–20 — confirming the volatility expansion regime triggered by the gap. Has since modestly drifted lower to 9.50 but remains elevated. **Practical implication: a 1-ATR stop is ~$9.50; a 2-ATR stop is ~$19.** Position sizing should reflect this elevated volatility.

**Verdict:** Volatility regime is elevated. The breakout structure has lost its strongest characteristic (band-riding) and is now in mean-reversion mode.

---

## 3. Synthesis: What's the Setup?

**Bull case (still alive):**
- 200 SMA, 50 SMA, and 10 EMA remain in proper bullish stack (10 EMA > 50 SMA > 200 SMA).
- MACD line still well above zero.
- April 30 gap up at ~$365–$374 has not been tested, let alone filled — gaps of that magnitude often act as accumulation zones.
- Pullback from $408 high to $380 is only ~7%, normal post-breakout consolidation.

**Bear / caution case (gathering steam):**
- RSI peaked at 84 — a textbook blow-off momentum reading. Subsequent pullbacks rarely V-bottom from such peaks; they typically retest or build a base.
- MACD histogram has been negative for 8 consecutive sessions and is **expanding negatively**, not contracting — the pullback is gaining downside momentum, not exhausting.
- May 29 closed below the 10 EMA on heavy volume (~44M, ~75% above recent average) — distribution signal.
- Price has lost the upper Bollinger Band (former "trend rail") and is mean-reverting toward the middle band.
- ATR remains elevated (~9.5), meaning whippy two-way action is likely.

**Key levels to watch:**
- **Resistance:** $390 (10 EMA), then $398–$402 (recent highs cluster), then $408 (May 18 high).
- **Support:** $378.46 (May 29 intraday low), then ~$365–$374 (April 30 gap zone — first major test), then 50 SMA at $347.57 (deeper pullback target).

---

## 4. Actionable Insights

1. **Existing long holders:** Trend remains intact above the 50 SMA ($347.57). Trailing stops below the gap zone (~$365) protect most of the rally gains while giving the trend room. Don't add here — risk/reward unfavorable until either a reset to $365 or a reclaim of $390+ on volume.
2. **New long entries:** Wait. RSI is neutral, MACD histogram negative and worsening, and price just lost the 10 EMA. A better entry comes either from (a) a successful retest of the April 30 gap zone ($365–$374) with bullish reversal, or (b) reclaim of $390 with the MACD histogram flipping back positive.
3. **Tactical shorts / hedges:** The setup is more compelling for a short-term tactical pullback trade than a structural short, since the long-term trend is firmly up. A break below $378 with volume could target $365 (gap fill) — about $13 of downside vs. a tight stop above $390, ~3:1 R:R.
4. **Risk management:** Use ATR-based sizing — current ATR ~$9.50 means a 2x ATR stop is ~$19. Avoid tight percent-based stops in this volatility regime.

---

## 5. Summary Table

| Theme | Indicator | Current Reading | Signal | Comment |
|---|---|---|---|---|
| Long-term trend | close_200_sma | $299.70, rising | **Bullish** | Price ~27% above; structurally elevated |
| Medium-term trend | close_50_sma | $347.57, rising | **Bullish** | Acts as primary support floor |
| Short-term trend | close_10_ema | $387.48, just rolled over | **Bearish (turning)** | Price closed below for first time in this leg |
| Momentum (trend) | macd | +9.64, falling | **Neutral/Weakening** | Above zero but down 56% from peak |
| Momentum (early signal) | macdh | -3.90, expanding negative | **Bearish** | 8 sessions negative and worsening |
| Momentum (oscillator) | rsi | 52.90 | **Neutral** | Overbought condition cleared; not oversold |
| Volatility (band) | boll_ub | $404.35 | **Bearish shift** | Price has lost upper-band ride |
| Volatility (range) | atr | $9.50 | **Elevated** | Use 2x ATR (~$19) for stops |
| Recent action | Volume on May 29 | ~44.4M (heavy, -2.5% day) | **Bearish** | Distribution signal |
| Key support | Apr 30 gap zone | $365–$374 | First major test | Untested gap |
| Key resistance | Recent highs | $398–$408 | Reclaim needed | Above $390 to flip short-term tone |

**Overall stance:** Long-term bullish, short-term cautious. The setup favors **patience and waiting for either a gap-zone retest (~$365) for re-entry or a reclaim of $390 with momentum confirmation**, rather than chasing here.