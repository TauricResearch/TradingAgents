Now let me fetch the BTC price data first. I'll pull a generous lookback window to capture enough history for the 200 SMA and other long-term indicators.
Good, I have the price data. Now let me select 8 complementary indicators for BTC's current market conditions. Based on the price action — a significant downtrend from ~$55 in Oct 2025 to ~$28 in Feb 2026, followed by a consolidation/early recovery phase around $29-$32 — I'll choose indicators that cover trend, momentum, volatility, and volume:

1. **close_50_sma** — Medium-term trend direction
2. **close_200_sma** — Long-term trend benchmark
3. **close_10_ema** — Short-term momentum
4. **macd** — Momentum/trend crossover signals
5. **macds** — MACD signal line for trade triggers
6. **rsi** — Overbought/oversold conditions
7. **boll_ub** / **boll_lb** — Bollinger Bands for volatility
8. **atr** — Volatility for risk management

Let me fetch all 8 indicators now:
Now let me also fetch ATR for volatility-based risk management:
I now have all the data needed. Let me compile the comprehensive analysis.

---

# 📊 BTC Technical Analysis Report — April 14, 2026

## Executive Summary

**BTC** is exhibiting signs of a **nascent trend reversal** following a brutal ~42% decline from its October 2025 peak of $55.57 to its February 2026 trough of $28.15. The most recent close on April 13 printed at **$32.45**, with price now trading above both the 10 EMA and 50 SMA for the first time in months. The MACD has just crossed above the zero line — a historically significant bullish signal — while RSI sits in a healthy neutral zone at 57.6. However, the price remains deeply below the 200 SMA ($42.68), confirming the long-term downtrend is still intact. A Bollinger Band squeeze is forming, suggesting an imminent volatility expansion that could determine the medium-term direction.

**Overall Bias:** Cautiously Bullish (Short-to-Medium Term) | Bearish (Long-Term Trend)

---

## 1. Indicator Selection Rationale

Eight indicators were selected to provide complementary, non-redundant coverage across four dimensions:

| Category | Indicators Selected | Why These? |
|---|---|---|
| **Trend** | `close_10_ema`, `close_50_sma`, `close_200_sma` | Three timeframes (short/medium/long) reveal trend alignment and divergence; the EMA captures recent momentum while SMAs confirm structural trend. |
| **Momentum** | `macd`, `macds`, `rsi` | MACD + Signal line provide crossover-based directional signals; RSI provides independent overbought/oversold context without redundancy. |
| **Volatility** | `boll_ub`, `boll_lb`, `atr` | Bollinger Bands define price envelopes and squeeze conditions; ATR quantifies absolute volatility for position sizing and stop-loss calibration. |

This combination avoids overlap (e.g., no MACD histogram alongside MACD/Signal, no duplicate momentum oscillators) while ensuring every critical dimension is covered.

---

## 2. Trend Analysis: Moving Averages

### 2.1 Short-Term — 10 EMA

| Date | 10 EMA | Close | Position |
|---|---|---|---|
| Apr 13 | 31.37 | 32.45 | ✅ Price ABOVE |
| Apr 2 | 30.23 | 29.65 | ❌ Price BELOW |
| Mar 17 | 31.58 | 32.99 | ✅ Price ABOVE |
| Mar 6 | 30.53 | 30.12 | ❌ Price BELOW |

The 10 EMA has been rising from ~30.23 (Apr 2) to **31.37** (Apr 13), and price has pushed decisively above it with a **$1.08 premium**. This confirms short-term bullish momentum has re-engaged after a brief pullback in late March / early April.

### 2.2 Medium-Term — 50 SMA

The 50 SMA has been in a **persistent decline**, falling from 38.03 (mid-Feb) to **30.89** (Apr 13). However, price has now crossed above it — the first sustained break above the 50 SMA since the selloff accelerated in October 2025. This is a significant development:

- **Apr 13 close ($32.45)** vs. **50 SMA ($30.89)** = **+5.0% premium**
- The 50 SMA's rate of decline is flattening (~$0.10/day now vs. ~$0.25/day in Feb), suggesting downward momentum is exhausting.

### 2.3 Long-Term — 200 SMA

The 200 SMA stands at **$42.68** — a staggering **$10.23 (24%) above** the current price. This confirms:

- A **death cross** (50 SMA below 200 SMA) has been in effect, with the gap widening: 50 SMA ($30.89) vs. 200 SMA ($42.68) = **~$11.79 spread**.
- The long-term trend remains **definitively bearish**. Any recovery rally faces massive overhead resistance at the 200 SMA level.
- A golden cross is far from materializing, requiring months of sustained upward price action.

