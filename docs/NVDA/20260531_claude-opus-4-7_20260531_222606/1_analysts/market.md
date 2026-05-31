# NVDA (NVIDIA Corporation) — Technical Analysis Report
**As of close 2026-05-29 (latest trading day; 2026-05-31 is a Sunday)**

> Note: The user's instructions referenced a `get_verified_market_snapshot` tool, but that tool is not available in this environment. All numbers below come directly from `get_stock_data` and `get_indicators` outputs and are cross-checked between the two.

## 1. Indicator Selection Rationale

To avoid redundancy while covering all four major dimensions (trend, momentum, volatility, volume context), I selected:

| Category | Indicator | Why chosen |
|---|---|---|
| Trend (long) | `close_200_sma` | Confirms primary uptrend / golden-cross status |
| Trend (medium) | `close_50_sma` | Dynamic medium-term support reference |
| Trend (short) | `close_10_ema` | Captures fast momentum shift, especially after the May surge & pullback |
| Momentum | `macd` | Trend-following oscillator; captures larger waves |
| Momentum | `macdh` | Earliest visual cue of momentum loss (already turned negative) |
| Momentum | `rsi` | Identifies overbought blow-off (May 14 reading) and current cooling |
| Volatility | `boll_ub` / `boll_lb` | Defines breakout zone vs. reversion target; price tagged upper band on May 14 |
| Volatility/Risk | `atr` | Sizing and stop placement during expanding range |

VWMA was deliberately skipped — volumes are extreme on both up and down days (e.g., 360M on Feb 26 down, 288M on May 29 down), and VWMA mostly tracks the 50-SMA at this scale; ATR + Bollinger already capture the volatility regime more cleanly.

---

## 2. Price Structure & Trend Backdrop

**Latest close (2026-05-29): $211.14**, on heavy volume of 288.3M shares — the highest daily volume since the late-April breakout.

**Year-to-date arc (2026):**
- Jan: Rangebound around **$183–$192**.
- Feb 26–27: Sharp 2-day decline from $195.55 → $177.18 on **massive 360M+ volume** (likely earnings/macro shock).
- Mar–early Apr: Trended down to a YTD low around **$165.17 (Mar 30)**.
- April: Powerful recovery; broke back above 50/200-SMA; closed Apr at **$199.57**.
- May 1–14: Parabolic leg from ~$198 to a swing high of **$236.54 (May 14 intraday)** / **$235.74 close**.
- May 15–29: Distribution / pullback. Price has fallen **~10.4% from the May 14 high** to $211.14 in 11 trading sessions.

**Moving average alignment (2026-05-29):**
- Price $211.14 > 50-SMA $199.35 > 200-SMA $187.64 → **bullish stack still intact**.
- 10-EMA $215.83 is **above** price → short-term momentum has flipped negative; the 10-EMA itself peaked at **220.42 on May 20** and has rolled over.

This is the classic profile of a **healthy bull trend in a corrective phase**, not a trend reversal — yet.

---

## 3. Momentum: MACD & RSI

**MACD line:**
- Peaked at **9.33 on May 15**, has fallen for 9 straight sessions to **3.81 on May 29**.
- Still positive (above zero), so trend bias remains bullish, but momentum is decelerating sharply.

**MACD histogram (early-warning gauge):**
- Flipped from **+2.22 (May 14)** to **−2.17 (May 29)** — a clean bearish crossover of MACD below its signal line occurred around **May 21–22** (histogram crossed from +0.33 to −0.21).
- Histogram continues to deepen negatively → momentum sellers in control near-term.

**RSI:**
- Hit **76.7 on May 14** — overbought.
- Cooled to **49.4 on May 29** — now squarely neutral.
- No bullish divergence yet; RSI made a lower high while price did, so this is straightforward unwinding rather than a setup for an immediate bounce.

**Read:** Momentum fully confirms the pullback. The MACD/RSI combo says NVDA worked off an overbought condition and is now neutral — not oversold. If buyers re-engage, expect that to show first as RSI reclaiming 55+ and the MACD histogram turning back up.

---

## 4. Volatility: Bollinger Bands & ATR

