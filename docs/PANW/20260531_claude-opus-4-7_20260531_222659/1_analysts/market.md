I now have all the data I need. Let me compose the detailed report.

# PANW (Palo Alto Networks, Inc.) — Technical Analysis Report
**Analysis Date:** 2026-05-31 (last trading day: Fri 2026-05-29)
**Last Close:** $281.69 (+9.30% on the day, on 14.99M shares — ~2.5x average volume)
**Sector:** Technology / Software – Infrastructure (NMS)

> Note: The dedicated "verified market snapshot" tool was not available in this environment. All numbers below are sourced directly from `get_stock_data` and `get_indicators` outputs and are quoted with their dates so they can be independently cross-checked.

---

## 1. Indicator Selection Rationale

The chart shows a deeply nonlinear regime over the last 7 months: a topping pattern in November, a sharp downtrend through early February, capitulation in mid-February (the 2026-02-18 gap-down from ~$163.50 to $152.35 on ~26.8M shares), a basing phase through March/early April, and a parabolic recovery in May ending in a breakout. To capture every regime in this trajectory I picked 8 complementary indicators across 5 categories:

| Category | Indicator | Why it matters here |
|---|---|---|
| Trend (medium) | **close_50_sma** | Defines the medium-term trend. Just regained by price in early May after months below — a regime change marker. |
| Trend (long) | **close_200_sma** | Confirms whether PANW is in a structural bull or bear regime; price just decisively reclaimed it in May. |
| Trend (fast) | **close_10_ema** | Captures the explosive May rally and is the natural trailing-stop reference for a momentum trade. |
| Momentum (line) | **macd** | Quantifies the strength of the new uptrend; surged from ~+2 in late April to +22.6 on 5/29. |
| Momentum (signal) | **macds** | Confirms the MACD crossover and helps detect early exhaustion. |
| Momentum (oscillator) | **rsi** | Critical right now — readings have been ≥70 for a month, currently 80.5; flags overbought risk and divergence. |
| Volatility | **atr** | Volatility expansion has been dramatic (ATR from ~$7 in late April to ~$11.7); essential for stop sizing. |
| Volatility/Breakout | **boll_ub** | Defines the breakout extension zone. Price closed at $281.69 vs upper band $289.36 — riding the band but not yet pierced. |

