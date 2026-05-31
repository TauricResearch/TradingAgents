I have all the data I need. Note: the verified market snapshot tool was unavailable, so I'll cite numbers strictly from `get_stock_data` and `get_indicators` outputs.

# COIN (Coinbase Global, Inc.) — Technical Analysis Report
**As of: 2026-05-29 (last trading day before 2026-05-31)**

## 1. Market Context & Price Action Summary

Coinbase has been in a brutal **structural downtrend** since early November 2025, with cascading risk-off behavior consistent with crypto-sector deleveraging. Key reference levels:

- **Nov 3, 2025 high zone**: ~$340.87 (open) / $342.80 (high)
- **Feb 5, 2026 capitulation low**: $145.16 intraday — the cycle low
- **Mid-May 2026 swing high**: $222.35 (May 14 intraday) → close $212.01
- **Current close (2026-05-29)**: **$189.03**
- **Peak-to-trough drawdown**: roughly **−57.7%** ($342.80 → $145.16)
- **Rebound from Feb low to May high**: roughly **+53%** ($145.16 → $222.35)
- **Pullback off May 14 high to current**: roughly **−15%** ($222.35 → $189.03)

The last 8 trading days have been a clear distribution/lower-high failure: May 14 closed at $212.01 and price has since stair-stepped down through $195.43 (5/15), $184.99 (5/22), $173.78 (5/27 — fresh swing low close), with a partial recovery to $189.03 on 5/29.

## 2. Indicator Selection Rationale

For a high-volatility crypto-proxy stock that has just transitioned from oversold rally to a possible lower-high reversal, I chose 8 complementary indicators across four dimensions:

| Indicator | Category | Why it's relevant for COIN now |
|---|---|---|
| close_200_sma | Long-term trend | Confirms structural bear regime; price is far below it |
| close_50_sma | Medium-term trend | Tests whether the Feb–May rally produced a real trend change |
| close_10_ema | Short-term momentum | Captures the recent breakdown from $200+ to $189 |
| macd | Momentum trend | Just flipped from positive to negative — a key inflection |
| macdh | Momentum acceleration | Histogram negativity is deepening — confirms downside thrust |
| rsi | Overbought/oversold | Mid-range (~48), gives room either way; watch for <30 |
| boll_ub / boll_lb | Volatility envelope | Frames the May 14 upper-band rejection and lower-band target |
| atr | Volatility/risk sizing | ATR ~$12 is critical for stops in this name |
| vwma | Volume-weighted trend | Tests whether down moves carry stronger volume than up moves |

(That is 9 names but boll_ub & boll_lb are part of one Bollinger framework, so 8 distinct concepts.)

## 3. Trend Structure (Moving Averages)

| Date | Close | 10 EMA | 50 SMA | 200 SMA |
|---|---|---|---|---|
| 2026-05-14 | 212.01 | 203.27 | 191.94 | 255.33 |
| 2026-05-22 | 184.99 | 194.42 | 191.08 | 251.12 |
| 2026-05-29 | **189.03** | **187.68** | **189.35** | **248.43** |

**Observations:**
- **200 SMA at $248.43** is sloping down and sits ~31% above current price → the long-term trend remains decisively **bearish**. No golden cross is anywhere on the horizon.
- **50 SMA at $189.35** is *exactly* where price is trading. This SMA had been rising steadily from $178.87 on Apr 14 to a peak of $191.94 on May 14, but in the last two weeks it has **rolled over** ($191.94 → $189.35). Price closing 5/29 right on this line ($189.03 vs $189.35) makes it the **immediate pivot**: a daily close back above ~$190–$192 keeps the rally hope alive; sustained rejection here confirms a fresh leg lower.
- **10 EMA at $187.68** has turned sharply down from $203.27 (5/14) and is now *below* the 50 SMA — a short-term bearish cross. The fact that the 5/29 close ($189.03) closed *above* the 10 EMA after touching $173.78 on 5/27 hints at a near-term oversold bounce, but the EMA is still in a steep downtrend.

## 4. Momentum (MACD & RSI)

| Date | MACD | MACD Hist | RSI |
|---|---|---|---|
| 2026-05-14 | +5.08 | +1.19 | 58.15 |
| 2026-05-18 | +2.92 | −0.82 | 46.58 |
| 2026-05-22 | +0.06 | −2.08 | 44.47 |
| 2026-05-27 | −2.56 | −3.23 | **39.30** (cycle low for May) |
| 2026-05-29 | **−2.71** | **−2.13** | **48.64** |

**Observations:**
- **MACD turned negative on/around 2026-05-26** (−1.13 → −2.56 by 5/27), a clean **bearish crossover** of the signal line after riding positive territory throughout most of May. This is a meaningful trend-momentum sell signal.
- **MACD histogram** has been negative since 5/18 and reached a trough of −3.23 on 5/27. The slight improvement to −2.13 on 5/29 indicates **decelerating downside momentum**, consistent with a near-term bounce attempt — but the MACD line is still falling.
- **RSI = 48.64** on 5/29 is squarely in *neutral-to-weak* territory. It dipped to 39.30 (5/27) — close to but not at oversold. Importantly, RSI peaked at only 62.6 on May 11 even at the rally high, never reaching overbought — a sign of **weak underlying momentum** during the rally.
- The lack of bullish RSI thrust above 70 during a +50% rally is a structural warning that the Feb–May move was a counter-trend bounce, not a regime change.

