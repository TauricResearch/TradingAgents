# TIME Benchmark: Key Takeaways for TradingAgents

**Source:** arXiv:2602.12147v3 — "It's TIME: Towards the Next Generation of Time Series Forecasting Benchmarks"
**Full paper:** `docs/archive/time-benchmark-paper-2602.12147.md`

---

## What This Is

TIME (Task-centric benchmark with 50 fresh datasets, 98 forecasting tasks) evaluates 12 Time Series Foundation Models (TSFMs) on zero-shot forecasting.

---

## TSFM Rankings (2026)

| Rank | Model | Architecture | Params | Multivariate |
|------|-------|--------------|--------|--------------|
| 1 | Chronos-2 | Encoder-Decoder | 120M | ✅ |
| 2 | TimesFM 2.5 | Decoder | 200M | ❌ |
| 3 | TiRex | xLSTM | 35M | ❌ |
| 4 | Moirai 2.0 | Decoder | 11M | ❌ |
| 5 | Toto | Decoder | 151M | ✅ |

**Observation:** Newer iterations consistently outperform predecessors — genuine capability gains, not overfitting.

---

## Key Findings

### TSFMs excel at:
- **Seasonality capture** — strong advantage over naive baselines on seasonal data
- **Non-stationary data** — larger gains vs S-Naive on shifting statistical properties
- **Low complexity patterns** — superior models distinguish themselves on structured signals

### TSFMs struggle with:
- **High complexity (spectral entropy)** — performance equalizes across models
- **Conservative predictions** — flat forecasts score well on MASE/CRPS even when wrong
- **Spike capture** — quantitative metrics look fine but miss distinct spike structures

### Pattern-Level Evaluation (Actionable for WATCH-001)

The paper uses STL decomposition to extract 7 structural features:

| Feature | What It Measures | Use for Screening |
|---------|-----------------|-------------------|
| Trend Strength (F1) | Variability explained by trend | Flag trending tickers |
| Trend Linearity (F2) | Linear vs nonlinear trend | Detect clear trends |
| Seasonality Strength (F3) | Seasonal contribution to variability | Flag seasonal stocks |
| Seasonality Correlation (F4) | Stability of seasonal cycles | Consistent vs erratic |
| Residual ACF-1 (F5) | Remaining autocorrelation after STL | Forecast difficulty |
| Spectral Entropy (F6) | Overall complexity | Difficulty scoring |
| Stationarity (F7) | ADF test result | Non-stationary flag |

**Recommendation:** Add these as enrichment fields in `watchlist_enrichment` (R02). Use pattern features to weight screening priority.

---

## Warning: Metrics vs Reality

> "Flat forecasts may statistically yield competitive MASE or CRPS scores. However, quantitative metrics alone cannot distinguish whether the model has successfully captured the underlying dynamics or merely defaulted to a safe, conservative mean."

**Implication for trading:** Don't trust model confidence scores at face value. Visual inspection matters.

---

## Benchmark Contamination Warning

Legacy datasets (M4, LSF, Monash) are likely in pretrained model corpora. Fresh data = reliable evaluation.

**Implication:** For WATCH-001 screening, prefer fresh price feeds over historical archives.

---

## Relevant to:

- `briefs/2026-05-13-brief-curated-watch-lists.md` (WATCH-001) — pattern features for screening enrichment
- `src/server/lib/screening-engine.ts` — shock stock detection could use trend/seasonality features
- `src/cli/commands/screen.ts` — `--json` output could include pattern scores