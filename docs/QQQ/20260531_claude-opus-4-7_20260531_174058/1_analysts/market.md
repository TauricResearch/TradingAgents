I have all the data I need. Let me write up the detailed analysis.

---

# QQQ (Invesco QQQ Trust) — Technical Analysis Report
**Date:** 2026-05-31 (last completed trading day: 2026-05-29)

> ⚠️ **Note on verification:** The `get_verified_market_snapshot` tool was unavailable in this environment. All numbers below are sourced directly from `get_stock_data` and `get_indicators` outputs, with explicit dates attached so they can be independently verified.

---

## 1. Price Action Context

QQQ's path over the last 7 months reveals three distinct regimes:

| Phase | Window | Range | Behavior |
|---|---|---|---|
| Range / drift | Nov 2025 – mid-Jan 2026 | ~$584 – $632 | Choppy, mostly trading $605–$625 |
| Sharp correction | Late-Jan – late-March 2026 | $632 → $558.28 (low 3/30/26) | ~−11.7% drawdown; high-volume distribution days (e.g., 2026-03-27 vol 82.7M, 03-26 vol 81.5M) |
| V-shaped rally | Apr 7 → May 29 2026 | $588.59 → $738.31 | **+25.4% in ~7.5 weeks**; largest gap-up 2026-04-08 ($588.59 → $606.09) following a hammer-style reversal off the $558 low |

Most recent close (2026-05-29): **$738.31**, all-time-high territory for this dataset. Volume on the late-May rally remains healthy (32–37M typical), but **not climactic** — i.e., there is no obvious blow-off volume signature yet.

---

## 2. Moving-Average Structure (Trend)

| MA | Value (2026-05-29) | Price vs. MA | Slope |
|---|---|---|---|
| 10 EMA | 722.46 | Price +2.2% above | Sharply rising (was 657.50 on 2026-05-01 → +9.9% in a month) |
| 50 SMA | 652.90 | Price +13.1% above | Rising steadily (612.34 → 652.90 in May) |
| 200 SMA | 616.82 | Price +19.7% above | Slowly rising (602.86 → 616.82 in May) |

**Interpretation:**
- Stack is textbook bullish: **Price > 10 EMA > 50 SMA > 200 SMA**, all sloping up.
- The gap between price and 50 SMA (~$85) and 200 SMA (~$121) is **historically wide** — this is a classic *extended* condition. Mean-reversion trades back toward the 10 EMA (~$722) or the rising 50 SMA are higher-probability than initiating fresh longs at this exact level.
- No imminent death-cross/golden-cross risk; the 50/200 spread is already wide and growing.

---

## 3. MACD (Momentum / Trend Confirmation)

| Date | MACD | MACD Hist |
|---|---|---|
| 2026-05-11 | 24.12 | **+3.95** (peak) |
| 2026-05-15 | 24.50 | +1.63 |
| 2026-05-22 | 20.46 | **−1.36** (trough) |
| 2026-05-29 | **21.49** | **+0.02** (just flipped positive) |

**Interpretation:**
- MACD line itself remains very elevated (>20) — confirming the strong uptrend.
- The histogram peaked on 2026-05-11 at +3.95, then **decelerated and went negative 2026-05-20 through 2026-05-28** even as price kept rising slightly. This is a **subtle bearish momentum divergence** at the local level — price made higher highs (peak $738.31 on 5/29) while MACD line printed a lower high vs. its 5/14 reading of 25.27.
- Histogram just flipped marginally positive again on 5/29 (+0.02), suggesting momentum is *trying* to re-accelerate, but the signal is fragile.

**Actionable:** A confirmed histogram cross *back below zero* on heavy volume would be the first meaningful "trend-cooling" trigger. For now, momentum is positive but no longer accelerating.

---

## 4. RSI (Overbought / Oversold)

| Date | RSI(14) |
|---|---|
| 2026-05-11 | **83.23** (extreme OB) |
| 2026-05-14 | 80.65 |
| 2026-05-19 | 65.61 (cooled) |
| 2026-05-22 | 71.38 |
| 2026-05-29 | **77.20** |

**Interpretation:**
- RSI has spent **most of May above 70**, the textbook overbought line. It briefly cooled to the mid-60s on 5/19 (a healthy reset) before re-accelerating.
- A **lower-high pattern in RSI** (83.23 on 5/11 vs 77.20 on 5/29) while price made a *higher* high is a **classic bearish RSI divergence at the very short-term horizon**. This does not by itself flip the trend, but it warns against chasing.
- In strong trends, RSI can remain >70 for weeks; the signal is "be cautious about new longs," not "sell aggressively."

