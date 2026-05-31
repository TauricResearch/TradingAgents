I have all the data I need. Note: The verified market snapshot tool isn't available in this environment — I'll rely on the OHLCV and indicator outputs as the source of truth and flag any computed values rather than invented levels.

# CRM (Salesforce, Inc.) — Technical Analysis Report
**As of 2026-05-29 (last trading day before 2026-05-31)**

## 1. Selected Indicators (and rationale)

CRM has been in a sustained, sharp downtrend for ~5 months that recently showed signs of stabilization and a reflex bounce. The right indicator mix should give us:
- **Trend (multi-timeframe):** `close_50_sma`, `close_200_sma` → confirm the prevailing bearish structure and quantify the gap from long-term mean.
- **Short-term momentum / reversal probe:** `close_10_ema` → capture the very recent inflection (the May 29 surge).
- **Trend-momentum:** `macd`, `macdh` → MACD line for direction, histogram for early divergence/momentum thrust signal.
- **Overbought/oversold + divergence:** `rsi`.
- **Volatility/Mean-reversion envelope:** `boll_ub`, `boll_lb` → identify whether the bounce is a tag of band/breakout vs. reversion to mean. (Lower band repeatedly tagged during decline.)
- **Risk sizing / stops:** `atr` → quantify true volatility for stop placement.

Avoided redundancy: did not pick both `boll` (middle band) and a third SMA (boll middle = 20 SMA already implicit), no `vwma` (volume already informs the snapshot via the 5/29 surge), no `macds` (signal line is implicit in `macdh`).

---

## 2. Price Action Narrative (Nov 2025 → May 29, 2026)

| Phase | Range | Behavior |
|---|---|---|
| Late 2025 rally | Nov-low ~$224 → Dec-high ~$267 | Strong post-November bounce, peaked Dec 26 at $267.24. |
| Jan distribution | $265 → $213 | Gap down Jan 2 ($264→$253), step-down through mid-Jan, capitulation Jan 29 (-6.1%). |
| Feb collapse | $213 → $177 | Post-earnings/macro stress: Feb 3 (-6.8%), Feb 5 (-4.8%), Feb 11 (-3.4%); $200 level lost decisively. |
| March chop | $185–$203 | Bear-flag rally to ~$203 (Mar 5–12), failed; rolled back to $179. |
| April bleed | $190 → $165 | Another leg down to a YTD low of **$164.96 on Apr 10**; gap-down on Apr 23 (-8.7% from $189.80 to $173.30). |
| May stabilization → squeeze | $165 → $191 | Retest of lows ($165.84 on May 13), then a sharp 3-day reversal culminating in **May 29: +8.3% to $191.10 on 33.96M volume** — the heaviest volume since February. |

**Key observation:** May 29 was a high-volume thrust day. Volume ≈ 2.4× the 20-day average, and the candle (open 180.24, high 194.14, low 180.02, close 191.10) printed a wide-range bullish bar. This is the first conviction-buying signature in months.

---

## 3. Indicator-by-Indicator Read (values from tools)

### Trend Structure
- **Close (5/29):** $191.10
- **10 EMA (5/29):** 179.99 → price is **+6.2% above** the 10 EMA. Short-term trend has flipped up.
- **50 SMA (5/29):** 180.68 → price now **+5.8% above** the 50 SMA, after spending most of April–May *below* it. First meaningful reclaim.
- **200 SMA (5/29):** 220.57 → price still **−13.4% below** the 200 SMA. Long-term trend remains decisively bearish.
- **50 SMA vs 200 SMA:** 180.68 vs 220.57 — the 50 is well below the 200 and still falling (was 196.40 on Apr 1 → 180.68 now). Death-cross alignment intact; no golden-cross signal anywhere on the horizon.

**Interpretation:** A short-term breakout has occurred, but it is still a counter-trend move within a larger bear structure. Reclaiming the 200 SMA at ~$220 would be the first technical confirmation of a regime change.

### Momentum
- **MACD line (5/29):** −0.0012 (essentially zero), up from −1.17 on 5/28 and −3.14 trough on 5/14. The MACD is on the verge of crossing into positive territory.
- **MACD Histogram (5/29):** +1.22, expanding from +0.36 on 5/28 — a strong bullish momentum thrust. Histogram has been positive since 5/20, confirming a bullish MACD signal-line crossover earlier in the week.
- **RSI (5/29):** 60.54, jumping from 46.86 on 5/28. Sat in the 36–50 band most of May; now breaking above 60 for the first time since early May. Not yet overbought (>70), so room to run, but the 1-day jump is large.

**Interpretation:** Momentum has clearly turned. MACD bullish cross + RSI thrust + histogram acceleration = textbook short-term buy signal. But: the May 14 RSI low of 36.73 was *not* a classic oversold (<30) print, so divergence-based reversal calls are weaker than they would be at deeper extremes.

