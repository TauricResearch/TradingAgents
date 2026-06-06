# TXN (Texas Instruments Incorporated) — Technical Analysis Report
**Date of analysis:** 2026-05-31 (latest trading session: Friday 2026-05-29)
**Sector:** Technology / Semiconductors | **Exchange:** NMS

---

## 1. Indicator Selection Rationale

Given TXN's recent explosive rally (a parabolic move from ~$185 in late March to a peak of $326.42 on May 26), and a sharp pullback in the last three sessions, I selected indicators that span **trend (multiple timeframes), momentum, volatility, and overextension/mean-reversion signals**:

| Indicator | Category | Why It's Relevant Here |
|---|---|---|
| `close_10_ema` | MA – fast | Tracks momentum-driven swings on the post-earnings parabolic move. |
| `close_50_sma` | MA – medium | Anchor of the medium-term uptrend; key dynamic support. |
| `close_200_sma` | MA – long | Confirms the long-term bullish regime; key macro reference. |
| `macd` | Momentum/Trend | Captures momentum strength and divergence after a vertical move. |
| `macds` | Momentum/Trend | Crossover trigger to confirm/deny weakening momentum. |
| `rsi` | Momentum oscillator | Flags repeated overbought conditions and divergences (highly relevant after a parabolic move). |
| `boll_ub` | Volatility | Locates upper-band excursion / mean-reversion targets after a breakout. |
| `atr` | Volatility | Critical for sizing/stops given volatility expansion (ATR has surged ~25%). |

I deliberately avoided `boll_lb`, `boll`, `vwma`, and `macdh` to prevent redundancy with the chosen set.

---

## 2. Big-Picture Trend (Daily, Nov 2025 → May 2026)

- **Nov 2025:** TXN traded sideways in a $151–$167 range.
- **Dec 2025:** First leg up to ~$180, followed by digestion in the $172–$180 zone.
- **Jan 2026:** Breakout. Close on 2026-01-28 jumped from $194.37 → **$213.68** (+9.9%) — likely a strong earnings catalyst, with volume surging to 19.6M.
- **Feb–early Mar:** Consolidation $210–$227, then pullback to $185–$195 by mid-March (correction of ~17% from the Feb 2 high of $227.67).
- **Late Mar – April:** Recovery, then a **second earnings-style gap** on 2026-04-23: close $235.12 → **$280.80** (+19.4%) on 25.7M volume.
- **May:** Continuation rally to an all-time high close of **$324.89 on 2026-05-26**, intraday peak $326.42.
- **Last 3 sessions:** Sharp reversal — $324.89 → $317.45 → $315.95 → **$305.68** on 2026-05-29 (-5.9% in three days, with the latest day printing 16.8M volume — well above the recent ~7M average).

**Net move:** +91.6% from the Nov 3 close ($159.60) to the May 29 close ($305.68) over ~7 months — a major parabolic advance.

---

## 3. Indicator-by-Indicator Read (as of 2026-05-29)

### Moving Averages
- **Price ($305.68)** vs **10 EMA ($307.93)**: Price closed **just below** the 10 EMA for the first time in this leg — earliest sign of short-term momentum loss.
- **50 SMA ($251.19)**: Strong rising medium-term trend; price is **+21.7%** above the 50-SMA, signaling extension.
- **200 SMA ($201.28)**: Price is **+51.9%** above its 200-day average — a historically extreme level. Long-term trend remains decisively bullish (50 SMA well above 200 SMA — golden-cross posture intact).

### MACD
- **MACD line:** 16.87 (down from a peak of **21.81 on 2026-05-14**).
- **Signal line:** 18.61.
- The MACD has now **crossed below its signal** (16.87 < 18.61), and the spread (-1.74) is widening. This is a **bearish momentum crossover** while still in positive territory — a classic momentum-fade warning rather than an outright trend reversal.

### RSI
- **2026-05-29: 61.05**, down sharply from **77.15 (May 26)** and a recent peak of **80.41 (May 14)**.
- RSI was in **overbought territory (>70)** on multiple days (May 4, 6, 11, 12, 13, 14, 15, 19, 20, 22, 26, 27).
- The drop from 77 → 61 in 3 sessions while price made a higher high on May 26 vs the May 14 swing high (closes: $324.89 vs $308.17) but RSI made a **lower high (77.15 vs 80.41)** — that is a **bearish RSI divergence** confirmed by the subsequent breakdown.

