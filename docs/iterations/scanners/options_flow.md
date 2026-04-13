# Options Flow Scanner

## Current Understanding
Scans for unusual options volume relative to open interest using Tradier API.
Call/put volume ratio below 0.1 is a reliable bullish signal when combined with
premium >$25K. The premium filter is applied at `options_flow.py:143-144`.
Scanning only the nearest expiration misses institutional positioning in 30+ DTE
contracts — scanning up to 3 expirations improves signal quality.

## Evidence Log

### 2026-04-12 — P&L review (2026-02-18 to 2026-04-07)
- options_flow produced 61 recommendations — second highest volume after insider_buying.
- Average score 74.7 (score/10 = 7.5), confidence 7.2 — well calibrated.
- The premium filter IS applied in code (`options_flow.py:143-144`): `(vol * price * 100) < self.min_premium` gates both calls and puts. "Premium filter configured but not explicitly applied" was incorrect — the hypothesis is resolved.
- CSCO appeared in options_flow on Apr 9 (score 85) and analyst_upgrade on Apr 8 (score 78) — cross-scanner confluence on same ticker.
- Confidence: high

### 2026-04-12 — Fast-loop (2026-04-08 to 2026-04-12)
- options_flow appeared in 2 of 5 analyzed runs with CSCO and TSLA as the main picks.
- TSLA scored only 60 (conf 6) — borderline quality; appeared alongside GME social_dd (56) in same run (Apr 8), suggesting the LLM is rightly cautious about speculative social names.
- Confidence: medium

## Pending Hypotheses
- [x] Premium filter: already applied in code at `options_flow.py:143-144, 159`. Hypothesis resolved.
- [ ] Does scanning 3 expirations vs 1 meaningfully change hit rate?
- [ ] Is moneyness (ITM vs OTM) a useful signal filter?