### Volatility / Bands
- **Bollinger Upper Band (5/29):** 191.66 — close of 191.10 is **right at the upper band** (a tag, not a breakout).
- **Bollinger Lower Band (5/29):** 166.40 — earlier in May (5/13–5/15), the close traded near the lower band (price 165.84–173.51 vs. band 166.26–169.08).
- **Band width:** ~$25.3, fairly wide → high realized volatility regime.
- **ATR (5/29):** 8.26, up from 7.28 on 5/26 — volatility *expanding* with the upside move (a typical thrust signature, but also raises whipsaw risk).

**Interpretation:** Price is testing the upper band on the day of the surge. Two scenarios from here are typical: (a) a 1–3 day pullback to the 20 SMA / mid-band area (~$179) before a continuation, or (b) "walking the band" if a true regime change is underway. The fact that ATR expanded with price (not just on declines) is constructive but increases position-sizing risk.

---

## 4. Confluence Map

| Theme | Signal | Strength |
|---|---|---|
| Long-term trend (200 SMA) | Bearish — price 13% below, SMA still falling | Strong bearish |
| Medium trend (50 SMA) | Just reclaimed today's price | Neutral-to-bullish (early) |
| Short-term trend (10 EMA) | Bullishly extended above | Bullish |
| MACD line cross | Just kissing zero from below | Bullish (early) |
| MACD histogram | Expanding positive (+1.22) | Bullish thrust |
| RSI | 60.5, rising from mid-40s | Bullish, not yet stretched |
| Bollinger Upper | At-the-band tag | Neutral / caution (resistance) |
| Bollinger Lower | Held in mid-May ($165.84 vs LB 166.26) | Bullish (held support) |
| ATR | Expanding to 8.26 | Caution — wide stops needed |
| Volume (5/29) | 33.96M, ~2.4× avg | Strong confirmation |

---

## 5. Actionable Insights

**Bias:** Cautiously constructive on the short-term swing; structurally still in a bear trend.

**Levels to watch (derived from tool data):**
- **Immediate resistance:** $191.66 (Bollinger upper band, 5/29) and the May 7 high $188.58 / Apr 22 high $191.15 — already being tested.
- **Next resistance:** $200 (round number + Mar 5–6 highs $203.91/$202.45 area).
- **Key confirmation level:** $220.57 (200 SMA) — must reclaim to confirm regime change.
- **Immediate support:** $179–$181 (50 SMA $180.68, 10 EMA $179.99, recent breakout pivot).
- **Major support:** $164.96 (Apr 10 YTD low) and $165.84 (May 13 retest low).

**Risk parameters:**
- ATR-based stop for a long entry near $191: 1.5× ATR ≈ $12.4 → stop near **$178** (just below 50 SMA & 10 EMA).
- Position size should be roughly halved versus normal given ATR is ~30% above the early-May reading.

**Setups:**
1. **Pullback-buy:** Wait for a retest of the $179–$182 zone (50 SMA / 10 EMA / breakout pivot) with a higher-low candle. Target $200, then $220. Stop $176.
2. **Breakout-buy:** Daily close > $194 (5/29 high) on continued above-average volume confirms the squeeze — chase to $200/$220, but expect noise given upper-band tag.
3. **Avoid chasing 5/29 close at $191** without confirmation — it's tagging the upper Bollinger band on a ~$15 single-day range, which historically (Feb–May) has often produced 1–2 day mean-reversion before continuation.

---

## 6. Summary Table

| Metric | Value (5/29/2026) | Read |
|---|---|---|
| Close | $191.10 | +8.3% day; high-volume thrust |
| Volume | 33.96M | ~2.4× recent avg — confirmation |
| 10 EMA | 179.99 | Price above; short-term bullish |
| 50 SMA | 180.68 | Price just reclaimed; falling SMA |
| 200 SMA | 220.57 | Price 13.4% below; long-term bearish |
| MACD | −0.001 | Crossing zero; bullish inflection |
| MACD Hist | +1.22 | Expanding positive thrust |
| RSI | 60.54 | Bullish, not overbought |
| Bollinger UB | 191.66 | Price tagging — resistance test |
| Bollinger LB | 166.40 | Held in mid-May |
| ATR | 8.26 | Volatility expanding |
| Net bias | — | **Short-term bullish, medium-term cautious, long-term bearish until $220 reclaimed** |

I'll let the next assistant in the chain incorporate fundamentals/news/risk inputs before finalizing the BUY/HOLD/SELL recommendation. From a pure-technicals standpoint, this profile reads as a **tactical long opportunity on a pullback to $179–$182 with a stop at $176, target $200 then $220** — not a structural buy until the 200 SMA is reclaimed.