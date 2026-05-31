I have all data I need. Note: the `get_verified_market_snapshot` tool was unavailable in this environment (returned an error); I'll use `get_stock_data` and `get_indicators` outputs as my source of truth and explicitly flag this.

# SMCI (Super Micro Computer, Inc.) — Technical Analysis Report
**Date of analysis:** 2026-05-31 (Sunday — last trading day = Friday 2026-05-29)

> **Tooling note:** The `get_verified_market_snapshot` tool was not available in this environment (returned an "invalid tool" error). All exact figures below are sourced directly from `get_stock_data` and `get_indicators`. Treat them as authoritative for this report; flag any discrepancy if a verified snapshot becomes available later.

---

## 1. Price-Action Narrative (Nov 2025 – May 2026)

SMCI has traded through three distinct regimes over the lookback window:

| Regime | Window | Behavior |
|---|---|---|
| **Decline / capitulation** | Nov 3 → Dec 17, 2025 | Fell from $50.75 → $29.84 (~−41%). High-volume distribution. |
| **Choppy base** | Dec 2025 → Mar 19, 2026 | Range-bound roughly $29–$34 with brief spikes to ~$34.94 (Feb 4) and $33.86 (Feb 25). |
| **Crash + V-recovery + breakout** | Mar 20 → May 29, 2026 | **Mar 20: −33.3% single-session collapse from $30.79 to $20.53 on 242.96M shares (≈10× normal volume)** — likely a fundamental/news event. Bottomed $20.53 (Mar 20). Recovered methodically. **May 6: explosive +24.4% gap from $27.83 → $34.66 on 127.30M shares.** Last 5 sessions (May 22–29): +29.6% from $33.46 to $46.09 on rising volume (peak 93.04M on May 29). |

The most recent close (Fri 2026-05-29) is **$46.09**, the highest level since early November 2025.

---

## 2. Indicator Readings (latest = 2026-05-29)

| Indicator | Value | Interpretation |
|---|---|---|
| Close | **$46.09** | At a multi-month high |
| 10 EMA | **$37.52** | Steeply rising; price ~22.8% above it (extended) |
| 50 SMA | **$28.67** | Now upward-sloping (vs. ~$27.60 a month ago) — slow medium-term turn |
| 200 SMA | **$35.98** | Still **declining** (~$37.76 a month ago); price recently crossed *above* it |
| MACD line | **+3.226** | Strongly positive, accelerating from +1.58 (May 22) |
| MACD histogram | **+1.146** | Expanding bullish momentum (was +0.18 on May 22) |
| RSI(14) | **79.5** | **Overbought** (>70); first overbought print of the rally |
| Bollinger Upper Band (20) | **42.85** | Price ($46.09) is **above** upper band — band-walk regime |
| ATR(14) | **2.79** | Sharply elevated (was 1.63 on May 5); ~6% of price |

---

## 3. Detailed Trend & Momentum Analysis

### Trend structure
- **Short-term (10 EMA):** Inflected from $27.31 (May 1) to $37.52 (May 29) — a **+37% lift in 4 weeks**, characteristic of a momentum thrust phase.
- **Medium-term (50 SMA $28.67):** Has begun curling upward only in the last ~2 weeks. Price now sits ~61% above the 50 SMA — historically an unsustainable spread that typically mean-reverts.
- **Long-term (200 SMA $35.98):** Still in a **multi-month downtrend** (was $37.76 a month ago and $36.51 mid-May). Price closed *above* the 200 SMA on May 29 ($46.09 vs $35.98) — a notable medium-term signal but **the 200 SMA is not yet rising**, so this is a tentative trend reversal, not a confirmed one. A confirmed golden cross (50 > 200) would still require considerable additional advance — currently 50 SMA is ~$7 below the 200 SMA.

### Momentum
- **MACD** went positive around early May and has now accelerated to +3.23 — its highest reading in the dataset shown. **Histogram** has expanded sharply over the last 3 sessions (0.35 → 0.49 → 0.74 → 1.15), indicating momentum is *still accelerating*, not topping. No bearish divergence yet.
- **RSI at 79.5** is overbought. In strong impulsive trends RSI can stay overbought, but each successive spike to ~80 carries higher pullback risk. Watch for the first lower RSI high while price still rises — that would be the divergence warning.