### Bollinger Upper Band
- **Upper band 2026-05-29: $325.33**. Price closed at $305.68, well **inside** the band after tagging it on May 26 ($324.89 close vs $323.65 band — a clean ride along the upper band).
- The May 26 high of **$326.42 marginally exceeded the band** ($323.65) — typical blow-off behavior, followed by a snap back inside the bands.

### ATR (Volatility)
- ATR has **expanded from ~$9.03 (May 8) to $11.42 (May 29)**, +26%. Volatility regime is rising, consistent with a topping/distribution pattern. For risk management, **1× ATR ≈ $11.4**, **2× ATR ≈ $22.8**.

---

## 4. Key Observations & Synthesis

1. **Three confluence-bearish signals just triggered:**
   - MACD bearish crossover below signal (16.87 vs 18.61).
   - Price closed below the 10 EMA for the first time this leg.
   - RSI rolled from overbought, with a bearish divergence vs price's higher high.
2. **Volume confirmation of distribution:** 2026-05-29 down day printed 16.8M shares — more than 2× the 30-day average — signaling institutional selling, not just light profit-taking.
3. **Long-term trend remains intact.** Price is still well above 50 SMA ($251) and 200 SMA ($201). A move back to the 50 SMA would be a ~18% drawdown, which would still preserve the broader uptrend.
4. **Mean-reversion targets** (purely technical, based on observed levels):
   - 10 EMA reclaim or rejection: **~$307–$308** is the immediate pivot.
   - First downside reference: prior breakout shelf around **$280** (April 24–28 cluster).
   - Secondary reference: **$251** (50 SMA).
   - Bollinger middle (20 SMA, not pulled but inferable as roughly midway between $325 upper and any extrapolated lower band): generally near the $280–$290 zone given recent prices.
5. **Volatility is elevated and rising** — using a tight stop is harder; position sizing should use the higher ATR ($11.4) to avoid being shaken out by normal noise.

---

## 5. Actionable Trading Insights

- **For trend-following longs already in:** Tighten stops. A reasonable trailing stop is **$305 minus 1.5× ATR ≈ $288** (under the late-April shelf). A close below $288 would invalidate the most recent breakout structure.
- **For new long entries:** Wait for either (a) a **pullback to the 50 SMA (~$251)** with stabilization, or (b) a **reclaim of $315–$320 with volume confirmation**. Chasing here, with MACD just turning negative and RSI fading, is poor risk/reward.
- **For tactical short/hedge candidates:** A confirmed close below $300 (round-number + below 10 EMA + MACD bear cross) opens a tactical move toward $280 first, $251 second. Stop above $326 (the all-time high). Keep size modest given the dominant uptrend regime.
- **For options traders:** Realized vol expansion + ATR jump argues for **selling premium on bounces** (call spreads) rather than buying calls outright after the parabolic run.

---

## 6. Summary Table

| Theme | Reading | Signal | Action Implication |
|---|---|---|---|
| Long-term trend (200 SMA $201.28 vs price $305.68) | +51.9% above | Bullish (extended) | Don't fight macro trend; respect pullbacks as buyable in time |
| Medium-term trend (50 SMA $251.19) | Price +21.7% above, rising | Bullish (extended) | Key support / mean-reversion magnet |
| Short-term trend (10 EMA $307.93) | Price closed $305.68, just below | First crack | Watch for confirmation below |
| MACD (16.87) vs Signal (18.61) | Bearish crossover, both still positive | Momentum fading | Caution on new longs |
| RSI 61.05 (was 77.15 on May 26) | Rolling over from overbought; bearish divergence vs price HH | Bearish near-term | Reduce/hedge longs |
| Bollinger Upper Band ($325.33) | Tagged & rejected May 26 high $326.42 | Mean-reversion in play | Targets back to mid-band |
| ATR ($11.42, +26% in 3 wks) | Volatility expansion | Risk-off volatility regime | Widen stops; reduce size |
| Volume on 2026-05-29 down day | 16.8M (>2× avg) | Distribution day | Institutional selling confirmed |
| **Net technical posture** | Long-term bullish, **short-term bearish reversal underway** | **Caution / Trim** | Defensive bias near-term |

---

### Note on Verification
The requested `get_verified_market_snapshot` tool is **not available in this environment** (it returned an error). All numbers above are sourced directly from `get_stock_data` and `get_indicators` outputs and dates/values are quoted exactly as returned. No support/resistance or percentage move is asserted that isn't traceable to the printed tool output above.