# Analyst Upgrades Scanner

## Current Understanding
Detects analyst upgrades/price target increases. Most reliable when upgrade comes
from a top-tier firm (Goldman, Morgan Stanley, JPMorgan) and represents a meaningful
target increase (>15%). Short squeeze potential (high short interest) combined with
an upgrade is a historically strong setup.

## Evidence Log

### 2026-04-12 — P&L review + fast-loop
- 36 tracked recommendations (mature). Win rates: 38.2% 1d, 50.0% 7d, 30.4% 30d. Avg returns: +0.13% 1d, -0.75% 7d, -3.64% 30d.
- 7d win rate of 50% is close to coin-flip; 30d degrades sharply.
- Recent runs (Apr 6-12): 7 candidates — LRN, SEZL, NTWK, CSCO, NFLX, DLR, INTC. INTC Apr 12 (score=85) had a strong catalyst (Terafab + Apple rumor), which is a genuine material catalyst, fitting the "already priced in" concern.
- CSCO appeared in analyst_upgrade (Apr 8) AND options_flow (Apr 6, Apr 9) — cross-scanner confluence is a positive quality signal.
- Confidence calibration: Good (cal_diff ≤ 0.5 across all recent instances).
- Confidence: medium (36 samples, 7d win rate at breakeven)

## Pending Hypotheses
- [ ] Does analyst tier (BB firm vs boutique) predict upgrade quality?
- [ ] Does short interest >20% combined with an upgrade produce outsized moves?
- [ ] Does cross-scanner confluence (analyst_upgrade + options_flow on same ticker) predict higher 7d returns?