### Trend Verdict
**Short-term bullish, medium-term inflecting, long-term bearish.** The price is above the 10 EMA and 50 SMA but deeply below the 200 SMA. This is consistent with a **counter-trend rally within a larger downtrend** — not a confirmed trend reversal.

---

## 3. Momentum Analysis: MACD & RSI

### 3.1 MACD — Zero Line Crossover

The MACD line has undergone a **dramatic recovery**:

| Date | MACD | Signal | Histogram (implied) | Interpretation |
|---|---|---|---|---|
| Feb 13 | -2.783 | -2.239 | -0.544 | Deep bearish, below signal |
| Feb 25 | -2.345 | -2.488 | +0.143 | Bullish crossover (MACD > Signal) |
| Mar 13 | -0.688 | -1.162 | +0.474 | Accelerating bullish momentum |
| Apr 2 | -0.564 | -0.506 | -0.058 | Momentum stalling |
| **Apr 13** | **+0.074** | **-0.247** | **+0.321** | 🎯 **Zero-line crossover — bullish** |

**Key observations:**
1. **MACD crossed above zero on April 13** — the first positive MACD reading in this dataset. This signals that the 12-period EMA has crossed above the 26-period EMA, confirming medium-term momentum has shifted from bearish to bullish.
2. **MACD is above the Signal line** (0.074 vs. -0.247), generating a clear **buy signal**.
3. The recovery from -2.78 to +0.07 over ~40 trading days represents a **sustained, orderly bullish divergence** — not a spike-and-fade, which adds credibility to the signal.

⚠️ **Caution**: In late March (Mar 27–Apr 2), the MACD dipped again (-0.56), showing the recovery has not been linear. Traders should watch for follow-through above zero to confirm.

### 3.2 RSI — Recovering from Oversold

| Date | RSI | Zone |
|---|---|---|
| Feb 23 | 31.6 | ⚠️ Oversold |
| Feb 24 | 31.7 | ⚠️ Oversold |
| Mar 4 | 50.9 | Neutral |
| Mar 27 | 39.4 | Near oversold |
| **Apr 13** | **57.6** | ✅ Neutral-Bullish |

**Key observations:**
1. RSI bottomed at **~31.6** in late February — touching the oversold threshold (30) — and has since recovered to **57.6**, confirming the bearish momentum has subsided.
2. RSI has **not yet reached overbought territory** (70), meaning there is room for further upside before the rally becomes overextended.
3. The RSI trajectory (31 → 57 over ~7 weeks) mirrors the price recovery and aligns with the MACD's bullish crossover, providing **cross-confirmation**.
4. RSI briefly dipped to ~39 on March 27 during the late-March pullback, but quickly rebounded — suggesting buyers are defending lower levels.

### Momentum Verdict
**Bullish**. The MACD zero-line crossover combined with RSI's healthy 57.6 reading provides the strongest momentum signal in months. However, the rally is still in its early stages and requires sustained follow-through.

---

## 4. Volatility Analysis: Bollinger Bands & ATR

### 4.1 Bollinger Band Squeeze — Breakout Imminent

| Date | Upper Band | Lower Band | Bandwidth | Close | Position |
|---|---|---|---|---|---|
| Feb 13 | 44.26 | 26.10 | 18.16 | 30.43 | Mid-range |
| Mar 4 | 32.40 | 27.72 | 4.68 | 32.35 | Near upper |
| Mar 27 | 32.91 | 29.33 | 3.58 | 29.19 | Near lower |
| **Apr 13** | **33.24** | **28.86** | **4.38** | **32.45** | **Near upper** |

**Critical finding — Bollinger Band Squeeze:**
- Bandwidth has **collapsed from 18.16 to 4.38** (~76% contraction) over the past two months.
- The current bandwidth of ~4.38 on a ~$31 midline represents just **14.1% of price** — extremely compressed.
- This is a classic **Bollinger Squeeze** formation, which historically precedes significant breakout moves.
- **Price ($32.45) is pressing against the upper band ($33.24)** — just $0.79 below — signaling bullish pressure within the squeeze.

### 4.2 ATR — Volatility Declining

| Date | ATR | % of Price |
|---|---|---|
| Feb 13 | 1.77 | 5.8% |
| Mar 4 | 1.59 | 4.9% |
| Mar 27 | 1.22 | 4.2% |
| **Apr 13** | **1.12** | **3.5%** |

ATR has declined **37%** from 1.77 to 1.12, confirming:
1. **Volatility is compressing**, aligning with the Bollinger Band squeeze.
2. **Risk per trade is decreasing** — tighter stop-losses are viable.
3. **Volatility expansion is likely ahead**, given the squeeze conditions. Traders should prepare for a large directional move.

### Volatility Verdict
A textbook **Bollinger Squeeze** is forming with price pressing the upper band. Combined with declining ATR, this strongly suggests an imminent breakout. The direction will be determined by whether price can break and hold above $33.24 (upper band) or fails back toward $28.86 (lower band).

