# Polymarket Phase A — Backtest Findings

## TL;DR

After running the research engine against 25 resolved markets across two
domains (crypto-FDV launches + cross-domain politics/sports/tech) with two
models (gpt-4o-mini, claude-sonnet-4-6), the honest read is:

**The pipeline produces calibrated outputs. It does not yet have proven edge.**

## Numbers

| Test | Model | Markets | Accuracy | HOLDs | Notes |
|---|---|---|---|---|---|
| Crypto-FDV (5) | mini | 5 | 60% | 0 | All BUY_YES, class-balance match, no real differentiation |
| Crypto-FDV (5) | Sonnet | 5 | 100% (4/4 + 1 HOLD) | 1 | Looks great, but training-data look-ahead almost certain |
| Crypto-FDV (10) | Sonnet | 10 | 100% (8/8 + 2 HOLDs) | 2 | Same caveat |
| **Cross-domain (10)** | **mini** | **10** | **70%** | **0** | First test where mini differentiated, 7 BUY_YES + 3 BUY_NO |
| **Cross-domain (10)** | **Sonnet** | **10** | **67% (6/9 + 1 HOLD)** | **1** | Truth-tell, Sonnet drops to mini-level once look-ahead is gone |

## Key findings

### 1. Sonnet's 100% crypto-FDV was partially recall
On post-cutoff diverse markets, Sonnet drops to ~67%. The crypto-FDV
markets are recent (Apr-May 2026), within the LLM's training horizon for
news ingestion. Cross-domain markets a few weeks earlier produce a
different shape entirely.

### 2. Both models share a "yes-it-happens" geopolitical bias
On the cross-domain set, both went BUY_YES on "Will another country
conduct military action against Iran by April 15?" (actual: NO). The
bull researcher prompt rewards finding any "evidence YES might happen,"
which over-weights low-probability dramatic events.

### 3. Sonnet's HOLD discipline is the only real differentiator
On 10 cross-domain markets, Sonnet HELD 1 (US escorts Hormuz, conf 0.52)
that mini lost on. Effective edge from HOLDs preserving capital is real
but small, 1 saved bet out of 10.

### 4. Sample size 25 is too small for any statistical claim
Need 30-50+ markets across diverse domains, ideally with `--end-date-max`
pushed back further to fully eliminate look-ahead bias.

### 5. Live testing on post-cutoff markets is the real signal
The 18 paper positions on Welsh/UK local elections (resolving over the
next 24-72h) cannot be recall, those events occur AFTER training.
That is the clean test.

## Implications for Phase B

The case for real-money execution is **NOT YET justified**:
- 67-70% accuracy on 10 markets is not statistically significant
- 2% Polymarket fees + slippage erode marginal edge
- Geopolitical drama bias unaddressed

Recommended sequence before any real-money move:
1. Score the live Welsh/UK positions when they resolve (post-cutoff truth)
2. Tighten bull/bear prompts to push back on drama bias
3. Run a 50-market backtest with `--end-date-max 2026-03-01` for a
   wider, less-recallable sample
4. Only then evaluate Phase B economics with the binary risk model