---

## 5. Bollinger Upper Band (Volatility Envelope)

| Date | Close | Boll Upper | Distance |
|---|---|---|---|
| 2026-05-08 | 711.23 | 707.55 | **Above band** |
| 2026-05-11 | 713.29 | 713.26 | **Riding band** |
| 2026-05-14 | 719.79 | 728.28 | inside |
| 2026-05-22 | 717.54 | 737.56 | inside |
| 2026-05-29 | 738.31 | **745.86** | inside (~1.0% below UB) |

**Interpretation:**
- QQQ pierced and rode the upper band 5/8–5/11 — a classic strong-trend signature, *not* automatically a sell signal.
- Since then, the band itself has expanded (from ~707 to ~746), absorbing further price gains. Price is now approaching the band again but hasn't pierced it.
- The expanding upper band quantifies that **realized volatility is rising** — consistent with the parabolic feel of the rally.

---

## 6. ATR (Volatility / Risk Sizing)

| Date | ATR(14) |
|---|---|
| 2026-05-01 | 9.84 |
| 2026-05-15 | 10.73 |
| 2026-05-29 | **10.35** |

**Interpretation:**
- ATR has risen ~5% over the month. A typical daily true range is now ~$10.35 (≈1.4% of price).
- For a swing-trade long, a **2× ATR stop ≈ $20.70**, placing a logical stop near **$717.60** (just below the recent breakout pivot of ~$717–718 on 5/22). This also coincides roughly with the rising 10 EMA at $722.
- For tighter trades, 1× ATR stop = ~$728.

---

## 7. Synthesis & Actionable Insights

### Bull case (still intact)
- All MAs aligned & rising; price > 10 EMA > 50 > 200.
- MACD line elevated and just re-curling up.
- New all-time highs printed 2026-05-29 with reasonable (not exhausted) volume.
- Bollinger band expanding, not contracting → trend has fuel.

### Bear / caution case (developing)
- **RSI 77.2 with a lower high vs. May 11 reading of 83.2** = short-term bearish divergence.
- **MACD histogram divergence** (lower highs while price made higher highs).
- Price extended **~13% above 50 SMA / ~20% above 200 SMA** — historically rich.
- No volume surge to confirm the late-May leg ($730–$738) — rally is narrowing.

### Trade Posture
- **Existing longs:** Hold; trail stops to ~$717–$722 zone (10-EMA / 2× ATR).
- **New longs:** Avoid chasing at ~$738. A pullback to the 10 EMA (~$722) or 20-day Bollinger middle would offer better R:R.
- **Shorts/hedges:** Premature without a *trigger* — wait for (a) a daily close < $722 (10 EMA), (b) MACD histogram closing below zero for 2+ days, and (c) RSI breaking back below 70.
- **Volatility note:** ATR expansion suggests sizing positions ~5–10% smaller than May-1 sizing for the same dollar risk.

---

## 8. Key Levels

| Level Type | Price | Source |
|---|---|---|
| Resistance / current high | **$741.63** | Intraday high 2026-05-29 |
| Bollinger Upper Band | $745.86 | 2026-05-29 |
| Short-term support (10 EMA) | $722.46 | 2026-05-29 |
| Breakout pivot | $717.54 | 2026-05-22 close (recent base) |
| Medium-term support (50 SMA) | $652.90 | 2026-05-29 |
| Long-term support (200 SMA) | $616.82 | 2026-05-29 |
| Cycle low | $558.28 | 2026-03-30 close |

---

## 9. Summary Table

| Indicator | Reading (2026-05-29) | Signal | Conviction |
|---|---|---|---|
| close_10_ema | $722.46 (rising) | Bullish — price above & extended | High |
| close_50_sma | $652.90 (rising) | Bullish trend | High |
| close_200_sma | $616.82 (rising) | Long-term bullish | High |
| MACD | 21.49 (still high) | Bullish, decelerating | Medium |
| MACD Histogram | +0.02 (just flipped +) | Neutral / fragile | Low |
| RSI(14) | 77.20 | Overbought, bearish divergence vs. 5/11 peak of 83.2 | Medium-bearish caution |
| Bollinger Upper | $745.86 (expanding) | Trend-strong; not yet pierced | Medium-bullish |
| ATR(14) | 10.35 (≈1.4% of price) | Volatility rising; size down | Risk-mgmt |

**Net read:** Strong primary uptrend, but stretched and showing early *internal* deceleration. Best action is to **manage existing longs with trailing stops near the 10 EMA**, refrain from initiating new full-size longs at $738, and require concrete trigger events before flipping bearish.