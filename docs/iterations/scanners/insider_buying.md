# Insider Buying Scanner

## Current Understanding
Scrapes SEC Form 4 filings. CEO/CFO purchases >$100K are the most reliable signal.
Cluster detection (2+ insiders buying within 14 days) historically a high-conviction
setup. Transaction details (name, title, value) must be preserved from scraper output
and included in candidate context — dropping them loses signal clarity.

## Evidence Log

### 2026-04-12 — P&L review (2026-02-18 to 2026-04-07)
- insider_buying produced 136 recommendations — by far the highest volume scanner.
- Score distribution is healthy and concentrated: 53 picks in 80-89, 11 in 90-99, only 1 below 60.
- Confidence calibration is tight: avg score 78.6 (score/10 = 7.9) vs avg confidence 7.5 — well aligned.
- Cluster detection (2+ insiders → CRITICAL priority) is **already implemented** in code at `insider_buying.py:73`. The hypothesis was incorrect — this is live, not pending.
- High-conviction cluster examples surfaced: HMH (appeared in 2 separate runs Apr 8-9), FUL (Apr 9 and Apr 12), both with scores 71-82.
- Confidence: high

### 2026-04-12 — Fast-loop (2026-04-08 to 2026-04-12)
- Insider_buying dominates final rankings: 3 of 6 ranked slots on Apr 9, 2 of 5 on Apr 10, contributing highest-ranked picks regularly.
- Context strings are specific and include insider name, title, dollar value — good signal clarity preserved.
- Confidence: high

### 2026-04-12 — P&L update (180 tracked recs, mature data)
- Win rates are weaker than expected given high confidence scores: 38.1% 1d, 46.4% 7d, 29.7% 30d.
- Avg returns: -0.01% 1d, -0.4% 7d, -1.98% 30d — negative at every horizon.
- **Staleness pattern confirmed**: HMH appeared 4 consecutive days (Apr 6-9) with nearly identical scores (72, 85, 71, 82) — same insider filing, no new catalyst. FUL appeared Apr 9 and Apr 12 with identical scores (75). This is redundant signal, not confluence.
- High confidence (avg 7.1) combined with poor actual win rates = miscalibration — scanner assigns scores optimistically but real outcomes are below 50%.
- Confidence: high

### 2026-04-14 — P&L review (Apr 3-9 mature recs) + staleness filter implementation
- Staleness pattern confirmed at scale: PAGS appeared 4 consecutive days (Apr 3-6, identical $10.34 entry, same Director Frias $4.96M purchase). ZBIO appeared 4 consecutive days (Apr 3-6, same $5.59M cluster buy). HMH appeared 3 consecutive days (Apr 7-9, same CFO $1M purchase).
- 11 of 22 insider_buying picks in Apr 3-9 (50%) were stale repeats — same Form 4 filing surfaced daily within the 7-day lookback window.
- Root cause: `lookback_days=7` causes any filing made on day D to appear every day from D through D+6. The deduplication is within a single fetch, not across runs.
- Code fix: Added `_load_recent_insider_tickers(suppress_days=2)` in `insider_buying.py`. Loads the past 2 days of recommendation files and filters out tickers already recommended as `insider_buying`. This directly suppresses the PAGS/ZBIO/HMH pattern.
- Updated statistics: 184 recs total (+48 since last analysis). 7d win rate 45.9% (was 46.4%), 30d win rate 32.8%. Avg returns negative at all horizons: -0.01% 1d, -0.44% 7d, -1.62% 30d.
- Confidence: high (staleness pattern now confirmed across 3 distinct tickers in a single week)

## Pending Hypotheses
- [x] Does cluster detection (2+ insiders in 14 days) outperform single-insider signals? → **Already implemented**: cluster detection assigns CRITICAL priority. Code verified at `insider_buying.py:73-74`. Cannot assess outcome vs single-insider yet (all statuses 'open').
- [x] Does filtering out repeat appearances of the same ticker from the same scanner within 3 days improve precision? → **Implemented 2026-04-14**: staleness suppression added, uses 2-day lookback against recommendation history.
- [ ] Is there a minimum transaction size below which signal quality degrades sharply? (current min: $100K raised from $25K as of 2026-04-07)
- [ ] Does the staleness suppression (2-day lookback) measurably improve 7d win rate? Track over next 2 weeks.
