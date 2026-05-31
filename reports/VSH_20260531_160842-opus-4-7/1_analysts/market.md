# VSH (Vishay Intertechnology) — Technical Analysis Report
**Date: 2026-05-31 | Sector: Technology / Semiconductors | Exchange: NYQ**

> ⚠️ **Tool Note**: The `get_verified_market_snapshot` tool was unavailable in this environment, so all numbers below are sourced directly from `get_stock_data` and `get_indicators`. Any reader should treat those tool outputs as the source of truth and flag conflicts rather than reconcile manually.

---

## 1. Price Action Overview (Nov 2025 → May 2026)

VSH has undergone an extraordinary, multi-stage rally over the last seven months:

| Phase | Dates | Approx. Range | Character |
|---|---|---|---|
| Capitulation low | Nov 3 → Nov 20, 2025 | $16.57 → $11.67 | Steep -29% selloff |
| Basing/recovery | Nov 21 → Dec 31, 2025 | $11.67 → $14.41 | Choppy mean reversion |
| First leg up | Jan 2 → Feb 3, 2026 | $15.20 → $20.62 | Breakout +35% |
| Consolidation/pullback | Feb 4 → Apr 1, 2026 | $20.62 → ~$16.56 (Mar 30 low) | Mid-trend correction |
| Second leg up (parabolic) | Apr 2 → May 29, 2026 | $18.58 → **$52.05** | Vertical +180% |

The most recent close on record (last available trading day, **2026-05-29**) is **$52.05**, with an intraday high of **$55.24**. Over the previous 7 sessions alone (May 21 → May 29), the stock advanced from $42.17 to $52.05 (+23%), and over the trailing 30 sessions has roughly doubled.

---

## 2. Indicator Selection Rationale (8 chosen)

I avoided redundant indicators (e.g., did not pair RSI with Stoch RSI, did not use both `boll` middle and `close_50_sma`) and selected a balanced set:

- **close_10_ema** – Short-term momentum tracker, critical for a parabolic move.
- **close_50_sma** – Medium-term trend / dynamic support.
- **close_200_sma** – Long-term trend benchmark; useful for golden-cross context.
- **macd** – Momentum confirmation and divergence detection.
- **rsi** – Overbought/oversold extremes — highly relevant given vertical move.
- **boll_ub** – Upper band tells us how stretched price is vs. statistical norm.
- **atr** – Volatility expansion gauge & for stop-loss sizing.
- **vwma** – Volume-weighted trend confirmation; key to validating the breakout.

---

## 3. Indicator Readings (latest = 2026-05-29)

| Indicator | Value | Reading vs. Price ($52.05) |
|---|---|---|
| Close (last) | $52.05 | — |
| 10 EMA | 45.74 | Price ~+13.8% above 10 EMA |
| 50 SMA | 28.95 | Price ~+80% above 50 SMA |
| 200 SMA | 19.31 | Price ~+170% above 200 SMA |
| MACD line | 6.28 (rising) | Strongly positive, expanding |
| RSI (14) | 84.13 | Deeply overbought (>70) — has been >74 every day in May |
| Bollinger Upper Band | 53.69 | Price riding just under upper band |
| ATR (14) | 2.83 | Volatility roughly **2.4x** April baseline (~$1.20) |
| VWMA | 42.34 | Price ~+23% above volume-weighted mean |

### Trend Structure
- Stack from top to bottom: **Price > 10 EMA > VWMA > 50 SMA > 200 SMA**. This is a textbook strong uptrend stack with maximum bullish ordering.
- 50 SMA crossed above 200 SMA earlier in the dataset (50 SMA = 28.95 vs 200 SMA = 19.31), confirming a long-standing **golden cross** posture.
- The 10 EMA has been rising every single session in May (27.42 on May 1 → 45.74 on May 29) — no near-term momentum cracks.

### Momentum
- MACD has more than **doubled** since May 1 (2.52 → 6.28) and continues to widen. No bearish crossover or hidden divergence yet — but the rate of expansion is unsustainable.
- RSI sits at 84.13 — extreme. Notably, RSI has been in the 74–88 zone for the **entire month of May** without resolving lower, which is consistent with a "ride the band" strong-trend regime, not a reliable mean-reversion signal on its own.

