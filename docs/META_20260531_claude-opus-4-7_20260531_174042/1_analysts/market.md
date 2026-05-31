I have all the data I need. Note: `get_verified_market_snapshot` is not available, so I'm relying on `get_stock_data` and `get_indicators` outputs as my source of truth. Let me synthesize the report.

---

# META Platforms (META) — Technical Analysis Report
**Analysis Date:** 2026-05-31 (last trading day: Friday 2026-05-29)
**Last Close:** $632.51 | **Prior Close (5/28):** $635.29 | **Daily Change:** −$2.78 (−0.44%)

> Data source note: The verified-snapshot tool was unavailable in this session; all numbers below are sourced directly from `get_stock_data` and `get_indicators` outputs. I've cited specific dates/values for each claim.

---

## 1. Big-Picture Context: A Volatile 7-Month Round Trip

The price tape over the last seven months tells a dramatic story:

- **Nov 2025 base** ~$590–$650
- **Late Jan 2026 melt-up to all-time highs**: 1/29/2026 high of **$743.36** (close $737.68 on ~60M volume — almost certainly an earnings reaction)
- **Mid-Feb to late-March collapse**: Steady distribution, capped by a **gap-down crash on 3/26–3/27** (close $547.54 → $525.72, low $520.26 on heavy volume of 30–35M). That's roughly a **−29% peak-to-trough** drawdown in two months.
- **April rebound**: Recovery to **$688.55** on 4/17, retesting prior support-turned-resistance.
- **April 30 second leg down**: Another large gap-down day ($668.91 open → $611.91 close, volume 52.7M — likely an earnings-related reset). Price re-tested the post-crash zone.
- **May consolidation**: Tight range $598–$640. The most recent two sessions (5/27–5/28) printed a **bullish reversal** with $635 closes on 23M and 16M volume — the first sign of demand returning. 5/29 gave back a fraction ($632.51).

Net: META is currently **−14.8% off the January peak** of $737.68 but has built what looks like a five-week base around $610.

---

## 2. Indicator-by-Indicator Read

### Trend Structure — 50-SMA, 200-SMA, 10-EMA

| Date | Close | 10-EMA | 50-SMA | 200-SMA |
|---|---|---|---|---|
| 2026-05-29 | 632.51 | 621.53 | 618.53 | 665.83 |
| 2026-05-22 | 610.26 | 610.83 | 617.80 | 668.65 |
| 2026-05-01 | 608.75 | 647.46 | 630.14 | 677.37 |
| 2026-04-17 | 688.55 | — | 629.56 | 680.26 |

**Read:**
- The **200-SMA at ~$665.83** is sloping **down** (was $684.60 on 4/1) — a clear **long-term trend deterioration**. Price has been below the 200-SMA since the late-March crash.
- The **50-SMA at ~$618.53** is also sloping down but is **flattening** (618.5 vs 617.8 a week earlier). The 50-SMA sits **below** the 200-SMA by ~$47, confirming a **death-cross regime** is firmly in place.
- The **10-EMA ($621.53) just crossed back above the 50-SMA ($618.53)** in the last two sessions — a **short-term bullish trigger** but only meaningful if confirmed by a sustained move above the 50-SMA. Friday's close of $632.51 is now **+2.3% above** the 50-SMA.
- The 200-SMA is the major **overhead resistance**: roughly **+5.3% above current price**.

### MACD (line only — paired with histogram via inference)

| Date | MACD |
|---|---|
| 2026-04-28 | +17.26 (peak) |
| 2026-05-04 | +3.32 |
| 2026-05-12 | −7.37 (low) |
| 2026-05-26 | −6.55 |
| 2026-05-29 | **−1.08** |

**Read:** MACD has executed a sharp negative swing from +17 in late April to −7.5 around 5/20. **Over the last four sessions it has rallied from −6.55 → −1.08**, a steep recovery. A **bullish zero-line crossover is imminent** if the next 1–2 sessions extend the move. Until it crosses zero, however, the trend-following signal is still net negative.

### RSI(14)

| Date | RSI |
|---|---|
| 2026-05-11 | 39.17 (low) |
| 2026-05-19 | 41.47 |
| 2026-05-26 | 46.46 |
| 2026-05-27 | 56.87 |
| 2026-05-29 | **55.36** |

**Read:** RSI bottomed near 39 (oversold-ish but not extreme) and has rebounded **above the 50 midline** — a classic **regime-shift signal from bearish to neutral-bullish momentum**. Not yet overbought (70+), so there's headroom for further upside before exhaustion.

### Bollinger Upper Band (boll_ub)

| Date | boll_ub | Close | Distance |
|---|---|---|---|
| 2026-05-01 | 717.59 | 608.75 | far below |
| 2026-05-15 | 696.53 | 614.23 | far below |
| 2026-05-29 | **634.07** | 632.51 | **kissing band** |

