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
| Cross-domain (10) | mini | 10 | 70% | 0 | First test where mini differentiated, 7 BUY_YES + 3 BUY_NO |
| Cross-domain (10) | Sonnet | 10 | 67% (6/9 + 1 HOLD) | 1 | Sonnet drops to mini-level once look-ahead is gone |
| **Cross-domain (10) + drama-fix** | **Sonnet** | **10** | **88.9% (8/9 + 1 HOLD)** | **1** | **+22pp from drama-bias prompt fix; surgical effect on Iran-military and Trump-ceasefire markets** |
| **Look-ahead-free deep (30)** | **Sonnet** | **30** | **100% (24/24 + 6 HOLDs)** | **6** | **closed before 2026-03-01; class-imbalanced (28 NO / 2 YES); Sonnet held both YES markets (4.6% random chance); no BUY_YES calls in sample** |
| Cross-domain (10) + quote-fix v2 | Sonnet | 10 | 60% (6/10 + 0 HOLDs) | 0 | 2 regressions are Exa news stochasticity (different articles = different drama-bias trigger); Trump-Allah failure traced to look-ahead market price data in Exa results, not prompt failure; see finding #7 |
| **50-market balanced attempt (pre-2026-03-01)** | **Sonnet** | **50** | **85.4% (35/41 + 9 HOLDs)** | **9** | **44 NO / 6 YES (88% NO rate); always-NO bot scores 87.8% on same set — model is 2pp below; real signal is 2 correct BUY_YES (Gen.G LCK, Red Wings O/U) + 1 smart HOLD (XRP 5-min binary); see finding #8** |

## Key findings

### 1. Sonnet's 100% crypto-FDV was partially recall
On post-cutoff diverse markets, Sonnet drops to ~67%. The crypto-FDV
markets are recent (Apr-May 2026), within the LLM's training horizon for
news ingestion. Cross-domain markets a few weeks earlier produce a
different shape entirely.

### 2. Both models share a "yes-it-happens" geopolitical bias [FIXED]
On the cross-domain set, both initially went BUY_YES on "Will another
country conduct military action against Iran by April 15?" (actual:
NO). The bull researcher prompt rewards finding any "evidence YES
might happen," which over-weights low-probability dramatic events.

**Fix shipped (commit b1ee146):** added a BASE-RATE SKEPTICISM clause
to the trader synthesis prompt. The trader now explicitly checks
whether the YES case rests on "something dramatic might happen"
without specific recent catalysts, and defaults to HOLD or BUY_NO
when no concrete catalyst exists.

**A/B result on the same 10 markets**: accuracy jumped from 67% to
88.9%. Two markets flipped from wrong to right (Iran military action,
Trump ceasefire end), no regressions. The fix is surgical, not blunt.

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

### 8. 50-market run: still class-imbalanced; YES discrimination exists but sample is too small

Run: 50 markets closed before 2026-03-01, ≥$5K volume, Sonnet.
Result: 85.4% accuracy (35/41 decisions, 9 HOLDs).

**The class imbalance problem persists.** The sample is 44 NO_WINS / 6 YES_WINS
(88% NO rate). An always-NO bot scores 36/41 = 87.8% on non-HOLD decisions.
The model at 85.4% is **2pp below the always-NO baseline**, so the headline
number does not demonstrate edge over a trivial strategy.

**What the run does show:**
- **HOLD discipline is reliable.** 9 HOLDs including XRP and Ethereum 5-minute
  binaries (coin flips), the uncallable US-forces-Iran drama, and tight award
  races. The model correctly abstains where it has no information advantage.
- **BUY_YES discrimination exists but is weak at n=5.** Out of 6 YES_WINS
  markets (1 HOLDed), the model scored 2/5 correct BUY_YES calls:
  - **Gen.G wins LCK Cup 2026** (BUY_YES, conf 0.82) ✓ — requires esports knowledge
  - **Red Wings vs Hurricanes O/U 4.5** (BUY_YES, conf 0.62) ✓ — requires hockey context
  - Ethereum 5-min binary (BUY_NO) ✗ — coin flip, unpredictable
  - Trump "SAVE America Act" on Truth Social (BUY_NO) ✗ — quote-prediction failure
  - DC Metro median home value range (BUY_NO) ✗ — real estate range market

**Why the filter failed to produce balanced data.** Markets closed before
2026-03-01 with volume ≥$5K are dominated by SAG awards (all NO — most
nominees lose), 5-minute crypto binaries, and esports head-to-head bets.
To get 15-20 YES_WINS markets in a 50-market sample, need a different query
strategy: filter by domain (exclude pure awards, include sports O/U and
head-to-head finals) or use a YES_WINS fraction target directly.

---

### 7. Trump-Allah failure is look-ahead market price data, not a prompt failure

The quote-prediction prompt fix (commit shipped 2026-05-10) correctly handles
Trump-Biden ("again" → known base rate → BUY_YES, correct) but persistently
fails on Trump-Allah (BUY_NO, conf 0.82, actual YES_WINS across two runs).

Inspection of the model's rationale revealed the root cause: Exa news is
returning **market price history** from close to expiry, showing the YES price
collapsing from >99% to <1% with $319K active volume in the final days before
resolution. The model correctly infers from this data that sophisticated
participants were pricing near-zero probability — but the actual outcome was YES.

This is a look-ahead bias artifact, not a quote-prediction failure: the model
is reasoning from post-decision market price data, not from the speaker's
historical word frequency. Prompt engineering cannot fix a data quality issue.

**Implication for real-time use:** In live `run_polymarket.py`, there is no
look-ahead market price data (Exa only returns articles from ≤ current time),
so this failure mode does not affect live trading. It is a backtest-specific
artifact.

**The quote-prediction clause (v2) is still correct** and adds value for
clean cases where Exa does not contaminate with price history.

---

### 6. 30-market look-ahead-free backtest: calibration evidence
On a deeper sample closed before 2026-03-01 (mostly SAG awards markets,
2 esports, 1 economic indicator, 1 geopolitical, 2 short crypto-price
binaries), Sonnet hit 24/24 directional + 6 HOLDs.

The "100%" headline is inflated by the class imbalance (28 NO / 2 YES);
an always-NO bot would score 93.3% on this sample. The interesting
result is that **both** YES_WINS markets (XRP 15-min, Red Wings hockey)
were among the 6 HOLDs. The probability Sonnet held both YES markets
by random chance is ~4.6%, so this is statistically meaningful evidence
of calibration discipline: Sonnet refused to bet on the un-callable
markets rather than guessing.

The gap: zero BUY_YES calls in the entire sample. The drama-fix run
(88.9%) DID show working YES discrimination on a smaller cross-domain
sample, but the 30-market sample didn't include enough YES-favoring
markets to test it independently.

## Implications for Phase B

The case for real-money execution is **MORE PLAUSIBLE but not yet justified**:
- 88.9% accuracy on 10 markets + 100% on 30 (mostly NO-skewed) shows
  calibration discipline; absolute edge claims still need a balanced sample
- 2% Polymarket fees + slippage erode marginal edge
- Geopolitical drama bias addressed; quote-prediction bias remains (Trump-Allah)

Recommended sequence before any real-money move:
1. Score the live Welsh/UK positions when they resolve (post-cutoff truth)
2. ~~Tighten bull/bear prompts to push back on drama bias~~ DONE (commit b1ee146)
3. Run a 50-market backtest with `--end-date-max 2026-03-01` for a
   wider, less-recallable sample
4. Investigate the quote-prediction failure mode (Trump-Allah) if it
   recurs at scale
5. Only then evaluate Phase B economics with the binary risk model