### Volatility
- ATR has roughly **doubled** in three weeks (1.40 on May 11 → 2.83 on May 29). Daily true ranges are now $3–$7. This is a clear **volatility expansion** phase typical of late-stage trends and squeeze-driven moves.
- Bollinger Upper Band has moved from 31.63 (May 1) to 53.69 (May 29). Price riding the upper band on May 22 ($47.25 close vs. 45.08 UB — closed *above* it) and May 26 ($50.37 vs. 47.88 UB — *above* it again) confirms a true breakout regime rather than typical overbought reversion.

### Volume
- The VWMA at 42.34 vs. price of $52.05 shows price has decisively leveraged from the volume-weighted mean.
- Volume itself has surged: May 13 (11.9M shares), May 22 (9.1M), May 26 (9.8M), May 29 (8.5M) — multi-fold the November/December baseline of ~1–2M. **Volume is confirming the trend**, not diverging.

---

## 4. Risk Signals to Monitor

1. **RSI sustained >80** with parabolic price action historically resolves with sharp 1–3 day flush events. The May 27 candle ($50.50 high to $47.27 low, close $48.90) already showed a -6% intraday drawdown.
2. **ATR expansion** means stop placement must widen — anything tighter than ~1× ATR ($2.83) is likely to be hit on noise alone.
3. **Distance from 50 SMA (~+80%)** is statistically extreme; mean-reversion to even the 10 EMA ($45.74) would be a -12% move; to the upper Bollinger middle line region (~$40 implied) would be -23%.
4. **No bearish technical confirmation yet** — MACD still rising, no lower high in price, no break of 10 EMA.

---

## 5. Actionable Insights

- **Trend-followers / existing longs**: The trend is intact and confirmed across all 8 indicators. Trail stops behind the **10 EMA (~$45.74)** or use **2× ATR ($5.66)** below recent close as a chandelier-style trail. Do not exit on RSI alone — strong trends can keep RSI extreme for weeks.
- **New buyers**: Chasing here carries asymmetric reward/risk. A pullback to the 10 EMA or VWMA ($42.34) zone offers a more defensible entry. A break of the 10 EMA on closing basis would be the first warning sign.
- **Counter-trend / shorts**: No technical confirmation of a top yet (no MACD cross-down, no break of 10 EMA, no lower high). Premature shorts have been punished throughout May. Wait for a daily close below 10 EMA AND MACD histogram contraction before considering it.
- **Risk managers**: Position sizing should reflect ATR doubling. A position calibrated to April volatility is now effectively oversized by ~2x in dollar-risk terms.

---

## 6. Summary Table

| Theme | Signal | Evidence | Implication |
|---|---|---|---|
| Long-term trend | **Strongly bullish** | Price $52.05 >> 200 SMA $19.31; golden cross intact | Macro trend = up |
| Medium-term trend | **Strongly bullish** | 50 SMA rising (26.93 → 28.95 in May); price +80% above | Don't fight the trend |
| Short-term momentum | **Bullish but extended** | 10 EMA rising daily; price +13.8% above it | Trend healthy, but stretched |
| MACD | **Bullish, expanding** | 2.52 → 6.28 in May, no bearish cross | Momentum still accelerating |
| RSI | **Overbought (caution)** | 84.13; >74 entire month of May | High mean-reversion risk; not a sell signal alone |
| Bollinger Upper Band | **Riding/breaking band** | Closed *above* UB on May 22 & May 26 | True breakout regime, not standard reversion |
| ATR (volatility) | **Expanded ~2.4x** | $1.20 (May 1) → $2.83 (May 29) | Widen stops; reduce size |
| VWMA | **Confirms trend** | VWMA $42.34, rising on multi-fold volume | Volume validates the rally |
| Recommended stance | **Hold/trail longs; do not chase; do not short blindly** | All 8 indicators align bullish; only RSI/ATR flag risk | Manage risk, let winners run |

---

FINAL TRANSACTION PROPOSAL: **HOLD**

(Bias: bullish-but-extended. Existing longs should hold with trailing stops near the 10 EMA at ~$45.74 or 2×ATR ($5.66) below close. New entries are not advisable at current extension; wait for a pullback to the 10 EMA / VWMA zone ($42–$46). Shorts are not yet justified — no technical breakdown has occurred.)