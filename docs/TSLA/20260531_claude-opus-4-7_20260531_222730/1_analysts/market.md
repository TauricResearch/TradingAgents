# TSLA Technical Analysis Report — As of May 29, 2026 (last trading day before 2026-05-31 weekend)

## 1. Indicator Selection Rationale

I selected 8 complementary indicators across all five categories to capture trend, momentum, volatility, and volume context without redundancy:

| Indicator | Category | Why Chosen |
|---|---|---|
| close_10_ema | Trend (short) | Captures fast momentum shifts after the early-May rally |
| close_50_sma | Trend (medium) | Defines the medium-term trend slope and dynamic support |
| close_200_sma | Trend (long) | Confirms structural trend; key for golden/death cross context |
| MACD | Momentum | Identifies broader trend-momentum reversals via EMA differential |
| MACD Histogram | Momentum | Provides early warning on momentum decay/expansion before crossovers |
| RSI | Momentum oscillator | Flags overbought/oversold regimes & divergences (non-redundant with MACD which is trend-driven) |
| Bollinger Upper Band | Volatility | Pinpoints overbought breakout zones and "band riding" in strong rallies |
| ATR | Volatility (risk) | Quantifies absolute volatility for stop-loss/position sizing |

I deliberately omitted `boll`/`boll_lb` (redundant with `boll_ub` for current upside-leaning context), `vwma` (data not retrieved; price/trend coverage already strong via SMAs/EMA), and `macds` (the histogram already encodes that information).

---

## 2. Price Action Recap (Nov 2025 → May 2026)

TSLA has experienced three distinct regimes over the past 7 months:

- **Nov–Dec 2025: Topping & rebound.** Price peaked at ~$498.83 on Dec 22, 2025, after climbing from the high $400s. A sharp December selloff began, with TSLA closing $449.72 on Dec 31.
- **Jan–early April 2026: Sustained downtrend.** Price ground from ~$450 to a low close of $343.25 on April 8 (intraday low $337.24 on April 7). That's roughly a -31% peak-to-trough drawdown from December highs.
- **Mid-April → late May 2026: V-shaped recovery.** From the April 7 low ($346.65) to the May 14 swing high ($451.98 intraday), TSLA rallied ~30%. Since then it has consolidated in a $410–$445 range, closing **$435.79 on May 29**.

---

## 3. Trend Analysis

| Moving Avg | Value (May 29) | Close vs MA | Slope |
|---|---|---|---|
| 10 EMA | 429.48 | Price **above** (+1.5%) | Rising sharply (was 380.40 on May 1) |
| 50 SMA | 391.80 | Price **above** (+11.2%) | Turning up after months of decline |
| 200 SMA | 412.13 | Price **above** (+5.7%) | Still rising slowly (~$10 over the month) |

**Key observations:**
- Price reclaimed the 200 SMA in early May (200 SMA was ~$402.86 on May 1 and TSLA closed $390.82 that day; cross occurred mid-May as TSLA pushed above $410+). This is a structurally bullish event.
- The 10 EMA crossed back above the 50 SMA in early May (10 EMA went from 380.40 on May 1 to 429.48 on May 29; the 50 SMA only moved from 383.71 → 391.80), signaling renewed short-term momentum dominance.
- However, **10 EMA is decelerating**: 422.22 (May 14) → 417.10 (May 19) → 429.48 (May 29) — choppy, suggesting consolidation rather than a clean trend continuation.
- **No golden cross yet**: 50 SMA ($391.80) remains below 200 SMA ($412.13). Until that flips, the *long-term* posture remains technically neutral-to-cautious.

---

## 4. Momentum Analysis

**MACD line** rose from 0.76 (May 1) → peak 16.18 (May 14) → 12.07 (May 29). Still strongly positive but **rolling over from its peak**, then re-curling up the last 3 sessions.

**MACD Histogram** is the most telling:
- May 11: +6.75 (peak strength)
- May 21: -0.86 (turned negative — bearish momentum waning warning)
- May 29: +0.70 (back positive, signal-line re-cross)

This shows a **bullish re-acceleration** after a brief mid-May pullback. The histogram flip back positive on May 27–29 is a fresh short-term buy signal, though the magnitude is much smaller than the early-May surge — characteristic of a second leg trying to form.

