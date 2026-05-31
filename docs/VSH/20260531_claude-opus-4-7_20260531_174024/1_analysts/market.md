# VSH (Vishay Intertechnology, Inc.) — Technical Analysis Report
**As of close: Friday, May 29, 2026 (last trading day before 2026-05-31)**

## 1. Price Action Overview

VSH has staged one of the most aggressive multi-month rallies in its recent trading history. The chart shows a classic three-phase progression:

- **Phase 1 — Capitulation Bottom (Nov 2025):** Price collapsed from ~$16.57 (Nov 3) to a closing low of **$11.67 (Nov 20)**, a ~30% drawdown over three weeks on rising volume.
- **Phase 2 — Steady Recovery (Dec 2025 – Mar 2026):** Price rebuilt from ~$12 to ~$20, with several pullbacks. The stock briefly broke down again to **$16.56 on Mar 30** before reversing.
- **Phase 3 — Parabolic Acceleration (Apr–May 2026):** From $18.00 close on Mar 31 to **$52.05 on May 29**, a roughly **+189% move in ~two months**. The most violent leg occurred May 12–29, where price moved from $33.63 to $52.05 (+55%) on dramatic volume expansion (sessions of 9.1M, 9.8M, 7.9M, 8.5M shares versus a typical 2M baseline). May 22 closed at $47.25 (+17.5% single-day gain), and May 26 closed at $50.37 (the first close above $50).

The intraday range on May 28 ($48.03–$53.60) and May 29 ($50.84–$55.24) shows that volatility is now extreme. The stock printed a wider 5-day true range than in any prior period.

## 2. Indicator-by-Indicator Analysis

### Trend (50 SMA, 200 SMA, 10 EMA)
- **Close:** $52.05 (May 29)
- **10 EMA (5/29):** **$45.74** — price ~13.8% above the 10 EMA, confirming acceleration steeper than even the fast trend filter can keep up with.
- **50 SMA (5/29):** **$28.95** — price is roughly **+80% above its 50-day average**, an extraordinary statistical extension.
- **200 SMA (5/29):** **$19.31** — price trades at **~2.7x the 200-day mean**, an exceedingly rare extension.
- The 50 SMA is rising sharply ($26.93 on 5/26 → $28.95 on 5/29) and is well above the 200 SMA ($18.76 → $19.31), confirming a textbook **bullish long-term trend regime**. Slope is steepening.

### Momentum (MACD, MACD Histogram, RSI)
- **MACD (5/29):** **6.28**, up from 4.63 on 5/22 and 3.85 on 5/20 — the line is rising and accelerating, not flattening.
- **MACD Histogram (5/29):** **+1.23**, expanded from +0.29 on 5/20 → +0.77 on 5/22 → +1.27 on 5/28. Histogram is making higher highs, signalling **no momentum divergence yet**; price strength is being matched by indicator strength.
- **RSI (5/29):** **84.13**. RSI has held above 70 essentially since early May (range 74–88 over the entire month). It hit a recent peak of **88.26 on 5/26**, then 84.85 on 5/28, and 84.13 on 5/29. This is a *trend-riding* RSI pattern — chronically overbought but not yet diverging. There is no negative divergence (price made new highs on 5/29, RSI did not exceed its 5/26 peak — a *very early* warning sign worth monitoring but not yet confirmed).

### Volatility (Bollinger Upper Band, ATR)
- **Bollinger Upper Band (5/29):** **$53.69**. Close of $52.05 sits just below the upper band — price is "riding the band," typical of strong trends but high-risk for late entries.
- The upper band has expanded enormously: **$31.97 on 5/04 → $53.69 on 5/29 (+68% in 19 sessions)**. This reflects exploding standard deviation.
- **ATR (5/29):** **$2.83**, up from $1.20 on 5/01 — a **+136% increase in average daily range**. A 1-ATR stop now equals ~5.4% of the share price; a 2-ATR stop (~$5.66) is required for breathing room.

### Volume Confirmation (VWMA)
- **VWMA (5/29):** **$42.34** vs. close $52.05. Price is ~23% above the volume-weighted mean — confirming that *the breakout is supported by genuine volume*, not just thin tape. Volume on the largest up-days (May 13: 11.9M; May 26: 9.8M; May 22: 9.1M) corroborates institutional participation.

## 3. Synthesis & Trading Implications

