I have all the data I need. Note the verification snapshot tool was unavailable; I'll rely on directly retrieved tool data and clearly attribute every numeric claim.

# CRWD (CrowdStrike Holdings, Inc.) — Technical Analysis Report
**As of: 2026-05-29 close (most recent trading day; 2026-05-31 is a Sunday)**
**Last Close: $731.00** | **Prior Close (5/28): $671.00** | **52-week Trough (Feb 23, 2026): $350.33 intraday low/$350.33 close ≈ $342.72 low**

---

## 1. Why These 8 Indicators Were Selected

CRWD has just executed one of the most violent reversals in its trading history — a ~49% peak-to-trough drawdown from late January to late February 2026, followed by a near-vertical V-shaped recovery that just punched out fresh local highs. This kind of regime requires a balanced toolkit:

| Category | Indicator | Why it's appropriate now |
|---|---|---|
| Long-term trend | `close_200_sma` | Confirms whether the rally has reclaimed the structural trend benchmark after the crash. |
| Medium-term trend | `close_50_sma` | Tracks the slope of the recovery and acts as dynamic support during pullbacks. |
| Short-term momentum | `close_10_ema` | Captures the speed of the rebound; tells us whether price is extended above its short-term mean. |
| Trend momentum | `macd` | Confirms the bullish regime shift after a deeply negative print in early April. |
| Momentum acceleration | `macdh` | Spots momentum exhaustion / divergence before the MACD line crosses. |
| Overbought/oversold | `rsi` | Critical at the moment — readings are extreme; flags reversal risk. |
| Volatility / breakout | `boll_ub` | Quantifies how far above "normal" range the rally has stretched; potential mean-reversion target. |
| Volatility / risk sizing | `atr` | Stop placement & position sizing — ATR has nearly doubled since early April. |

I deliberately excluded redundant overlays: `boll` (middle band) duplicates the 20-SMA already implied; `macds` is implied by MACD + histogram; `vwma` adds little because the recovery has been broadly volume-confirmed (see volume column in raw data).

---

## 2. Trend Structure

**Price vs. moving averages (5/29 close = $731.00):**
- **10 EMA:** $649.12 → price is **+$81.88 / +12.6% above** the 10 EMA. Extreme short-term extension.
- **50 SMA:** $482.51 → price is **+$248.49 / +51.5% above** the 50 SMA.
- **200 SMA:** $470.24 → price is **+$260.76 / +55.5% above** the 200 SMA.

**Slope inflection points:**
- 50 SMA bottomed at **$405.17 on 4/16** and has risen every session since — now $482.51 (+19.1%). This is a textbook trend reversal in the medium-term mean.
- 200 SMA bottomed at **$457.49 on 5/06** and has just begun to curl up. Price retook the 200 SMA only on **5/04** (close $469.24 vs. 200 SMA $457.55) — about 4 weeks ago.
- Golden-cross watch: 50 SMA ($482.51) is closing in on the 200 SMA ($470.24), gap = $12.27 and narrowing fast. **A bullish 50/200 cross looks likely within 1–3 weeks** if price holds above ~$500.

**Conclusion:** Multi-timeframe trend has flipped cleanly bullish. However, the *degree* of extension above all three averages is historically rare and unsustainable without consolidation.

---

## 3. Momentum (MACD + RSI)

**MACD line history (selected):**
| Date | MACD | MACD Hist |
|---|---|---|
| 2026-04-01 | -8.55 | -3.29 |
| 2026-04-17 | +0.25 | +3.11 |
| 2026-05-04 | +13.62 | +3.06 |
| 2026-05-15 | +39.81 | +11.84 |
| 2026-05-22 | +56.43 | +12.40 |
| 2026-05-26 | +58.50 | +11.58 |
| 2026-05-29 | **+62.41** | **+9.30** |

- MACD crossed above zero on/around **4/17** and has since posted a near-uninterrupted climb to **+62.41** — among the highest readings in the dataset.
- **However**, the histogram has begun to *contract* (peak +13.46 on 5/20, now +9.30). This is a **subtle early warning of decelerating bullish momentum** — not a reversal yet, but the second derivative has turned negative.

**RSI (14):**
| Date | RSI |
|---|---|
| 2026-04-10 | 41.32 |
| 2026-05-04 | 63.83 |
| 2026-05-08 | 74.15 |
| 2026-05-18 | 84.82 |
| 2026-05-26 | 87.44 (peak in window) |
| 2026-05-27 | 75.81 |
| 2026-05-29 | **83.80** |

- RSI has been **above 70 since 5/07** — 16 consecutive trading sessions of overbought readings.
- RSI re-acceleration on 5/29 (75.81 → 83.80) confirms the breakout is real, but every print above 80 raises tail risk of mean reversion.
- **Look for bearish RSI divergence**: a new price high paired with a lower RSI peak (5/26 RSI 87.44 was the high; 5/29 RSI 83.80 is *lower* despite price reaching $731 — **a mild negative divergence is already forming**).

---

