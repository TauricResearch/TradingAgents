# AMAT (Applied Materials, Inc.) — Technical Analysis Report
**Date:** 2026-05-31 | **Sector:** Semiconductor Equipment & Materials | **Exchange:** NMS

> Note: The verification snapshot tool requested in my instructions is not available in this environment (returned an error). I have therefore relied directly on `get_stock_data` and `get_indicators` outputs as the source of truth. All exact values cited below trace to those tool returns.

## 1. Price Action Overview (Nov 2025 → May 29, 2026)

AMAT has had an extraordinary run over the seven-month window:

- **Nov 3, 2025 close:** $236.66
- **Feb 13, 2026 (gap-up day after presumed earnings/event):** opened $364.04, closed $354.03 (a ~16% one-day surge from prior $327.57 close)
- **Mar 26, 2026 sharp pullback:** closed $338.13 (down ~$30 in a day from $368.88), bottoming around **Mar 30 at $322.72**
- **Apr 8, 2026 breakout day:** opened $378.42 from prior $353.87 close, closed $385.24 (another large gap-up)
- **May 14, 2026 intraday high:** $447.89; closed $440.01 — local cycle peak
- **May 18 deep one-day drop:** closed $413.06 (-5.2% from $436.08 on 5/15)
- **May 29, 2026 (latest close):** **$450.06**, near all-time highs

The structure is a clear **major uptrend with three distinct legs** (Nov–Dec 2025 base, Jan–Feb 2026 ramp, April–May 2026 acceleration), each separated by sharp but short-lived corrections of 8–15%.

## 2. Indicator Selection Rationale (8 Indicators)

I selected a balanced, non-redundant suite covering trend (multiple horizons), momentum, volatility, and volume:

| Category | Indicator | Why Selected |
|---|---|---|
| Trend (long) | **close_200_sma** | Confirms secular uptrend; provides the strategic backstop. |
| Trend (medium) | **close_50_sma** | Acts as the primary dynamic support during pullbacks. |
| Trend (short) | **close_10_ema** | Captures the explosive short-term momentum and tactical pivots. |
| Momentum (trend) | **macd** | Identifies trend strength and bullish/bearish crossovers. |
| Momentum (signal) | **macds** | Crossover confirmation against MACD — together they avoid whipsaws. |
| Momentum (oscillator) | **rsi** | Independent overbought/oversold gauge, complements MACD. |
| Volatility | **boll_ub** + **boll_lb** | Defines breakout/exhaustion zones; range expansion telltales. |
| Volatility (risk) | **atr** | Position-sizing and stop placement in a high-volatility name. |
| Volume | **vwma** | Confirms whether the rally has genuine volume backing vs. price-only drift. |

(I deliberately avoided combining RSI with stochRSI and avoided multiple redundant volume oscillators.)

## 3. Trend Structure

| Indicator | 2026-05-29 Value | Reading |
|---|---|---|
| Close | $450.06 | All-time-high zone |
| 10 EMA | $438.85 | Price > 10 EMA → bullish short-term |
| 50 SMA | $396.82 | Price ~13.4% above 50 SMA → strong medium-term uptrend |
| 200 SMA | $291.86 | Price ~54% above 200 SMA → powerful long-term uptrend |
| VWMA (20) | $434.84 | Price > VWMA → rally is volume-supported |

**Stacking:** Price > 10 EMA > VWMA > 50 SMA > 200 SMA — a textbook bullish alignment. The gap between 50 SMA ($396.82) and 200 SMA ($291.86) is wide and still expanding (50 SMA rose from $368.99 on May 1 to $396.82 on May 29 — a ~7.5% advance in 4 weeks), confirming trend acceleration rather than maturation.

## 4. Momentum

**MACD (12/26/9):**
- May 29: MACD = **14.22**, Signal = **13.25**, Histogram positive (~+0.97)
- Bullish cross occurred on/near **May 22** when MACD (11.19) crossed back above Signal (12.50)... actually MACD at 11.19 was below Signal at 12.50 on May 22, then both rose together; the firm re-acceleration (MACD 12.87 → 13.52 → 13.99 → 14.22 from May 26–29) shows momentum is **re-expanding** after a mid-May cool-off.
- Earlier histogram peak around **May 14–15** (MACD ~16.25 vs Signal ~14.12) had compressed sharply during the May 18 sell-off, then has now stabilized and rolled back up.

**RSI (14):**
- May 29: **61.97** — bullish but **not overbought** (well below 70).
- Prior local extremes in the window: dipped to **49.78 on May 19** (healthy reset), peaked at **66.49 on May 11**.
- Importantly, despite price making fresh highs ($454.89 on May 26 vs $447.89 on May 14), RSI on 5/26 (64.36) is **lower than RSI on 5/11 (66.49)** — a mild **bearish RSI divergence** worth flagging. Not yet a sell signal, but a caution flag against chasing.