**Bollinger Bands (20-period, 2σ):**
- Upper band (May 29): **$235.22** — price closed roughly **$24 below the upper band** (about 10%).
- Lower band (May 29): **$195.70** — about **$15 below current price**, and notably very close to the **50-SMA at $199.35**. This $195–$200 zone is a high-confluence support.
- Bands widened materially in mid-May (upper band rose from $217 on May 8 → $235 on May 14), reflecting the breakout volatility burst, and have stabilized since.

**ATR:**
- **$7.13** on May 29 (≈ **3.4% of price**).
- ATR rose from **$6.18 (May 5)** to a peak **$7.79 (May 21)** during the volatility expansion, and is slowly contracting.
- Translation: a normal daily range is roughly $7. Stops < 1×ATR will likely get noised out; **1.5× ATR ≈ $10.7** is a more durable swing-stop spacing.

---

## 5. Key Levels (evidence-based)

| Level | Price | Source / Evidence |
|---|---|---|
| **Major resistance** | **$235.74 / $236.54** | May 14 close / intraday high |
| **Near resistance** | **$215.83** | Current 10-EMA — must reclaim to restart momentum |
| **Pivot / current price** | **$211.14** | 2026-05-29 close |
| **Confluence support 1** | **$199–$200** | 50-SMA $199.35 + Bollinger lower band $195.70 + prior breakout zone |
| **Major support** | **$187.64** | 200-SMA, also Feb–Mar consolidation zone |
| **Bear-case target** | **$165–$172** | March 2026 lows |

---

## 6. Actionable Scenarios

**Bull case (price holds $200):**
- A successful test of the 50-SMA / lower Bollinger ($199–$200) followed by RSI reclaiming 55 and MACD histogram turning positive would set up a re-test of $235. Trade entry on a daily close back above the 10-EMA ($215.83) with stop below $199. R:R ≈ 1:2 to $235.

**Bear case (price loses $199):**
- A daily close below $199 breaks both the 50-SMA and lower Bollinger simultaneously — that would invalidate the May breakout and target the 200-SMA at **$187**, with risk to **$172** (March low retest) on continuation.

**Base case (most likely):**
- Sideways-to-down chop in the **$200–$220 range** for 1–2 weeks while moving averages catch up and RSI rebuilds energy. Volatility (ATR ≈ $7) suggests $5–10 daily swings are normal, so don't over-react to single-day moves.

**Risk management:** Use ATR-based stops. For a long swing entry, 1.5× ATR ≈ $10–11 stop. For a short, target lower Bollinger and trail.

---

## 7. Summary Table

| Dimension | Reading | Value(s) | Signal |
|---|---|---|---|
| Long-term trend | 200-SMA | $187.64 (rising) | **Bullish** |
| Medium-term trend | 50-SMA | $199.35 (rising) | **Bullish** |
| Short-term trend | 10-EMA vs price | $215.83 vs $211.14 | **Bearish (price below)** |
| Momentum (MACD) | MACD line | 3.81, falling from 9.33 | **Decelerating bullish** |
| Momentum (Histogram) | MACDH | −2.17 (negative since ~May 21) | **Bearish near-term** |
| Momentum (RSI) | RSI(14) | 49.4 (was 76.7 on May 14) | **Neutral, cooling** |
| Volatility (Bollinger) | Upper/Lower band | $235.22 / $195.70 | Price mid-range, room both ways |
| Volatility (ATR) | ATR(14) | $7.13 (≈3.4% of price) | Elevated but contracting |
| Key support confluence | 50-SMA + lower Bollinger | **$195–$200** | Critical line in the sand |
| Key resistance | May 14 high | **$235.74** | Must reclaim for new uptrend leg |
| Bias | — | — | **Constructive but cautious — wait for either $200 hold or 10-EMA reclaim** |

The longer-term uptrend in NVDA remains intact (price > 50-SMA > 200-SMA, both rising), but the short-term tape has clearly turned corrective after the May 14 blow-off. The **$199–$200 confluence is the trade**: holding it sets up a continuation attempt; losing it opens the door to a deeper retracement toward $187 and possibly $172.