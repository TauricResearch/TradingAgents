Note: I attempted to call `get_verified_market_snapshot` per the system instructions, but the tool is not available in this environment. I will rely on the OHLCV pulled via `get_stock_data` and the indicator outputs as the source of truth for all numerical claims.

# AAPL Technical Analysis Report — As of 2026-05-31

## 1. Macro Context & Price Action Narrative

Apple Inc. (AAPL, NMS) closed Friday, **2026-05-29 at $312.06** (intraday high $315.00, low $309.53), capping an extraordinarily strong May 2026. Looking back over the past ~7 months of price action observed in the data:

- **Early Nov 2025:** Trading in the $266–$275 range.
- **Dec 2025:** Brief push to ~$288.08 high (12-03), then a multi-week consolidation/decline.
- **Jan 2026:** Sharp drawdown — from $277 down to a low of **$242.97 on 2026-01-20** (a ~12% decline in ~3 weeks).
- **Feb 2026:** Initial recovery to $280.39 (02-06), followed by a re-test down to $255.21 (02-13).
- **Mar 2026:** A second leg lower to **$245.28 (03-30)** — forming what appears to be a higher low vs. January.
- **April–May 2026:** A powerful, near-uninterrupted rally from ~$246 to ~$315 (+28% in ~9 weeks).
- **Late May 2026:** New highs each session (308.82 → 308.33 → 310.85 → 312.51 → 312.06), with daily ranges expanding.

This is a textbook V-shaped recovery, transitioning from a corrective downtrend into a confirmed uptrend, now in what appears to be the **late-stage / blow-off phase** based on overbought momentum readings.

---

## 2. Indicator-by-Indicator Analysis

### 2.1 Trend Structure — 50 SMA, 200 SMA, 10 EMA

| Date | Close | 10 EMA | 50 SMA | 200 SMA |
|---|---|---|---|---|
| 2026-05-01 | 279.88 | 270.93 | 260.98 | 254.67 |
| 2026-05-15 | 300.23 | 291.60 | 265.97 | 258.65 |
| 2026-05-29 | 312.06 | 305.87 | 275.11 | 262.79 |

**Key observations:**
- **Stacking is fully bullish:** Price > 10 EMA > 50 SMA > 200 SMA. This is the canonical "trend-up" alignment.
- **Gap between price and 50 SMA = ~$37 (≈13.4%).** This is a wide stretch — historically a sign of an extended move that often mean-reverts.
- **50 SMA slope:** Rising from $260.98 (May 1) → $275.11 (May 29), confirming medium-term acceleration.
- **200 SMA slope:** Gently rising ($254.67 → $262.79). The long-term trend has only recently turned constructive after the Jan–Mar correction.
- **10 EMA at $305.87** — price still above it, but the gap is narrowing (close $312.06 vs EMA $305.87 = only ~2% premium), meaning short-term momentum is decelerating slightly compared to mid-May when daily gains were larger.

### 2.2 Momentum — MACD & MACD Histogram

| Date | MACD | MACD Hist |
|---|---|---|
| 2026-05-01 | 4.36 | 0.91 |
| 2026-05-13 | 8.89 | 2.07 (peak) |
| 2026-05-22 | 10.04 | 0.99 |
| 2026-05-29 | 10.45 | 0.62 |

- **MACD line is at multi-month highs (~10.45)** and still rising — confirming an established uptrend.
- **However, the MACD histogram peaked on 2026-05-13 at 2.07** and has since narrowed to 0.62. This is a classic **bearish momentum divergence**: price keeps making higher highs ($298.87 → $312.51), but the rate of momentum acceleration is slowing.
- This does NOT signal an immediate reversal — it signals that the **easy gains of the rally are likely behind us**, and trend continuation will require fresh catalysts.

### 2.3 RSI — Overbought Stress Test

| Date | RSI |
|---|---|
| 2026-05-01 | 66.4 |
| 2026-05-13 | 75.98 |
| 2026-05-18 | 71.67 (brief cool-off) |
| 2026-05-22 | 78.63 |
| 2026-05-28 | **80.03** |
| 2026-05-29 | 79.00 |

- **RSI has been above 70 for nearly the entire month of May**, a hallmark of a strong trend, but Tuesday's print of **80.03 is an extreme reading**.
- Readings above 80 typically precede short-term consolidation or pullbacks even in healthy uptrends.
- No bearish RSI divergence yet — RSI made a new high (80.03 on 5/28) along with price, so the trend is not yet exhausted in classical divergence terms.
- **Trader takeaway:** Chasing here invites adverse short-term entry timing. Wait for RSI to reset to 60–65 area on a pullback.

