I have enough verified data. Let me also note: `get_verified_market_snapshot` was unavailable per the error, so I will rely on direct tool outputs from `get_stock_data` and `get_indicators`, and I will explicitly source every numeric claim.

# CRDO (Credo Technology Group) – Technical Analysis Report
**As of close Friday, May 29, 2026 (current date 2026-05-31, weekend)**

> Note on verification: The `get_verified_market_snapshot` tool returned an error and is unavailable. All numeric claims below are sourced directly from `get_stock_data` (OHLCV) and `get_indicators` outputs from this session. Where I cannot verify a level from the tool data, I avoid stating it.

## 1. Indicator Selection Rationale

I selected 8 complementary indicators across four dimensions to handle CRDO's exceptionally volatile regime (a ~63% peak-to-trough drawdown into late March followed by a ~169% rally):

| Category | Indicator | Why it's relevant for CRDO right now |
|---|---|---|
| Trend (long) | **close_200_sma** | Defines the macro trend; CRDO recently regained it after a deep break, making it a key reclaim test. |
| Trend (mid) | **close_50_sma** | Acts as the dynamic mid-term floor; the rally has taken price decisively above it. |
| Trend (short) | **close_10_ema** | Captures the velocity of the May squeeze; useful for tactical stops. |
| Momentum | **macd** | Confirms the trend-change from negative (April) to strongly positive territory. |
| Momentum | **macds** | Signal-line crossover validation – avoids reacting to single-bar MACD spikes. |
| Momentum (oscillator) | **rsi** | Independent overbought/oversold check given parabolic move; non-redundant with MACD because it's bounded. |
| Volatility | **boll_ub** | Identifies whether price is "riding the band" (strong trend) vs. exhausted breakout. |
| Volatility | **atr** | Sizes risk for an instrument whose true range has nearly doubled since April. |

I deliberately omitted boll/boll_lb (redundant with boll_ub for current context, since price is at the upper band, not the lower), MACD histogram (encoded in macd–macds spread), and VWMA (volume already informs the narrative qualitatively from OHLCV).

---

## 2. Price Action Narrative (Nov 2025 → May 29, 2026)

**Three distinct regimes in the lookback window** (sourced from `get_stock_data`):

1. **Distribution / decline (Nov 3, 2025 → Mar 30, 2026):**
   - Nov 3 close: **$180.64**; brief rally peak at Dec 2 high of **$213.80**, close $188.44.
   - Persistent lower highs and lower lows into a capitulation low: **Mar 30 low $86.49, close $87.81** – the cycle bottom in this dataset.
   - Drawdown from the Dec 2 intraday high to the Mar 30 low: ~**59.6%**.

2. **Base + V-shaped recovery (Mar 31 → Apr 24, 2026):**
   - Strong reversal day Apr 13 (close $134.36 vs. prior close $116.88) and Apr 14 gap-up (close $159.52, volume 18.5M – the highest single-day volume of the entire window).
   - By Apr 24 close: **$195.04**, more than doubling off the low in ~17 trading days.

3. **Pullback then squeeze to new highs (Apr 27 → May 29, 2026):**
   - Sharp pullback Apr 27–29 (low $164.80 on Apr 28, close $165.92).
   - Renewed rally with another shakeout on May 18 (low $150.41, close $156.27, volume 8.6M – biggest single-day decline of the recovery), immediately reclaimed.
   - Series of rising closes culminating: May 22 close **$218.41**, May 26 **$221.64**, May 29 close **$236.03** (intraday high $240.81 – the highest print in the dataset).

**Net result:** CRDO closed **May 29 at $236.03**, **+168.8%** off the Mar 30 closing low of $87.81 (calculated from get_stock_data).

---

## 3. Indicator-by-Indicator Read (verified values for May 29, 2026)

### Trend Structure
- **10 EMA: 209.51** | **50 SMA: 159.05** | **200 SMA: 145.23**
- Stack is **price (236.03) > 10 EMA > 50 SMA > 200 SMA** – a textbook fully-aligned bullish stack.
- The 50 SMA crossed back above the 200 SMA's neighborhood on the rally; on May 29 the 50 SMA (159.05) is now **+13.82 above** the 200 SMA (145.23), an embryonic golden-cross posture from `get_indicators` data.
- 10 EMA slope: rising from **174.23** (May 1) to **209.51** (May 29) = +20.3% in a month – aggressive short-term momentum.

### Momentum
- **MACD: 16.21**, **MACD Signal: 12.95** → MACD line is above signal by **+3.26**, and both lines turned positive on **Apr 15** (MACD 8.63, Signal 0.65 from the indicator output) after being deeply negative through early April (MACD bottom near **−6.66 on Apr 1**). This confirms the momentum-regime change.
- **RSI: 69.09** on May 29, up from 43.90 on May 18 (the squeeze low). RSI is **just below the classic 70 overbought threshold** but did not yet print >70 on May 29. Earlier in the rally RSI peaked at **78.40 on Apr 22**, which preceded the late-April pullback – a precedent worth respecting.