## 5. Volatility & Bollinger Envelope

| Date | Close | Boll Upper | Boll Lower | ATR(14) |
|---|---|---|---|---|
| 2026-05-01 | 388.60 | 421.31 | 360.21 | 14.73 |
| 2026-05-14 | 440.01 | 449.20 | 368.62 | 17.18 |
| 2026-05-18 | 413.06 | 452.52 | 371.45 | 18.73 |
| 2026-05-29 | 450.06 | 466.01 | 389.69 | 18.16 |

Observations:
- ATR has expanded from **$14.73 → $18.16** in May (+23%) — volatility regime has **stepped up** materially.
- The May 14 close ($440.01) tagged the upper band ($449.20) within 2%, and the subsequent May 18 plunge to $413.06 was a classic **upper-band rejection** event. Price has since recovered without re-tagging the upper band ($466.01 on 5/29 vs close $450.06 — ~3.5% headroom).
- Lower band has lifted aggressively from $360.21 (5/1) to $389.69 (5/29) — a sign of a "**riding the bands**" trend rather than mean-reverting chop.

## 6. Volume Confirmation (VWMA)

Price/VWMA spread on 2026-05-29: $450.06 vs $434.84 → **+3.5%**. VWMA itself rose from $393.93 (5/4) to $434.84 (5/29), a **+10.4% advance in ~4 weeks** with rising volume on big-up days (e.g., 14.9M shares on 5/14, 12.8M on 5/15, 8.3M on 5/18). The trend has genuine institutional participation behind it; this is not a low-volume drift higher.

## 7. Risk & Key Levels

- **Immediate support cluster:** 10-EMA $438.85 → VWMA $434.84 → Bollinger mid (boll = ~$427.9 implied from band midpoint).
- **Stronger support:** 50 SMA $396.82 (also near the May 18 low of $413). A break below ~$395 would invalidate the medium-term trend.
- **Overhead:** Bollinger upper $466.01 is the proximate resistance; round-number $460–$465 (May 27 high $462.40) is the immediate ceiling.
- **ATR-based stops:** With ATR ≈ $18.16, a 1.5x ATR stop from $450 sits near **$422.7** — comfortably above the 50 SMA but tight enough to respect recent volatility.

## 8. Synthesis & Actionable Stance

**Bullish factors (dominant):**
- All MA stack aligned bullish with widening separation
- MACD re-expanding after a healthy cool-down
- VWMA confirms volume-backed advance
- Price holding above all key averages and reclaimed momentum after the 5/18 shakeout

**Caution factors:**
- ATR up 23% in May — risk regime has expanded; position sizing must be smaller
- RSI **bearish divergence** between 5/11 and 5/26 (lower RSI on higher price)
- Price is ~54% above 200 SMA — extension risk; reversion-to-mean episodes (like 5/18 and 3/26) have been violent
- Recent earnings/event-driven gaps (Feb 13, Apr 8) show the stock can move 5–16% on single sessions

**Tactical read:** Trend-following bias remains **constructive/bullish**, but the optimal action is *not* to chase a fresh long at $450 with the upper Bollinger only 3.5% away and an active RSI divergence. The favored setup is to add on pullbacks toward the 10 EMA / VWMA confluence ($434–$439) with stops below the 50 SMA. Existing longs should trail stops up using ATR.

---

## Key Points Summary Table

| Theme | Reading | Value(s) on 2026-05-29 | Implication |
|---|---|---|---|
| Long-term trend | Strongly bullish | Close $450.06 vs 200 SMA $291.86 (+54%) | Secular uptrend intact |
| Medium-term trend | Bullish, accelerating | 50 SMA $396.82, rising ~7.5%/4wk | Healthy trend support |
| Short-term trend | Bullish | Close > 10 EMA $438.85 | Momentum on side of bulls |
| MACD | Positive & re-expanding | MACD 14.22 > Signal 13.25 | Bullish momentum reasserting |
| RSI | Bullish but with divergence | 61.97 (was 66.49 on 5/11 at lower price high) | Caution on chasing |
| Bollinger Bands | Riding upper half | UB $466.01, LB $389.69 | Trend mode; UB rejection on 5/14 |
| ATR (volatility) | Elevated, rising | $18.16 (+23% MoM) | Smaller size, wider stops |
| VWMA (volume) | Confirming | Close $450 vs VWMA $434.84 | Real institutional buying |
| Immediate support | 10 EMA / VWMA confluence | $434–$439 | Buy-the-dip zone |
| Immediate resistance | Bollinger UB / recent high | $462–$466 | Take-profit / fade zone |
| Critical invalidation | Break of 50 SMA | <$395 | Trend regime change |
| Tactical bias | Buy pullbacks, do not chase | — | Add at $434–$439, stop <$395 |