### 2.4 Volatility — Bollinger Upper Band & ATR

| Date | Close | Boll UB | ATR |
|---|---|---|---|
| 2026-05-01 | 279.88 | 279.80 | 6.59 |
| 2026-05-13 | 298.87 | 299.67 | 6.29 |
| 2026-05-22 | 308.82 | 314.92 | 5.94 |
| 2026-05-29 | 312.06 | 318.72 | 5.56 |

- **Price has been "walking the upper band"** throughout May, which is bullish trend confirmation but also signals overextension.
- The **upper band at $318.72** is now ~2.1% above the close — limited near-term upside before encountering statistical resistance.
- **ATR has been declining** from ~$6.69 on 5/8 to ~$5.56 on 5/29. **Volatility is contracting even as price rises** — this is typical of a maturing trend before a volatility expansion event (often a sharp pullback or breakout).
- **Risk-management implication:** With ATR ≈ $5.56, a reasonable stop-loss for new long entries is ~1.5–2× ATR ($8.30–$11.10) below entry, e.g., a stop near **$300–$303** for any new long.

---

## 3. Synthesis — Confluence of Signals

**Bullish factors:**
1. Full bullish MA stacking (price > 10 EMA > 50 SMA > 200 SMA) with all slopes rising.
2. MACD line at cycle highs, still positive and above signal.
3. New all-time/period highs being made on rising volume (5/29 volume of 69.98M was elevated).
4. Higher-low structure since January confirmed.

**Cautionary / bearish-leaning factors:**
1. **RSI ≈ 79–80** — extreme overbought.
2. **MACD histogram divergence** — momentum decelerating despite higher prices.
3. **Price ~13% above the 50 SMA** — wide stretch typically mean-reverts.
4. **Declining ATR with rising price** — volatility compression often precedes a sharp move; in an extended trend, the resolution is more often a flush than continuation.
5. Bollinger upper band only ~2% above price — limited statistical headroom.

---

## 4. Actionable Trade Plan

- **Trend bias:** Bullish (medium and long term).
- **Tactical bias (1–3 weeks):** Cautious — trend is intact but extended. **Do not chase** at $312.
- **Preferred long entry zones** on a pullback:
  - **First support:** 10 EMA, currently ~$306, rising fast (likely ~$308–$310 next week). A shallow pullback that holds here is the ideal continuation buy.
  - **Stronger support / better risk-reward:** $295–$300 zone (mid-May breakout shelf) — would coincide with RSI resetting toward 60.
  - **Trend-breaker:** Loss of **50 SMA (~$275)** would invalidate the rally structure and warrant exit/reversal.
- **Upside target if trend continues:** Bollinger upper band $318–$320 in the immediate term; psychological $325 next.
- **Stop-loss for existing longs:** Trail below 10 EMA (~$305) or use 2× ATR (~$11) below entry.
- **For new positions:** Wait. The combination of RSI ≥ 79, MACD-histogram divergence, and price riding the upper band is a **classic "let it cool" setup**, not a "press the bid" setup.

---

## 5. Summary Table

| Indicator | Value (2026-05-29) | Reading | Implication |
|---|---|---|---|
| Close | $312.06 | New high | Strong uptrend |
| 10 EMA | $305.87 | Price above, gap ~2% | Short-term bullish, narrowing |
| 50 SMA | $275.11 | Price ~13% above | Medium-term bullish but extended |
| 200 SMA | $262.79 | Rising, well below price | Long-term trend turning up |
| MACD | 10.45 | Multi-month high | Trend confirmed |
| MACD Histogram | 0.62 (down from 2.07 peak on 5/13) | **Bearish divergence** | Momentum decelerating |
| RSI | 79.00 (peaked 80.03 on 5/28) | **Extreme overbought** | Pullback risk elevated |
| Bollinger Upper Band | $318.72 | Price ~2% below | Limited near-term headroom |
| ATR | 5.56 (down from 6.69 on 5/8) | Compressing | Volatility expansion likely |

---

## FINAL TRANSACTION PROPOSAL: **HOLD**

**Rationale:** The primary and intermediate trends are unambiguously bullish, so existing longs should be held with trailing stops below the 10 EMA / $305. However, the confluence of **RSI ~79–80, MACD-histogram divergence, price ~13% extended above the 50 SMA, and Bollinger upper-band proximity** makes initiating new longs at $312 a poor risk/reward proposition. A **HOLD** posture is warranted: stay long if already in, but wait for a pullback to the $300–$306 zone (or an RSI reset to ~60–65) before adding. Only a break below the 50 SMA (~$275) would shift the bias to outright bearish.