**Bullish factors:**
- All trend filters (10 EMA, 50 SMA, 200 SMA) stacked bullishly with steepening slopes.
- MACD and histogram both rising and at multi-month highs — no momentum exhaustion confirmed yet.
- VWMA confirms volume-supported breakout, not a low-liquidity squeeze artifact.
- Price is riding the upper Bollinger Band, a classic strong-trend behavior.

**Risk / caution factors:**
- RSI at 84 with two sessions of slightly lower readings despite higher closing prices (5/26 RSI 88.26 at close $50.37; 5/29 RSI 84.13 at close $52.05) — **earliest signs of nascent bearish divergence**. Not yet a sell signal but a yellow flag.
- Price extension of **+80% over the 50 SMA** and **+170% over the 200 SMA** is statistically unsustainable. Mean reversion risk is elevated.
- ATR has more than doubled, meaning future drawdowns will be measured in dollars, not pennies. A 2-ATR pullback ($5.66) is normal noise; a 50% retrace of the May 12–29 leg ($33.63→$52.05) targets ~$42.84 — close to the current 10 EMA and VWMA cluster.
- Two intraday reversals (5/27 and 5/29 both saw highs > $50.50/$55 sold off into close) hint at distribution emerging at the highs.

**Actionable observations:**
- **For trend-followers already long:** Trail a stop using ATR. A 2.5x ATR trailing stop from the close sits near **$45.00**, which coincidentally aligns with the 10 EMA ($45.74) — a logical defensive pivot.
- **For new long entries:** Chasing $52 into an 84 RSI is poor risk/reward. Wait for a pullback to the 10 EMA ($45.74) or VWMA ($42.34) zone, where prior breakout buyers are likely to defend.
- **For shorts/contrarians:** Premature. No bearish trigger has fired yet (no MACD crossdown, no break of 10 EMA, no confirmed RSI divergence). Wait for at least a daily close below $45 with expanding down-volume.
- **Key support levels to watch:** $45.74 (10 EMA), $42.34 (VWMA), $38.50 (May 13 close / breakout pivot), $33.56 (May 6 close).
- **Key resistance:** $53.69 (upper Bollinger Band), $55.24 (May 29 intraday high).

## 4. Caveats / Data Integrity Notes
- The `get_verified_market_snapshot` tool returned an "invalid tool" error and could not be used. All numbers above are sourced directly from `get_stock_data` and `get_indicators` tool outputs at the dates and values shown — no values are fabricated or reconciled.
- May 30–31, 2026 are weekend dates with no trading data; the most recent close is 2026-05-29.

---

## Summary Table

| Indicator | Value (5/29/2026) | Reading | Implication |
|---|---|---|---|
| Close | $52.05 | New cycle high | Strongest trend phase |
| 10 EMA | $45.74 | Price +13.8% above | Short-term momentum extreme |
| 50 SMA | $28.95 | Price +80% above | Medium-term overextended |
| 200 SMA | $19.31 | Price +170% above | Long-term highly stretched |
| MACD | 6.28 | Rising, multi-month high | Momentum still expanding |
| MACD Histogram | +1.23 | Higher highs, no divergence | Bullish, no exhaustion yet |
| RSI (14) | 84.13 | Chronically >70 since early May | Trend-riding; faint divergence vs 88.26 on 5/26 |
| Bollinger Upper Band | $53.69 | Price riding the band | Strong trend / overbought |
| ATR (14) | $2.83 | +136% vs 5/01 | Volatility regime change — widen stops |
| VWMA | $42.34 | Price +23% above | Volume confirms breakout |

| Trade Stance | Setup | Trigger | Stop / Invalidation |
|---|---|---|---|
| **Hold longs** | Trend intact, momentum positive | Continue holding while >10 EMA | Daily close <$45.00 (10 EMA & 2.5×ATR stop) |
| **New long (chase)** | Not recommended | — | RSI 84 + 80% above 50 SMA = poor R/R |
| **New long (pullback)** | Wait for retest | Buy bounce at $45.74 (10 EMA) or $42.34 (VWMA) | Close below $38.50 |
| **Short** | Premature | Need daily close <$45 + MACD bearish cross + RSI divergence confirmation | — |

**Net technical bias: Bullish trend, but with elevated mean-reversion and volatility risk. Best stance is to manage existing longs with disciplined trailing stops rather than initiate new exposure at current levels.**