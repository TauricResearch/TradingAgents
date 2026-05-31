I have all the data I need. Note: the `get_verified_market_snapshot` tool was unavailable (error), so I'll rely on the price data and indicator outputs as my source of truth and explicitly cite dates and values from those tool outputs.

# ASML Holding N.V. (ASML) — Technical Analysis Report
**As of close: Friday, 2026-05-29 (current date 2026-05-31, weekend)**

---

## 1. Indicator Selection Rationale

For ASML — a large-cap semiconductor equipment leader currently in a powerful but volatile uptrend — I selected eight complementary indicators spanning four analytical dimensions:

| Category | Indicator | Why it was chosen |
|---|---|---|
| Trend (long) | **close_200_sma** | Anchors the secular trend and confirms the post-Jan 2026 regime change. |
| Trend (medium) | **close_50_sma** | Defines the medium-term trend and dynamic support after the Mar–Apr correction. |
| Trend (short) | **close_10_ema** | Captures fast momentum shifts; critical for a stock making outsized daily moves. |
| Momentum (trend) | **macd** | Highlights momentum acceleration/deceleration via EMA differential. |
| Momentum (signal) | **macds** | Crossover trigger; confirms macd direction without redundancy. |
| Momentum (oscillator) | **rsi** | Independent overbought/oversold gauge & divergence detector — non-redundant with MACD. |
| Volatility (band) | **boll_ub** | Defines breakout/over-extension zones; especially useful given ASML is "riding the band." |
| Volatility (range) | **atr** | Quantifies absolute dollar volatility for stop-loss/position sizing — distinct from Bollinger. |

I deliberately omitted `boll` and `boll_lb` (redundant with `boll_ub` for current breakout context), `macdh` (redundant with macd vs. macds), and `vwma` (50-SMA + price-volume reading from raw data already covers volume confirmation).

---

## 2. Price Action Overview (Nov 2025 → May 29, 2026)

Using the raw OHLCV data:

- **Early-phase consolidation (Nov 2025):** ASML traded in a 960–1080 range, with a notable Nov 21 low of **$963.19**.
- **December rally and pullback:** Climbed to **$1,136.93** on Dec 3, then chopped back into the $1,050–$1,080 zone by month-end.
- **Explosive January breakout:** Gapped from **$1,066.12 (Dec 31)** to **$1,159.71 (Jan 2)** — a ~+8.8% single-day move — and proceeded to rally to **$1,449.51 (Jan 27)**, a ~36% gain in 4 weeks.
- **Feb–early Mar topping:** Made a higher high at **$1,523.18 (Feb 25)**, then sold off sharply to **$1,289.98 (Mar 6)** — roughly **−15.3%** in 7 sessions.
- **Late-Mar/early-Apr retest:** Bottomed near **$1,251.23 (Mar 30)** and **$1,301.17 (Apr 6)**, forming a higher low vs. the March bounce zone.
- **April–May resumption:** A second, even more aggressive leg up: from $1,303.60 (Apr 7) to **$1,632.90 (May 22)** — ~+25% in ~6 weeks. The most recent close is **$1,612.76 (May 29)**, just below the new all-time high near $1,654 intraday.

---

## 3. Trend Structure (Moving Averages)

| Date | Close | 10 EMA | 50 SMA | 200 SMA |
|---|---|---|---|---|
| 2026-05-29 | **1,612.76** | 1,582.10 | 1,454.09 | 1,191.77 |
| 2026-05-22 | 1,632.90 | 1,546.42 | 1,434.20 | 1,173.94 |
| 2026-05-15 | 1,501.81 | 1,523.88 | 1,415.20 | 1,152.64 |
| 2026-05-01 | 1,427.02 | 1,426.00 | 1,398.76 | 1,112.33 |

**Observations:**
- **Stacking is textbook bullish:** Price > 10 EMA > 50 SMA > 200 SMA — all four sloped upward.
- **Price is ~10.9% above the 50 SMA and ~35.3% above the 200 SMA** (using 5/29 close vs. listed values). That kind of separation from the 200 SMA historically signals an extended trend that, while bullish, is statistically prone to mean-reversion pullbacks.
- The 50 SMA (~1,454) is the most likely first defense on any pullback; the 10 EMA (~1,582) is the immediate near-term pivot. A close back below the 10 EMA would be the first short-term yellow flag.

---

## 4. Momentum (MACD + RSI)

**MACD (5/29):** macd = **44.64**, macds = **39.51** → MACD is **above signal** and the spread (~5.1) is **expanding** vs. 5/26 (43.59 vs. 34.91 spread = 8.7) — actually, comparing dates carefully:

| Date | MACD | Signal | Spread |
|---|---|---|---|
| 2026-05-29 | 44.64 | 39.51 | +5.13 |
| 2026-05-26 | 43.59 | 34.91 | +8.68 |
| 2026-05-22 | 39.08 | 32.74 | +6.34 |
| 2026-05-19 | 26.25 | 31.44 | **−5.19** (bearish cross prior week) |

The **bullish MACD re-cross occurred around 5/20–5/22**, which aligned with the price breakout from the 5/15–5/19 dip ($1,459 area). MACD is back near cycle highs, confirming momentum, but the signal line is catching up — **histogram (spread) has narrowed slightly into 5/29**, an early hint that momentum thrust is moderating, not reversing.