---

## 5. Key Price Levels

| Level | Price | Significance |
|---|---|---|
| **Immediate Resistance** | $33.24 | Bollinger Upper Band — breakout trigger |
| **Secondary Resistance** | $35.00 | Psychological level + prior support (Feb 2026) |
| **Major Resistance** | $42.68 | 200 SMA — defines the long-term trend |
| **Immediate Support** | $30.89 | 50 SMA — critical to hold for bullish case |
| **Secondary Support** | $28.86 | Bollinger Lower Band |
| **Critical Support** | $28.15 | February 2026 low — breakdown level |

---

## 6. Actionable Trading Scenarios

### Scenario A: Bullish Breakout (Probability: ~55%)
- **Trigger**: Daily close above **$33.25** (Bollinger Upper Band) with expanding volume.
- **Entry**: On breakout confirmation above $33.25, or on retest of $33.25 as support.
- **Target 1**: $35.00 (psychological + prior support-turned-resistance)
- **Target 2**: $37.50 (Nov 2025 breakdown zone)
- **Stop-Loss**: Below 50 SMA at $30.50 (**1.5× ATR** from current price = ~$1.68 risk)
- **Risk/Reward**: ~1:1.5 to T1, ~1:3.0 to T2

### Scenario B: Range Continuation (Probability: ~30%)
- **Trigger**: Price remains between $28.86–$33.24 (Bollinger Bands).
- **Strategy**: Range-trade with buys near $29.00 and sells near $33.00.
- **Stop-Loss**: Below $28.15 (February low).
- **Key tell**: RSI oscillating between 40–60 without breakout.

### Scenario C: Bearish Breakdown (Probability: ~15%)
- **Trigger**: Daily close below **$28.86** (Bollinger Lower Band) and February low ($28.15).
- **Entry**: Short on breakdown below $28.00 with volume confirmation.
- **Target**: $25.00–$26.00 (extrapolated lower Bollinger expansion zone)
- **Stop-Loss**: Above $30.00 (1.5× ATR above breakdown)
- **Note**: This scenario becomes more likely if MACD re-crosses below zero and RSI drops below 40.

---

## 7. Risk Management Guidelines (ATR-Based)

| Parameter | Value | Calculation |
|---|---|---|
| Current ATR | $1.12 | 14-day average true range |
| Suggested Stop Width | $1.68 | 1.5× ATR |
| Suggested Position Size | 2–3% of capital per $1.68 risk | Standard risk management |
| Maximum Daily Expected Move | ±$1.12 | Based on ATR |
| Trailing Stop Suggestion | $2.24 below high | 2× ATR for trend-following |

---

## 8. Summary Dashboard

| Indicator | Latest Value | Signal | Trend |
|---|---|---|---|
| **Price** | $32.45 | — | Recovering from $28.15 low |
| **10 EMA** | $31.37 | ✅ Bullish (Price above) | Rising |
| **50 SMA** | $30.89 | ✅ Bullish (Price above) | Declining but flattening |
| **200 SMA** | $42.68 | ❌ Bearish (Price far below) | Declining |
| **MACD** | +0.074 | ✅ Bullish (Zero-line cross) | Rising sharply |
| **MACD Signal** | -0.247 | ✅ Bullish (MACD > Signal) | Rising |
| **RSI** | 57.6 | ✅ Neutral-Bullish | Rising from oversold |
| **Bollinger Upper** | $33.24 | ⚠️ Near resistance | Narrowing (Squeeze) |
| **Bollinger Lower** | $28.86 | Support floor | Narrowing (Squeeze) |
| **ATR** | $1.12 | Declining volatility | 37% lower vs. Feb |
| **Overall Bias** | — | **Cautiously Bullish** | Counter-trend rally |

---

## 9. Conclusion

BTC is at a critical technical juncture. The **MACD zero-line crossover**, **RSI recovery to 57.6**, and **price above both the 10 EMA and 50 SMA** collectively signal the strongest bullish momentum since the October 2025 selloff began. The **Bollinger Squeeze** — with bandwidth compressed 76% — indicates a major move is imminent.

However, this remains a **counter-trend rally** within a broader bearish structure (price 24% below the 200 SMA, death cross in effect). The most prudent approach is to **trade the breakout, not the anticipation**: wait for a confirmed close above the Bollinger Upper Band ($33.24) before initiating long positions, with disciplined ATR-based stop-losses at ~$30.50.

> **Bottom Line**: The short-term setup favors bulls, but the long-term trend demands caution. Position sizing should reflect the counter-trend nature of any long trade, and traders must be prepared to reverse if the Bollinger Squeeze resolves to the downside.