### Volatility
- **ATR has nearly doubled** (1.63 → 2.79) in 3 weeks. Combined with the price *outside* the upper Bollinger band, this is a classic **expansion / band-walk** signature — bullish in the short term, but it inflates stop-loss distances and position-sizing risk significantly.
- The Bollinger upper band ($42.85) has been left behind; price closed $3.24 above it. Rallies that puncture the upper band typically either (a) keep band-walking for several days, or (b) snap back to the 20-day mid-line within 1–2 weeks. The 20-day mid-line ("boll" basis) is implicitly near ($42.85 - 2σ-distance), roughly the low-$30s, which aligns with the breakout zone.

### Volume confirmation
- The May 6 surge (127.3M shares) and May 29 close ($46.09 on 93.0M shares) both occurred on **3–5× normal volume**, supporting the move. Volume on the rally has been increasing into the late stages — a positive *and* a warning (climax behavior often follows).

---

## 4. Actionable Insights

**Bullish factors**
- All three trend MAs aligned with rising short-term slope; price reclaimed the 200 SMA.
- MACD and histogram both expanding — no negative divergence yet.
- High-volume breakout above the multi-month $34–35 ceiling (the May 8 high $35.64 and Mar 17 high $32.81).
- Bollinger band-walk + ATR expansion → momentum regime in force.

**Bearish / risk factors**
- RSI **79.5** = overbought; first such print since early November 2025 (when SMCI was at $50 just before the Nov decline began). Statistically extended.
- Price is **+22.8% above the 10 EMA** and **+61% above the 50 SMA** — historically these gaps mean-revert.
- 200 SMA is still **falling**; no confirmed long-term reversal yet.
- The March 20 capitulation (–33% in one day) demonstrates that SMCI is exposed to abrupt event-driven gaps — risk management is non-optional.

**Trade-management framework**
- **Trend-followers / momentum buyers** can stay long while price holds **above the 10 EMA (~$37.50)**. A close back inside the Bollinger band (<$42.85) on declining volume would be the first warning. A close below the 10 EMA = exit.
- **New-entry buyers** should *not* chase at $46+; wait for either (a) a pullback to the breakout zone (~$35–37, near the 10 EMA / prior resistance turned support) or (b) a multi-day consolidation with the upper band catching up.
- **Stops:** With ATR = 2.79, a 2-ATR stop = ~$5.6 below entry. That's a wide stop, justifying smaller-than-normal position size. A tighter swing stop would sit just below the May 27 low ($36.76) for active swing traders.
- **Targets:** The next reference levels above are the November 2025 supply zone of **$50–53** (Nov 3 high $53.01) — that is the logical first profit-take for the current swing.

---

## 5. Summary Table

| Theme | Reading | Signal | Action implication |
|---|---|---|---|
| Long-term trend (200 SMA) | $35.98, falling; price just crossed above | Cautiously improving | Not yet confirmed; await flattening of 200 SMA |
| Medium-term trend (50 SMA) | $28.67, rising | Bullish turn | Trend follower–friendly |
| Short-term trend (10 EMA) | $37.52, rising sharply | Strongly bullish | Use as trailing stop |
| Momentum (MACD / Hist) | +3.23 / +1.15, expanding | Bullish, accelerating | Still in trend — no exit signal yet |
| Overbought (RSI) | 79.5 | Overbought | Risk of pullback; do not chase |
| Volatility (ATR) | 2.79, elevated | Expansion regime | Reduce position size; widen stops |
| Bollinger Upper Band | $42.85, price $3.24 above | Band-walk / breakout | Momentum on, but extended |
| Volume | 93M on May 29 (3–5× avg) | Confirms breakout | Watch for climax/exhaustion volume |
| Key support | 10 EMA $37.50; breakout zone $35–37 | Logical pullback targets | Buy-the-dip entry zones |
| Key resistance | $50–53 (Nov 2025 supply) | First swing target | Profit-take zone |
| Major risk event reminder | Mar 20 2026 –33% single-day crash on 243M shares | Idiosyncratic gap risk | Always size for tail events |

**Bias:** Short-to-medium-term **bullish but extended**. Best execution is on a pullback into $36–38, not chasing $46. Long-term trend reversal is *probable but not yet confirmed* — keep the 200 SMA's slope on watch over the next 2–4 weeks.