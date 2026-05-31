I have all the data needed. Let me compose a detailed report.

Note on data: A 10:1 stock split occurred on 2025-11-17 (visible in the raw data row), so all post-split prices are in the new split-adjusted scale (~$85–$110 range). Pre-split prices in the early November rows were already split-adjusted by the data feed (showing ~$110 in early November). The key observation: the verified snapshot tool was unavailable, so all claims below cite specific dates and values directly from `get_stock_data` and `get_indicators` outputs.

---

# NFLX (Netflix, Inc.) — Technical Analysis Report
**As of close 2026-05-29 (latest trading day; 2026-05-30/31 are weekend)**

## 1. Price Action Overview (Nov 2025 → May 2026)

NFLX has experienced a textbook three-phase cycle over the past seven months:

- **Phase 1 — Distribution / Decline (Nov 2025 – mid-Feb 2026):** Price fell from ~$115.75 (2025-11-12 high close) to a cycle low of **$75.86 on 2026-02-12**, a peak-to-trough decline of roughly **-34.5%**. Notable accelerations occurred 2025-12-05 (volume 133.4M, close $100.24, down from $103.22) and 2026-01-21 (volume 127.9M, close $85.36, gapping below the $87 area).
- **Phase 2 — Sharp V-Reversal (Feb 25 – mid-April 2026):** A capitulation low followed by an explosive recovery. The pivotal day was **2026-02-27**, which gapped higher with **200.8M shares** (the highest volume in the dataset) and closed at $96.24 from the prior $84.59 — a single-day +13.8% gap-and-go. Price ran to a swing high close of **$107.79 on 2026-04-16**.
- **Phase 3 — Renewed Downtrend (Apr 17 – present):** A second high-volume breakdown on **2026-04-17** (volume 125.96M, close fell from $107.79 to $97.31, a -9.7% drop) reignited a bearish leg. Price has since drifted lower to **$86.02 on 2026-05-29**, down ~20.2% from the April peak in just six weeks.

## 2. Trend Structure (Moving Averages)

| Date | Close | 10 EMA | 50 SMA | 200 SMA | VWMA |
|---|---|---|---|---|---|
| 2026-04-16 (peak) | 107.79 | 103.05 | 91.61 | 106.04 | 100.24 |
| 2026-05-29 (latest) | 86.02 | 87.58 | 93.04 | 101.20 | 87.64 |

**Key trend observations (all values verified above):**
- Price ($86.02) is **below all four moving averages** — short, medium, long, and volume-weighted — a strictly bearish stack.
- **10 EMA (87.58) < 50 SMA (93.04) < 200 SMA (101.20)** — a fully bearish alignment.
- The **50 SMA crossed below the 200 SMA** earlier in the period (a death-cross condition was already in place on 2026-04-01: 50 SMA 87.90 vs 200 SMA 107.25), confirming that the long-term regime turned bearish well before the latest leg down.
- The **50 SMA itself is now rolling over** — it peaked at ~95.54 on 2026-05-08 and has declined every session since to 93.04 (2026-05-29), reinforcing fresh negative medium-term momentum.
- VWMA (87.64) sitting essentially on top of the 10 EMA (87.58) but well below the 50 SMA tells us that **volume is not supporting any rally attempt**; the sellers are dominant on heavier days (note the 125.9M-share 2026-04-17 gap-down).

## 3. Momentum (MACD & RSI)

**MACD line history (2026-04-16 to 2026-05-29):**
- Peak bullish reading: **+3.93 on 2026-04-16**
- Crossed below zero around 2026-04-23/24 (0.55 → 0.11)
- Most negative reading: **-2.45 on 2026-05-14**
- Latest: **-1.66 on 2026-05-29**, with histogram printing **+0.06** (just barely positive after being deeply negative).

**MACD Histogram trajectory:** -1.06 (2026-05-05) → -0.96 (05-11) → -0.50 (05-14) → -0.10 (05-18) → **+0.28 (05-22)** → +0.06 (05-29). This is a **bullish momentum divergence in progress**: MACD line still negative, but histogram has shifted positive — signaling decelerating downside. However, the histogram itself has been **fading from +0.28 back to +0.06 over the last week**, hinting the bounce attempt is losing steam.

