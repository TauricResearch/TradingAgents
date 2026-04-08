# Options Flow Scanner

## Current Understanding
Scans for unusual options volume relative to open interest using Tradier API.
Call/put volume ratio below 0.1 is a reliable bullish signal when combined with
premium >$25K. The premium filter is configured but must be explicitly applied.
Scanning only the nearest expiration misses institutional positioning in 30+ DTE
contracts — scanning up to 3 expirations improves signal quality.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does scanning 3 expirations vs 1 meaningfully change hit rate?
- [ ] Is moneyness (ITM vs OTM) a useful signal filter?