I deliberately avoided `boll_lb` and `boll` (redundant with `boll_ub` for a breakout setup), `macdh` (redundant with the macd/macds pair), and `vwma` (the volume signal is already strong on the 5/29 gap-up; a VWMA wouldn't add unique info given how clean the trend is).

---

## 2. Price Action & Regime Map

**Phase 1 — Distribution top (Nov 2025):** PANW peaked around $219–220 on 11/3, then broke down with the 11/20 plunge ($199.90 → $185.07 on 16.1M shares — 3x normal volume). Classic earnings/guidance gap-down behavior.

**Phase 2 — Stair-step decline (Dec 2025 – early Feb 2026):** Price drifted from $190s to mid $180s. Then 2026-01-29 produced a major break: $183.74 → $176.20 on 12.9M shares.

**Phase 3 — Capitulation (Feb 2026):** Sequential gap-downs:
- 2026-02-03: $175.42 → $166.24
- 2026-02-05: $166.72 → $154.77
- 2026-02-18: $163.50 → $152.35 (massive 26.8M-share day)
- Cycle low: **2026-02-24 at $141.67** intraday low / $141.67 close.

**Phase 4 — Base / re-test (Mar–early Apr):** Recovery to ~$170, then a second leg lower bottoming at **$147.02 on 2026-03-27**, forming a higher low vs February — a classic double-bottom structure.

**Phase 5 — Recovery (mid-Apr to early May):** Steady climb from $147 to ~$184, reclaiming the 50-SMA on/around 2026-05-04 ($184.56 close vs 50-SMA $164.53).

**Phase 6 — Breakout & blow-off (May 7–29):** Explosive move:
- 5/7: gap up $183.68 → $196.53
- 5/8: $196.53 → $207.88
- 5/13: $215.60 → $227.79
- 5/15: $242.83 (clears 200-SMA decisively)
- 5/22: $260.58
- 5/29: **$281.69 (+9.30% gap up on 15M shares, the largest one-day gain of the year)**

Net move from the 3/27 low ($147.02) to 5/29 ($281.69) = **+91.6% in ~9 weeks**.

---

## 3. Indicator-by-Indicator Reading

### 3.1 Moving Averages — Bullish stack newly intact

| Date | Close | 10 EMA | 50 SMA | 200 SMA |
|---|---|---|---|---|
| 2026-04-21 | 174.96 | 167.08 | 160.91 | 185.67 |
| 2026-05-04 | 184.56 | 178.87 | 164.53 | 184.97 |
| 2026-05-15 | 242.83 | 215.07 | 175.60 | 185.64 |
| 2026-05-29 | **281.69** | **252.01** | **191.42** | **189.41** |

- **Stack:** Price ($281.69) > 10 EMA ($252.01) > 50 SMA ($191.42) > 200 SMA ($189.41). All four aligned bullishly — the textbook "perfect stack."
- **Price vs 10 EMA gap:** $281.69 − $252.01 = **$29.68 (11.8% extension)**. Historically extreme; mean-reversion risk.
- **50 SMA / 200 SMA "near-cross":** On 5/29 the 50 SMA ($191.42) is now *above* the 200 SMA ($189.41) by ~$2 — a fresh **golden cross** has just occurred. Strategically bullish over a multi-month horizon.

### 3.2 MACD — Powerful, still expanding

| Date | MACD | Signal | Histogram |
|---|---|---|---|
| 2026-04-21 | 2.02 | 0.83 | +1.20 |
| 2026-05-04 | 5.25 | 4.20 | +1.05 |
| 2026-05-15 | 16.74 | 11.05 | +5.69 |
| 2026-05-29 | **22.57** | **19.80** | **+2.78** |

- MACD is at extreme positive levels (22.57) and remains above the signal line — uptrend intact.
- **Watch the histogram:** It peaked around 5/15 at +5.69 and has narrowed to +2.78 by 5/29. This is an early hint that *acceleration* is fading even as price keeps making new highs — a subtle momentum divergence forming. Not a sell signal yet, but it removes the "easy" part of the trend.

### 3.3 RSI — Persistently overbought, ripe for cooling

| Date | RSI |
|---|---|
| 2026-05-04 | 62.92 |
| 2026-05-11 | 78.31 |
| 2026-05-15 | 86.10 |
| 2026-05-18 | 87.00 (peak) |
| 2026-05-22 | 83.61 |
| 2026-05-26 | 79.47 |
| 2026-05-27 | 71.26 |
| 2026-05-29 | **80.47** |

- RSI has been above 70 essentially without break since 5/11 — almost three weeks. In strong trends this is normal, but the magnitude (peak 87) is in the top tier of historical overbought readings.
- Because price made a fresh high ($281.69 on 5/29) while RSI's recent peak (87.00 on 5/18) was higher than its 5/29 reading (80.47), there is **a mild bearish RSI/price divergence**. This is a classical caution signal — not a definitive top, but argues against fresh chasing.

### 3.4 ATR — Volatility expansion

| Date | ATR (14) |
|---|---|
| 2026-04-21 | 7.11 |
| 2026-05-04 | 6.92 |
| 2026-05-15 | 9.36 |
| 2026-05-29 | **11.69** |

- ATR jumped ~69% in five weeks. A $1 move now is "small"; expect typical daily ranges of $10–12. Position sizing must shrink accordingly.
- Practical stop framework: a 2×ATR stop from the close = $281.69 − $23.38 = **~$258**, which neatly aligns with the 5/27 swing low of $245–$251. Tighter aggressive stop: 1×ATR ≈ $270.

### 3.5 Bollinger Upper Band — Riding, not piercing

| Date | Close | Upper Band | Distance |
|---|---|---|---|
| 2026-05-15 | 242.83 | 238.51 | **+$4.32 (above)** |
| 2026-05-18 | 247.55 | 246.87 | **+$0.68 (above)** |
| 2026-05-22 | 260.58 | 271.44 | -$10.86 (below) |
| 2026-05-29 | **281.69** | **289.36** | -$7.67 (below) |

- Price tagged or pierced the upper band on 5/14–5/18, then the band itself widened so quickly that price is now back inside it despite still rallying. This is the hallmark of a "trend ride" — band-walking rather than mean-reverting.
- The band expansion (now ~$98 wide between upper and middle) confirms genuine, supply-driven volatility, not a liquidity squeeze.

---

## 4. Key Levels (Sourced from Historical Bars)

| Type | Level | Origin |
|---|---|---|
| Resistance (band ceiling) | **~$289** | Bollinger upper band on 2026-05-29 |
| Resistance (psychological) | $300 | Round number |
| Pivot / breakout retest | **$247–$252** | 5/18 high $248.85 and 5/27 low $243.04 zone |
| Support (10 EMA) | **~$252** | 10 EMA on 2026-05-29 |
| Support (5/13 breakout level) | **~$227–$228** | 5/13 close $227.79 — the "breakaway gap" base |
| Support (50 SMA) | **~$191** | 50 SMA on 2026-05-29 |
| Major support (200 SMA + golden cross zone) | **~$189** | 200 SMA on 2026-05-29 |

---

## 5. Trade Construction & Actionable Insights

**Trend bias:** Strongly bullish — golden cross just confirmed, perfect MA stack, MACD elevated and positive.
**Tactical bias:** Short-term stretched — RSI 80, price 11.8% above 10 EMA, mild RSI/MACD-histogram divergence, ATR-implied range very wide.

**For traders already long:**
- **Trail the 10 EMA (~$252)** as a momentum stop. Loss of 10 EMA on a closing basis would be the first warning.
- A 2×ATR stop (~$258) gives more breathing room and matches the most recent swing low.
- Consider scaling out 1/3 into $290–$300 (band ceiling + round number) to monetize parabolic extension.

**For new buyers:**
- **Do not chase the 5/29 gap.** The combination of an 80+ RSI, a 9.3% one-day gap on multiples of average volume, and price 12% above the 10 EMA argues for a pullback or sideways digestion.
- Preferred entry zones on a pullback:
  - First test: **$247–$252** (10 EMA + prior breakout pivot). High-quality risk/reward.
  - Deeper retest: **$227–$230** (the 5/13 breakaway gap). Would be a more controversial buy because it would trigger near-term momentum stops.
- Invalidation of the bull thesis: a sustained close back below **$215** (5/12 close) and especially below the 50 SMA (~$191) would mark a failed breakout.

**For shorts:**
- Do not pre-emptively short a strong, trending name with an active golden cross. Wait for an *actual* MACD bearish cross, a daily close below the 10 EMA, or a clear lower high. Tactical-only short candidate (1–3 day) with a stop above $290 — but this is fighting the trend.

---

## 6. Risk Notes

1. **Earnings/news asymmetry:** The 5/29 9.3% gap on heavy volume is the kind of move typically associated with earnings or major news. Without confirmation of catalyst, treat valuation and follow-through as uncertain on day +1.
2. **Volatility regime shift:** ATR has nearly doubled in five weeks. Many systematic strategies will reduce position size into this; expect noisier intraday action.
3. **Reflexive risk:** The November 2025 top occurred at ~$220 and led to a 36% drawdown. The current move has already exceeded that level by ~28%. Sustaining such a vertical advance requires fresh fundamental surprises; otherwise the path of least resistance for energetic momentum stocks after such extensions is sideways consolidation for several weeks.

---

## 7. Summary Table

| Theme | Reading | Signal |
|---|---|---|
| Long-term trend (200 SMA) | Price $281.69 vs SMA $189.41; **fresh golden cross** | **Bullish (strategic)** |
| Medium-term trend (50 SMA) | $281.69 vs $191.42, +47% above | **Bullish, but extended** |
| Short-term trend (10 EMA) | $281.69 vs $252.01, +11.8% above | **Bullish, very stretched** |
| MACD (line vs signal) | 22.57 vs 19.80, gap +2.78 | **Bullish, but histogram contracting** |
| RSI(14) | 80.47, 5/18 peak 87.00 | **Overbought; mild bearish divergence** |
| ATR(14) | 11.69 (vs 6.92 a month ago) | **Volatility expanding — reduce size** |
| Bollinger Upper Band | $289.36; price tagged then re-entered band | **Strong band-walk; near-term resistance** |
| Volume signature (5/29) | 14.99M, ~2.5× average | **Confirms breakout enthusiasm** |
| Key supports | $252 (10 EMA) → $227 (gap base) → $191 (50 SMA) | Buy-the-dip ladder |
| Key resistance | $289 (BB upper) → $300 (psych) | Sell-into-strength zone |
| Net stance | Trend long, but **don't chase**; buy pullbacks toward $250 area | **HOLD existing longs / WAIT for pullback to BUY** |

---

**Bottom line:** PANW is in a confirmed bullish trend regime (golden cross, perfect MA stack, elevated MACD), but is short-term overheated (RSI 80, 11.8% above 10 EMA, near upper Bollinger band) and exhibits early momentum-divergence hints (MACD histogram narrowing). The highest-probability action is to **hold longs with a trailing stop at the 10 EMA (~$252)** and wait for a pullback into $247–$252 (or, on a deeper flush, $227–$230) before adding new exposure. Chasing the 5/29 gap-up at $281.69 offers poor risk/reward.