**RSI** sits at **60.04** on May 29:
- Hit overbought 74.06 on May 11 (near the rally climax)
- Cooled to 50.30 on May 19 (healthy reset)
- Now climbing back through 60 — neither overbought nor oversold, room to run before the 70 threshold.

No bearish divergence is evident: price made a higher high May 13 ($453.40) and RSI made a lower high (70.19 vs 74.06 on May 11) — a **mild bearish divergence at the May peak**, which was confirmed by the May 14–19 pullback. Since then both have re-coupled lower, suggesting the divergence has been worked off.

---

## 5. Volatility Analysis

**Bollinger Upper Band**: 459.30 on May 29. TSLA closed $435.79 — well below the upper band (about $23.50 of headroom, ~5.4%). The May 11–14 surge briefly tagged/exceeded the upper band ($429.69 band vs $445 close on May 11), confirming the rally was a true volatility breakout, not noise.

**ATR**: 14.98 on May 29, down from a peak of 17.33 on May 13. Volatility is **cooling** — typical of a healthy consolidation after an impulsive move. Daily expected range is ~$15, so a typical stop-loss should be set at minimum 1.5× ATR (~$22) below entry.

---

## 6. Synthesized Outlook & Actionable Insights

**Bullish factors:**
1. Price above all three MAs (10 EMA, 50 SMA, 200 SMA) — a stacked bullish alignment for the first time since December 2025.
2. MACD histogram just flipped positive again (May 27–29) after a brief consolidation — fresh momentum buy trigger.
3. RSI at 60 with room to run.
4. ATR cooling supports a controlled grind higher rather than blow-off conditions.

**Bearish/caution factors:**
1. 50 SMA still below 200 SMA — no golden cross yet; long-term trend not fully repaired.
2. Mid-May bearish RSI divergence and the failure to hold $445+ shows distribution near $450.
3. MACD line is below its May 14 peak (12.07 vs 16.18) — momentum is weaker on this attempt.
4. Volume on the May 22–29 advance is modestly lower than during the May 7–14 surge (45–46M vs 60–78M), hinting at less conviction.

**Key levels to watch:**
- **Resistance:** $445 (May 11/13 swing highs), then $452 (May 14 intraday), then upper Bollinger at $459.
- **Support:** $422 (May 15 low), $410 (May 18 low), $404 (May 19 low). A break below $404 would invalidate the bullish setup and likely retest the 50 SMA at ~$392.
- **ATR-based stop** for new longs from current $435.79: ~$413–415 (1.5× ATR).

**Trade framing:**
- *Trend traders*: Buy pullbacks toward the 10 EMA ($429) or the $422 prior-low support. Target $452 → $459. Invalidation below $410.
- *Breakout traders*: Wait for a daily close above $445 with expanding volume to confirm continuation.
- *Risk-aware swing traders*: Reduce size; the lack of a golden cross and weaker MACD on this leg suggest higher probability of a range $410–$450 over the next 2–3 weeks.

---

## 7. Summary Table

| Theme | Reading | Signal |
|---|---|---|
| Short-term trend (10 EMA $429.48) | Price above, EMA rising | **Bullish** |
| Medium-term trend (50 SMA $391.80) | Price +11% above; SMA upturning | **Bullish** |
| Long-term trend (200 SMA $412.13) | Price above, but 50 < 200 | **Neutral-to-Bullish** |
| MACD ($12.07) | Positive, below May 14 peak | **Bullish, weakening 2nd leg** |
| MACD Histogram (+0.70) | Just flipped positive | **Fresh short-term buy** |
| RSI (60.04) | Mid-range, rising | **Bullish, room to run** |
| Bollinger Upper ($459.30) | Price 5.4% below | **Headroom, not overbought** |
| ATR ($14.98) | Cooling from $17.33 | **Healthy consolidation** |
| Key resistance | $445 / $452 / $459 | Watch for breakout |
| Key support | $422 / $410 / $404 | Invalidation < $404 |
| Net bias | Cautiously constructive | **Buy dips, not chase** |

*Note: I attempted to call `get_verified_market_snapshot` for cross-verification but that tool is not available in this environment. All values above are sourced directly from `get_stock_data` and `get_indicators` outputs and are tied to specific dates. The most recent trading session referenced is May 29, 2026 (May 30–31 are weekend).*