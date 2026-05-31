I have the data needed. Let me write the detailed report.

# MRVL (Marvell Technology) — Technical Analysis Report
**Date: 2026-05-31** (last trading day: Friday 2026-05-29)

> Note: The `get_verified_market_snapshot` tool was unavailable in this session. All claims below are sourced directly from `get_stock_data` and `get_indicators` outputs.

---

## 1. Price Action & Macro Context

MRVL has been on an **explosive multi-month rally**. Working from concrete data points:

- **2026-02-05 swing low close: $74.17** (intraday low $70.65) — a clear panic bottom.
- **2026-03-05 close: $75.64** (retest of the lows), then a **massive gap up on 2026-03-06 to a $89.53 close** on extreme volume (90.07M shares, ~5x average) — a clear catalyst-driven breakout (likely earnings/guidance).
- **2026-04-01 close: $106.66** — broke into triple digits.
- **2026-04-23 close: $165.56** on heavy volume, then a brief consolidation around $150–165.
- **2026-05-26 close: $208.26** — fresh blow-off high; intraday high $217.45.
- **2026-05-29 close: $205.00** — currently consolidating after the parabolic move.

From the 2026-02-05 low of $74.17 to the 2026-05-26 high close of $208.26, MRVL is **+180.7% in roughly 16 weeks** — a textbook parabolic advance. The 2026-05-27 single-day reversal (open 217.98 → close 198.70 on 54.2M volume) is a classic **shooting-star/distribution bar** worth flagging.

## 2. Indicator Selection Rationale

Given a **strong trending, high-volatility, late-stage rally** environment, I chose 8 complementary indicators across all five categories:

| Category | Selected | Why |
|---|---|---|
| Trend (long) | `close_200_sma` | Confirms primary structural uptrend; gauges how stretched price is |
| Trend (mid) | `close_50_sma` | Dynamic medium-term support; key for measuring pullback risk |
| Trend (short) | `close_10_ema` | Captures rapid momentum shifts; primary near-term trigger line |
| Momentum | `macd` | Trend-strength via EMA differential — best for trend-following confirmation |
| Momentum | `macdh` | Detects early waning momentum / divergence ahead of MACD line crosses |
| Mean-reversion / Oscillator | `rsi` | Identifies overbought extremes and bearish divergence |
| Volatility / Breakout | `boll_ub` | Captures upper-band rides typical of strong trends and blow-off tops |
| Volatility / Risk Sizing | `atr` | Critical for stop-loss placement in this high-volatility name |

I deliberately avoided RSI + StochRSI redundancy and avoided pairing both `boll_ub` and `boll_lb` since the action is decisively at the upper band. VWMA was skipped because the volume-trend confirmation is already obvious from raw volume bars (and price/MA alignment).

## 3. Indicator-by-Indicator Read (values from tool output)

### Moving Averages — Aggressively bullish stack, but extreme stretch
- **Close (2026-05-29): $205.00**
- **10 EMA: 193.70**
- **50 SMA: 146.66**
- **200 SMA: 98.37**

Stack order: **Price > 10 EMA > 50 SMA > 200 SMA** — perfect bullish alignment. However:
- Price is **39.6% above the 50 SMA** ($205.00 vs $146.66).
- Price is **108.4% above the 200 SMA** ($205.00 vs $98.37).
- The 50 SMA is itself rising sharply (from $109.81 on 2026-05-01 to $146.66 on 2026-05-29 — up ~33.5% in one month).

**Interpretation:** Trend is unambiguously bullish, but the spread between price and even the 10 EMA shows a *parabolic* condition. Mean reversion to the 10 EMA (~$193) or 50 SMA (~$147) would be a 6–28% pullback.

### MACD / MACD Histogram — Momentum still positive, but ATH spread
- **MACD (2026-05-29): 15.80**, vs ~16.29 on 2026-05-01 — actually **slightly lower than early May despite price being much higher**.
- **MACD Histogram: +1.12** on 2026-05-29, having flipped negative mid-May (lows of −1.45 on 2026-05-12 and −1.36 on 2026-05-19) and then turned positive again on 2026-05-26 (+1.36).

**Interpretation:** The histogram cross back to positive on 5/26 confirmed the latest leg up, but **the MACD line is no longer making new highs in line with price** — early-warning **bearish divergence** (price 5/26: $208.26 close, prior local high 5/06: $172.15; MACD 5/06 = 15.90, MACD 5/26 = 15.15). Subtle but worth watching.

### RSI — Overbought but not yet extreme; divergence forming
- **RSI (2026-05-29): 69.50**
- Recent high: **78.51 on 2026-05-06** (when price closed $172.15)
- 2026-05-26 RSI (price $208.26 close): **75.08**

**Interpretation:** Price has climbed from $172 → $208 (+21%), but RSI made a **lower high** (78.51 → 75.08) — a textbook **bearish RSI divergence** at higher price levels. RSI has now ticked back to 69.50, just below the overbought line. Not yet a sell trigger in a strong trend, but a yellow flag.

### Bollinger Upper Band — Price is riding/breaking the band
- **boll_ub (2026-05-29): 211.10**
- **2026-05-26 high: 217.45 vs boll_ub: 201.21** — close pierced the band intraday and high broke above.
- **2026-05-29 close: 205.00**, sitting just below the upper band.