**RSI (5/29) = 59.5.** Notably:
- RSI peaked at only **64.2 on May 8** despite price making new all-time highs on May 22 ($1,632.90) and a near-equal close on May 26 ($1,632.03).
- This is a **mild bearish RSI divergence** — price made higher highs while RSI made a lower high. It doesn't guarantee a reversal in a strong trend, but it does flag that internal momentum is weaker than the headline price suggests.
- RSI is **not overbought** (well below 70), giving room for further upside, but the divergence warrants caution.

---

## 5. Volatility (Bollinger Upper + ATR)

**Bollinger Upper Band (5/29) = $1,685.51.** Close ($1,612.76) sits **~4.3% below the upper band**. ASML pierced or rode the upper band:
- May 8 close $1,592.02 vs. UB $1,566.14 → **above the band** (extended).
- May 13 close $1,581.58 vs. UB $1,596.42 → just below.
- May 22 close $1,632.90 vs. UB $1,656.45 → **just under** the band, the marquee high.

The band is **expanding** (1,540 on 5/4 → 1,685 on 5/29), reflecting volatility expansion. Price has not closed materially above the band since May 8, suggesting the band itself is now functioning as resistance unless a fresh breakout occurs.

**ATR (5/29) = $60.86.** Down slightly from the May 20 peak of **$65.83**, but still elevated. Practical implications:
- Average daily true range is roughly **3.8% of price** — large.
- A reasonable swing stop is ~1.5–2× ATR ≈ **$91–$122** below entry, putting a stop on any long initiated near $1,613 around **$1,490–$1,520** (which conveniently aligns with both the 10 EMA at $1,582 and the broken resistance/now-support shelf around $1,500).

---

## 6. Volume Confirmation (from OHLCV)

- The May 6 breakout day ($1,544.74 close, +7.0%) traded **2.31M shares** — meaningfully above the prior 30-day average (~1.5M).
- May 8 thrust to $1,592.02 traded **2.29M**.
- May 22 all-time high at $1,632.90 traded only **1.67M** — *lighter* than the breakout days.
- Recent sessions (5/27–5/29) trade 1.0–1.4M, **below average and on neutral price action**.

This is consistent with the RSI divergence: **the move into late-May highs lacked the volume conviction of the early-May breakout**, suggesting buyer exhaustion at the highs without (yet) distribution.

---

## 7. Synthesis & Actionable Insights

**The bullish case (dominant):**
- All trend filters aligned long; 50/200 SMA gap is wide and growing (deep golden-cross regime since Jan).
- MACD remains in a positive crossover; RSI at 59 has plenty of headroom.
- Pullbacks since April have been bought aggressively (Apr 7 low → +25% in 6 weeks).

**The cautionary case:**
- **Bearish RSI divergence** at the May 22/26 highs.
- **Volume contraction** on the latest highs.
- Price extended >35% above the 200 SMA — historically a zone where mean-reversion risk rises.
- ATR at ~$61 means a "normal" pullback can erase a week of gains in 1–2 sessions.

**Tactical playbook:**
- **Trend-followers / existing longs:** Maintain bias with stops trailed under the **10 EMA (~$1,582)** for tight management or under the **50 SMA (~$1,454)** for a wider swing stop. Don't chase here.
- **New long entries:** Better risk/reward on a pullback to $1,500–$1,540 (prior breakout shelf + 10 EMA convergence area), not at $1,613 just below the upper Bollinger band.
- **Tactical short / hedge:** Only consider on a daily close back below the 10 EMA ($1,582) AND a MACD bearish crossover; otherwise the trend tax is too high. First downside target $1,500, second $1,454 (50 SMA).
- **Breakout chasers:** Wait for a **daily close above $1,653** (recent intraday high) on volume >2M; that would invalidate the divergence concern and open $1,685 (UB) → $1,750+.

---

## 8. Summary Table

| Dimension | Indicator | Latest Value (5/29) | Reading | Bias |
|---|---|---|---|---|
| Long-term trend | 200 SMA | $1,191.77 | Price 35% above | Strongly Bullish |
| Medium-term trend | 50 SMA | $1,454.09 | Price 10.9% above; rising | Bullish |
| Short-term trend | 10 EMA | $1,582.10 | Price above; key pivot | Bullish |
| Momentum (trend) | MACD | 44.64 | Above signal; spread narrowing | Bullish, weakening |
| Momentum (signal) | MACD Signal | 39.51 | Catching up to MACD | Neutral-Bullish |
| Momentum (oscillator) | RSI | 59.5 | Lower high vs. price = **divergence** | Cautionary |
| Volatility (upper) | Bollinger UB | $1,685.51 | 4.3% above price; band expanding | Resistance |
| Volatility (range) | ATR | $60.86 | Elevated, slightly easing | High volatility regime |
| Volume context | Raw volume | ~1.0–1.7M recently | Light at new highs | Cautionary |

**Net stance:** The primary trend remains decisively up, but late-May internals (RSI divergence, lighter volume, narrowing MACD histogram, price riding but not exceeding the upper Bollinger band) argue **against fresh longs at $1,613** and **in favor of waiting for either (a) a healthy pullback to $1,500–$1,540 or (b) a confirmed breakout close above $1,653 on heavy volume.**

*Note: The `get_verified_market_snapshot` tool was unavailable in this environment (returned an error). All values cited above are sourced directly from `get_stock_data` and `get_indicators` outputs with explicit dates.*