## 4. Volatility & Bollinger Context

- **Bollinger Upper Band (5/29): $744.65** vs. close $731.00. Price is **~$13.65 below the upper band**, but has been "riding the band" since 5/07.
- The upper band itself has been climbing aggressively (from $484.03 on 5/04 to $744.65 on 5/29 = +53.8%), reflecting a volatility expansion regime. In strong trends, riding the band is bullish — but historically this only persists for several weeks.
- **ATR (14): $28.78 on 5/29**, up from **$18.12 on 5/05** (+58.8%). One ATR is now ~3.9% of price. This means:
  - A normal daily swing should be expected in the **±$25–$30 range**.
  - A reasonable **stop-loss for long positions: ~2× ATR below entry ≈ $58** wide, or roughly the $670–$675 area as a first volatility-based stop.

---

## 5. Key Price Reference Points (from raw OHLC data)

- **Crash low:** Feb 23, 2026 — intraday low **$342.72**, close $350.33 on **15.08M volume** (largest in window).
- **Pre-crash high:** Jan 27, 2026 — intraday high **$487.20**.
- **Recovery breakout above pre-crash high:** May 7, 2026 (close $505.72 on 5.11M volume).
- **Latest blow-off candle:** May 29, 2026 — open $677.43, high $731.49, close $731.00, volume **4.81M** (above 30-day average). Strong close near highs = no sign of distribution yet.
- **Recent gain:** From the 4/10 closing low of $379.02 to 5/29 close of $731.00 = **+92.9% in 34 trading sessions**.

---

## 6. Synthesis & Actionable Insights

**Bullish evidence (dominant):**
1. Price > 10 EMA > 50 SMA > 200 SMA — perfect trend stacking.
2. MACD strongly positive and rising; impending 50/200 SMA golden cross.
3. Breakout above prior high ($487) confirmed by volume on 5/07 and again on 5/29.
4. Closes near daily highs = institutional accumulation pattern.

**Cautionary evidence (rising):**
1. RSI 83.8, overbought for 16 sessions — historically extreme.
2. Mild bearish RSI divergence (lower RSI high on 5/29 vs. 5/26 despite higher price).
3. MACD histogram has rolled over from its 5/20 peak.
4. Price is +12.6% above the 10 EMA — every prior such extension in this dataset (e.g., late January: $487 vs. 10 EMA ~$465) preceded a multi-day pullback.
5. ATR has nearly doubled since early May; volatility regimes this hot rarely persist without a shakeout.

**Trade construction ideas:**
- **For trend-followers already long:** Trail stops to ~$670 (just below 5/27 swing low + ~1 ATR buffer). Don't add aggressively here.
- **For new entries:** Avoid chasing $731. Wait for a pullback to the **10 EMA zone (~$650)** or a tag of the **20-day Bollinger middle**, where risk/reward improves materially. A reset of RSI to 55–65 would be ideal.
- **For mean-reversion / hedgers:** The **$744 Bollinger upper band** is the natural near-term resistance. A failure to break through with a daily close back below $700 could trigger a 5–10% mean-reversion move toward the 10 EMA.
- **Invalidation of bull thesis:** Daily close below the **50 SMA ($482)** would void the breakout structure.

---

## 7. Summary Table

| Theme | Reading (5/29/26) | Interpretation | Actionable Implication |
|---|---|---|---|
| Long-term trend (200 SMA) | Price $731 vs. SMA $470.24 | Strongly bullish; just reclaimed in early May | Macro trend supports longs |
| Medium-term trend (50 SMA) | $482.51, rising | Bullish recovery; nearing golden cross with 200 SMA | Add on pullbacks to 50 SMA |
| Short-term momentum (10 EMA) | $649.12; price +12.6% above | Severely extended | Don't chase; wait for revert |
| MACD | +62.41 (near window high) | Strong bullish momentum | Trend intact |
| MACD Histogram | +9.30, down from +13.46 peak (5/20) | Decelerating momentum | Early warning of consolidation |
| RSI (14) | 83.80; overbought 16 sessions | Extreme overbought; mild bearish divergence forming | Tighten stops; expect chop |
| Bollinger Upper Band | $744.65 | Near-term resistance ~$13 above | Mean-reversion risk into the band |
| ATR (14) | $28.78 (≈3.9% of price) | Volatility nearly doubled in 4 weeks | Use ~2× ATR ($58) stops; size down |
| Key support | 10 EMA $649 → 50 SMA $482 | Layered support | Pullback buy zones |
| Key resistance | $744 (BB upper) → psychological $750 | Near-term ceiling | First profit-take zone |
| Bull invalidation | Daily close < $482 (50 SMA) | Would break recovery structure | Exit longs |

**Note on data verification:** I attempted to call `get_verified_market_snapshot` as instructed, but that tool was not available in this environment (returned an error). All numeric claims above are sourced directly from `get_stock_data` and `get_indicators` outputs printed in this session, with dates referenced explicitly. No support/resistance bounce is claimed without a corresponding date and price from those tool outputs.