**Read:** The upper band has **collapsed from $717 → $634 in 4 weeks** — Bollinger compression is severe, indicating volatility has contracted sharply during May's consolidation. Friday's close of $632.51 is **right at the upper band ($634.07)**. This is significant: in a collapsing-band environment, a close *outside* the upper band is a high-probability **breakout signal**. Watch the next 1–2 sessions for a decisive close above ~$640 to confirm.

### ATR(14)

| Date | ATR |
|---|---|
| 2026-05-01 | 20.91 |
| 2026-05-15 | 17.06 |
| 2026-05-29 | **15.51** |

**Read:** ATR has compressed from ~$21 → ~$15.5 over the month — a **~26% drop in realized volatility**. Combined with the band squeeze, this confirms META is in a **coiled spring** setup. For risk management, a 2× ATR stop = ~$31, so a swing-trade stop on a long entered near $632 would sit around **$601** (also below the recent 5/19 swing low of $600.55).

### VWMA(20)

| Date | VWMA | Close |
|---|---|---|
| 2026-05-01 | 651.62 | 608.75 |
| 2026-05-15 | 617.27 | 614.23 |
| 2026-05-29 | **614.83** | 632.51 |

**Read:** Price ($632.51) is now **+2.9% above the volume-weighted MA**, after spending most of May *below* it. This is a **volume-confirmed bullish flip**. The 5/27 reversal day printed 23.1M volume (vs. recent ~12M average) — institutional accumulation footprint.

---

## 3. Confluence Synthesis

**Bullish near-term signals (last 2–3 sessions):**
1. 10-EMA crossed back above 50-SMA
2. MACD rallying hard toward zero (−1.08 from −7.5)
3. RSI broke above 50 midline
4. Price reclaimed VWMA on above-average volume
5. Bollinger squeeze + close at upper band = pending breakout
6. Two consecutive higher-volume up-closes on 5/27 ($635.26) and 5/28 ($635.29)

**Bearish/cautionary signals (still in force):**
1. 50-SMA < 200-SMA (death cross regime intact)
2. 200-SMA still sloping down at $665.83 — heavy overhead resistance
3. MACD still negative (not yet crossed zero)
4. Price still **−14.8%** from January high; no higher-high yet on the daily
5. April 30 gap-down ($668.91 → $611.91) created supply zone $640–$670

**Net interpretation:** META is at a **decision point**. The micro-trend (1–2 weeks) has clearly turned up, and the indicators are aligned for a **tactical bounce**, but the macro-trend (3–6 months) remains broken until price reclaims the 200-SMA at ~$666.

---

## 4. Actionable Trade Scenarios

| Scenario | Trigger | Target | Stop |
|---|---|---|---|
| **Long breakout** | Close > $640 (above boll_ub) | $666 (200-SMA), then $688 (April high) | $601 (below 5/19 low; ~2× ATR) |
| **Long pullback buy** | Test of $618 (50-SMA) holds | $640, then $666 | $598 (below 5/11 low) |
| **Short re-entry** | Failure at $666 (200-SMA) + MACD rolls back negative | $610, then $580 | $682 |
| **Stand aside** | Range $610–$640 with no expansion | — | — |

Risk-management note: ATR of ~$15.5 means a typical 1-day move of ±$15. Position size accordingly — a 1% portfolio risk on a $31 stop implies a position of ~3.2% of NAV per 1% risk taken.

---

## 5. Key Levels Reference Card

| Level | Price | Significance |
|---|---|---|
| All-time high (1/29/26) | $743.36 | Major resistance |
| Pre-crash high (4/17/26) | $688.55 | Swing resistance |
| April gap-down open | $668.91 | Supply zone |
| **200-SMA** | **$665.83** | Macro trend pivot |
| Bollinger upper band | $634.07 | Breakout trigger |
| **Last close** | **$632.51** | — |
| **50-SMA** | **$618.53** | Dynamic support |
| VWMA(20) | $614.83 | Volume-weighted pivot |
| Recent swing low (5/19) | $600.55 | Near-term support |
| Crash low (3/27) | $520.26 | Major structural support |

---

## Summary Table

| Dimension | Indicator | Value (2026-05-29) | Signal |
|---|---|---|---|
| Long-term trend | 200-SMA | $665.83 (down-sloping) | **Bearish** |
| Medium-term trend | 50-SMA | $618.53 (flattening) | Neutral → improving |
| Short-term trend | 10-EMA | $621.53 (turned up) | **Bullish** |
| Momentum (trend) | MACD | −1.08 (rising fast) | Neutral, turning bullish |
| Momentum (oscillator) | RSI(14) | 55.36 | **Bullish** (above 50) |
| Volatility (envelope) | Bollinger UB | $634.07 (collapsing) | Squeeze breakout pending |
| Volatility (range) | ATR(14) | $15.51 (compressing) | Coiling — expansion likely |
| Volume confirmation | VWMA(20) | $614.83 (price above) | **Bullish** |

**Overall posture:** Tactically constructive on a **breakout > $640** with target $666; structurally still in a downtrend until the 200-SMA is reclaimed. The setup currently favors a **long-bias swing trade with tight risk control**, not an aggressive position-build.