### Volatility
- **Bollinger Upper Band: 236.60** vs. close 236.03 → price is **literally riding the upper band** (within $0.57 / 0.24%). In strong trends this is normal; in tired trends it marks exhaustion.
- **ATR: 16.92** – elevated. Compare to **ATR 8.37 on Apr 1** – volatility has roughly **doubled**. A 1-ATR move at current levels is ~7.2% of price; risk parameters must widen accordingly.

---

## 4. Key Observations & Actionable Insights

**Bullish evidence (verified):**
- Full bullish MA stack (10 EMA > 50 SMA > 200 SMA); each MA is rising.
- MACD positive and above signal; the bullish cross (around Apr 14–15 per indicator output) preceded the largest gains.
- Three successive higher-high closes into May 29 ($221.64 → $222.35 → $236.03) on rising volume (May 26 vol 9.58M, May 29 vol 7.57M – above the typical 5–6M average earlier in the data).
- Reclaim of the 200 SMA from below has held convincingly.

**Caution flags (verified):**
- Price tagging boll_ub (236.60) on the same day RSI is at 69.09 – two simultaneous "near-overbought" readings.
- Prior instance of RSI >75 (Apr 22 RSI 78.40, close $189.49) was followed within 4 sessions by a pullback to $165.92 close on Apr 28 – a **−12.4%** pullback (calculated from OHLCV). Precedent suggests overbought readings here have produced ~10–15% mean-reversion shakeouts before resumption.
- ATR at 16.92 means a "normal" two-ATR adverse move is **~$33.84**, i.e., a pullback to ~$202 is statistically routine – not a structural break.
- The May 18 intraday low of $150.41 was a violent shakeout that closed strong, but it shows that even within this uptrend, single-day drawdowns of 15–20% remain possible.

**Levels traders should monitor (derived directly from tool data):**
- Resistance: **boll_ub at 236.60** (May 29 value) – immediate cap.
- Near-term support tiers: **10 EMA 209.51**, then prior breakout pivot ~**$193–198** (May 6 close 198.29, May 11 close 210.22 → range floor), then **50 SMA 159.05**.
- Invalidation of the bullish thesis: a daily close back **below the 50 SMA (~159)** would break the impulsive structure; a close below the **200 SMA (~145)** would re-open downside.

**Risk sizing:**
- ATR-based stop: a 1.5× ATR stop from $236.03 = **$210.65** (just below the 10 EMA – logical confluence).
- A 2× ATR stop = **$202.19** (aligns with prior breakout pivot).

---

## 5. Tactical Stance

The trend, momentum, and structure all point **up**, but extension is meaningful:
- Short-term: **overextended** (price kissing upper Bollinger, RSI ~69, 10 EMA 12.6% below price).
- Medium-term: **uptrend intact and confirmed**.

The disciplined play is **not to chase strength at the upper band**, but rather to use pullbacks toward the 10 EMA / prior pivot as the higher-probability re-entry. Existing longs from lower levels are justified in **trailing stops up to ~$210 (1.5× ATR / 10 EMA confluence)** rather than exiting outright, because the broader trend evidence is robust.

---

## 6. Summary Table

| Dimension | Indicator | Value (May 29, 2026) | Reading | Implication |
|---|---|---|---|---|
| Price | Close | **$236.03** | At all-time high in dataset | Trend leadership |
| Short trend | 10 EMA | 209.51 | Price 12.6% above | Overextended short-term |
| Mid trend | 50 SMA | 159.05 | Rising; price +48% above | Strong mid-term up-trend |
| Long trend | 200 SMA | 145.23 | Reclaimed; price +62% above | Macro trend turned bullish |
| Momentum | MACD / Signal | 16.21 / 12.95 | MACD > signal, both positive, rising | Momentum regime bullish |
| Momentum | RSI | 69.09 | Near 70 threshold | Approaching overbought, not yet stretched as in Apr (78.4) |
| Volatility | Bollinger Upper | 236.60 | Price riding the band | Strong trend OR exhaustion – watch next 1–2 closes |
| Volatility | ATR | 16.92 | ~2× early-April level | Use wider stops (1.5–2× ATR ≈ $25–34) |
| Key support | 10 EMA / prior pivot / 50 SMA | 209 / ~195 / 159 | Tiered support ladder | Pullback zones for re-entry |
| Key risk level | Below 50 SMA | <$159 | Would invalidate impulse | Defensive trigger |

**Overall bias:** Bullish trend, but tactically late-cycle within the move – favor buying pullbacks, not breakouts at the upper band.