**RSI (14):**
- Latest: **37.12 (2026-05-29)**, in the lower neutral zone but **not oversold** (no print below 30 since 2026-05-11's 30.35 — that was the local momentum low).
- April 16 peak RSI was **79.09** (overbought) — almost a perfect mirror of the current readings.
- The fact that RSI has been making **lower highs** (79 → 45 → 41 → 37) while price has made lower highs and lower lows is a clean bearish confirmation; no bullish RSI divergence yet at the latest low.

## 4. Volatility (Bollinger Bands & ATR)

**Bollinger Bands (20-period):**
| Date | Close | Lower | Upper | Width |
|---|---|---|---|---|
| 2026-05-05 | 87.89 | 84.26 | 109.04 | 24.78 |
| 2026-05-29 | 86.02 | 84.91 | 91.29 | **6.38** |

The bands have **compressed dramatically** — from a width of ~24.8 in early May to **6.38** at the latest reading. This is a classic **Bollinger Squeeze** following a high-volatility event, and historically precedes a directional expansion. Price is hugging the **lower band ($84.91)**: in the last 8 sessions the close has not touched the upper band but has tested the lower band region multiple times (low of $85.10 on 2026-05-11, $85.59 on 2026-05-28).

**ATR:**
- Peaked at **3.52 on 2026-04-20** (post-gap shock).
- Has steadily contracted to **2.28 on 2026-05-29** — a ~35% volatility decline.
- For risk management at $86.02, a 1.5×ATR stop = ~$3.42, suggesting a stop placement near $82.60 for a long trade or $89.45 for a short.

## 5. Volume-Weighted Confirmation (VWMA)

VWMA at **$87.64** vs simple 10-EMA at **$87.58** — virtually identical. This convergence indicates the recent down-move is happening on **proportional, not exhaustive, volume** — neither a panic bottom nor a low-volume drift. The most recent high-volume sessions were red (e.g., 2026-05-05 volume 51.96M close $87.89 down from $91.02), reinforcing distribution.

## 6. Synthesis — Where Are We?

NFLX is in a **confirmed downtrend** (full bearish MA stack, RSI sub-50, MACD below zero) but is **short-term oversold-stretched** with a **Bollinger squeeze** and **bullish histogram divergence** suggesting a bounce setup. However, none of the classic bottoming signals have triggered:
- No RSI reading <30 with a higher-low divergence on price.
- No MACD bullish line cross (still -1.66).
- No reclaim of the 10 EMA on a closing basis (close $86.02 < 10 EMA $87.58).
- No volume capitulation in the 2026-05-29 session (only 39.7M shares — modest).

**Key Levels to Watch:**
- **Resistance 1:** $87.58–$88.00 (10 EMA, VWMA) — must reclaim for any short-term bullish thesis.
- **Resistance 2:** $91.29 (Boll upper) → $93.04 (50 SMA) — the critical line in the sand for a trend-change call.
- **Support 1:** $84.91 (Boll lower) — actively being tested.
- **Support 2:** $82.60 (1.5×ATR below current) → $79.62 (2026-02-03 low cluster).

**Actionable Insights:**
1. **Trend-followers / longer-term holders:** No long signal. Wait for either a 10 EMA/50 SMA reclaim with rising MACD, or a true oversold flush with bullish RSI divergence below 30.
2. **Mean-reversion / swing traders:** A bounce play is *possible* given the squeeze and histogram turn — but quality is poor. Only consider with a tight stop below $84.50 (Boll lower / recent swing) and a target of $91 (50 SMA from below). Risk/reward ~1.5:1, low conviction.
3. **Short-sellers:** Trend, MA stack, and momentum all align bearish. Best setup is a failed retest of $91–$93 (50 SMA + Boll mid). Risk above $93.50, target $80–$82.
4. **Volatility traders:** ATR contraction + Bollinger squeeze → expect a range expansion event within 1–3 weeks. Long straddle/strangle around $86 is a defensible structure ahead of that resolution.

---

## Summary Table

| Category | Indicator | Latest Value (2026-05-29) | Reading | Bias |
|---|---|---|---|---|
| Trend (short) | 10 EMA | 87.58 | Price $86.02 below | Bearish |
| Trend (medium) | 50 SMA | 93.04 | Rolling over from 95.54 peak | Bearish |
| Trend (long) | 200 SMA | 101.20 | Sloping down; price -15% below | Bearish |
| Volume Trend | VWMA | 87.64 | Price below; converged with 10 EMA | Bearish |
| Momentum | MACD | -1.66 | Below zero, slight upturn from -2.45 low | Bearish but improving |
| Momentum | MACD Histogram | +0.06 | Flipped positive from -1.06 (05-05) | Early bullish divergence |
| Momentum | RSI(14) | 37.12 | Lower neutral, not oversold | Neutral-bearish |
| Volatility | Bollinger Upper | 91.29 | Compressed from 109.04 | Squeeze |
| Volatility | Bollinger Lower | 84.91 | Price hugging this level | Pressure point |
| Volatility | ATR(14) | 2.28 | Down 35% from 3.52 peak | Compression / pre-expansion |

| Trade Setup | Trigger | Stop | Target | Conviction |
|---|---|---|---|---|
| Short-term Long (mean reversion) | Daily close > $87.60 (10 EMA) | $84.50 | $91.30 → $93.00 | Low |
| Trend Short | Failed retest of $91–$93 | $93.60 | $82.60 → $79.60 | Medium-High |
| Volatility Long (straddle) | Squeeze still active | n/a | Range break either way | Medium |
| Long-term Buy | RSI <30 + bullish divergence + 50 SMA reclaim | n/a | n/a | None yet |

**Overall technical bias: Bearish trend intact, with a low-quality short-term bounce setup. Squeeze warns of imminent volatility expansion — direction unconfirmed, but weight of evidence (full bearish MA stack, declining 50 SMA, no oversold capitulation) favors a downside resolution.**