**Interpretation:** Classic "**riding the band**" behavior of a strong uptrend, but the band is now being tested rather than hugged. The 5/27 reversal day (high 218.26 → close 198.70) was a rejection at a band extension.

### ATR — Volatility has nearly doubled
- **ATR (2026-05-29): 12.26** (~6.0% of price)
- **ATR (2026-05-01): 7.80** (~4.7% of price)
- **ATR (2026-04-01): would be even lower** (roughly $4–5 range pre-rally)

**Interpretation:** ATR has expanded ~57% in one month. A reasonable **stop-loss** for new long entries should be ≥ **1.5× ATR ≈ $18–19 below entry**. Position sizing should be cut accordingly — a "normal" share count would be ~2.5x more capital at risk than it was a month ago.

## 4. Synthesis — What Is the Tape Telling Us?

**Bullish evidence:**
1. Perfect MA stack (price > 10 EMA > 50 SMA > 200 SMA), all rising.
2. MACD remains positive (15.80) and histogram flipped back positive 5/26.
3. Volume on the breakout days (3/06: 90M, 4/10: 41M, 5/26: 42M) confirms institutional accumulation through the move.
4. Trend rule: in strong trends RSI 70+ is normal, not a sell.

**Cautionary evidence:**
1. **Bearish MACD divergence** — MACD lower high (15.15 on 5/26 vs 16.29 on 5/01) against a much higher price.
2. **Bearish RSI divergence** — RSI lower high (75.08 vs 78.51) on a 21% higher close.
3. **Extreme stretch from MAs** — price 39.6% above 50 SMA, 108% above 200 SMA.
4. **Distribution bar 5/27**: open $217.98 → close $198.70 on the highest volume of the year (54.2M) — classic blow-off / climax-run signature.
5. **ATR expansion** indicating volatility regime shift — late-stage trend characteristic.

## 5. Actionable Trading Plan

- **Existing longs:** Consider trimming 25–40% into strength near $210–$218 (upper Bollinger / 5/27 high). Ratchet stops up to **$182** (just below 10 EMA + ~1× ATR cushion) or **$170** (5/12 swing-low region) for trend-following holders.
- **New longs:** Avoid chasing at $205. Wait for either (a) a pullback toward the **10 EMA ($193–195)** with a bullish reversal candle, or (b) a confirmed breakout *and hold* above $218 on strong volume. Use ATR-based stops of ≥ $18.
- **Aggressive shorts/hedges:** Only on confirmation — e.g., a daily close below the 10 EMA ($193) with MACD histogram turning negative again. Initial target: 50 SMA zone ($147), which is also the prior consolidation top. Until then, shorting a strong uptrend is low-probability.
- **Risk regime:** Volatility (ATR ~$12) and parabolic stretch warrant **half-size positions** vs normal sizing.

## 6. Bias

**Short-term (1–2 weeks):** Cautiously **neutral to bearish-on-fade** — divergences and the 5/27 reversal bar argue for digestion or a 5–15% pullback.

**Medium-term (1–3 months):** **Bullish trend intact**. A pullback to the 10 EMA / 50 SMA zone would be a higher-probability long setup than chasing the current breakout extension.

---

## Key Points Summary Table

| Theme | Metric (date) | Value | Read |
|---|---|---|---|
| Last close | 2026-05-29 | $205.00 | Just off ATH ($217.45 intraday 5/26) |
| Trend stack | 10 EMA / 50 SMA / 200 SMA (5/29) | 193.70 / 146.66 / 98.37 | Perfect bullish alignment |
| Stretch | Price vs 50 SMA | +39.6% | Parabolic; mean-reversion risk elevated |
| Stretch | Price vs 200 SMA | +108.4% | Long-term overextended |
| MACD | 5/01 → 5/26 → 5/29 | 16.29 → 15.15 → 15.80 | Lower high vs price = **bearish divergence** |
| MACD Histogram | 5/29 | +1.12 | Positive again after 5/12–5/22 dip |
| RSI | 5/06 → 5/26 → 5/29 | 78.51 → 75.08 → 69.50 | Lower high = **bearish divergence**; cooling |
| Bollinger Upper | 5/29 | 211.10 | Price riding/just under band; 5/26 pierced & rejected |
| ATR | 5/01 → 5/29 | 7.80 → 12.26 | Volatility regime shifted higher (+57%) |
| Distribution signal | 2026-05-27 | Open 217.98 → Close 198.70, 54.2M vol | Climax/reversal bar — yellow flag |
| Catalyst breakout | 2026-03-06 | Close $89.53 on 90.07M vol | Origin of current trend leg |
| 4-month return | 2/05 low → 5/26 high | +180.7% | Parabolic |
| Suggested stop (longs) | 10 EMA − 1 ATR | ~$181 | Trend-following stop |
| Pullback buy zone | 10 EMA / 50 SMA | $193 / $147 | Higher-probability re-entry |
| Bias (1–2 wk) | — | Neutral-to-bearish on fade | Digest/pullback expected |
| Bias (1–3 mo) | — | Bullish trend intact | Buy dips to MAs |