## 5. Volatility (Bollinger Bands & ATR)

| Date | Close | BB Upper | BB Lower | ATR |
|---|---|---|---|---|
| 2026-05-14 | 212.01 | 217.13 | 182.90 | 13.85 |
| 2026-05-15 | 195.43 | 216.43 | 182.51 | 14.27 |
| 2026-05-22 | 184.99 | 213.90 | 179.16 | 12.76 |
| 2026-05-29 | **189.03** | **215.89** | **173.64** | **12.20** |

**Observations:**
- The May 14 high of **$222.35 intraday tagged and rejected the upper Bollinger band** ($217.13), producing the local top — a classic mean-reversion signal.
- Lower band is at **$173.64** and has been *expanding lower*, while the upper band is roughly flat. This is a "bands widening downward" pattern often seen in early downtrends.
- ATR of **$12.20** means a 1× ATR stop equals ~6.4% of price — extremely wide. Position sizes must be reduced accordingly. Recent ATR peaked at $14.27 mid-May and is now compressing slightly, which can precede the next directional move.

## 6. Volume Confirmation (VWMA)

| Date | Close | VWMA |
|---|---|---|
| 2026-05-14 | 212.01 | 198.73 |
| 2026-05-22 | 184.99 | 198.91 |
| 2026-05-29 | **189.03** | **194.98** |

- VWMA is rolling over from $199.77 (5/21) to $194.98 (5/29) and is now **above** the spot price. Price trading below VWMA confirms that **down days have carried more volume-weighted impact than up days** in the recent window.
- Notably, the heaviest volume bars in 2026 occurred on capitulation days (Feb 5: 29.6M; Feb 13: 32.4M) and the biggest ramp days (Mar 4: 27.2M; Feb 25: 23.8M). The recent decline 5/15–5/27 has been on more moderate but consistently elevated volume (10–16M), suggesting **steady distribution** rather than panic — typically more bearish than a single capitulation flush.

## 7. Synthesis — What the Tape Is Saying

**Bearish factors (dominant):**
1. Price ~31% below 200 SMA, which is still declining.
2. 10 EMA crossed below 50 SMA; both rolling over.
3. MACD has crossed below zero.
4. May 14 upper Bollinger band rejection → lower-high failure pattern.
5. VWMA above price; distribution-style volume on the decline.
6. RSI failed to reach overbought during the entire +53% rally — momentum quality was poor.

**Counter-bullish factors (weaker):**
1. RSI 48 is not yet oversold; room exists for a relief bounce.
2. MACD histogram improved 5/27 → 5/29 (−3.23 → −2.13) — momentum deceleration.
3. Price held above the Feb capitulation low ($145.16) by a wide margin.
4. 5/29's $189.03 close reclaimed the 10 EMA ($187.68) after a sharp drop.

## 8. Key Levels & Actionable Plan

- **Immediate pivot zone**: $189–$192 (50 SMA + 10 EMA cluster). A daily close above $192 reopens $200–$206.
- **Bull invalidation / re-short trigger**: A close back below $180 (recent congestion) opens path to test the lower Bollinger at **$173.64**, then the Feb–March consolidation around $160–$165.
- **Tactical resistance**: $206–$212 (May 4–13 supply); above that, $217 (BB upper) → $222 (May 14 swing high).
- **Risk management**: ATR ~$12. A reasonable swing stop is 1.5× ATR ≈ $18, so longs from $189 require stops near **$171**; shorts from $189 require stops near **$207**.

## 9. Summary Table

| Dimension | Reading | Bias |
|---|---|---|
| Long-term trend (200 SMA = 248.43) | Price 31% below, SMA falling | **Bearish** |
| Medium trend (50 SMA = 189.35) | Price = SMA, SMA rolling over | **Neutral → Bearish** |
| Short trend (10 EMA = 187.68) | Steep decline from 203, just reclaimed | **Bearish (slowing)** |
| MACD (−2.71) / Histogram (−2.13) | Below zero, histogram improving | **Bearish but decelerating** |
| RSI (48.64) | Neutral; never reached overbought on rally | **Neutral / structurally weak** |
| Bollinger (UB 215.89 / LB 173.64) | Rejected at upper band 5/14, drifting toward LB | **Bearish** |
| ATR ($12.20) | Elevated; ~6.4% of price | **High volatility — size down** |
| VWMA ($194.98) | Above price, declining | **Bearish** |
| **Net technical bias** | Lower-high reversal in progress; oversold bounce possible but structural trend down | **Bearish with tactical bounce risk** |

**Tactical takeaway:** The path of least resistance is down, but the very short term (1–5 days) carries elevated risk of a relief bounce toward $195–$202 given the oversold thrust into 5/27 and the slight MACD histogram improvement. The high-conviction setup is to **fade rallies into the $200–$212 zone** with stops above $217, targeting $173 and ultimately the $160–$165 area. Outright longs are not justified by the indicator confluence at this time.