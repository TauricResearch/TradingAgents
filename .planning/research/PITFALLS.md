# Domain Pitfalls

**Domain:** Options trading analysis module for multi-agent AI trading system
**Researched:** 2026-03-29

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Stale Greeks Leading to Wrong Recommendations

**What goes wrong:** Tradier's ORATS-sourced Greeks update hourly. During volatile markets, Greeks can shift significantly within that hour. An agent recommending a delta-neutral strategy based on stale deltas could suggest a position that is actually directionally biased.
**Why it happens:** Treating API-provided Greeks as real-time when they are snapshots.
**Consequences:** Wrong strategy recommendations; user loses money following stale analysis.
**Prevention:** Always display the Greeks timestamp from Tradier response. Include a staleness warning in agent output if Greeks are >30 minutes old. For the volatility agent, compute IV from current bid/ask prices using scipy rather than relying solely on API-provided IV.
**Detection:** Agent output includes delta-neutral recommendation but underlying has moved >1% since Greeks timestamp.

### Pitfall 2: SVI Calibration Failure on Illiquid Options

**What goes wrong:** SVI model calibration (5 parameters) fails or produces nonsensical results when there are few liquid strikes. Illiquid options have wide bid-ask spreads, making mid-price IV unreliable. The optimizer converges to a local minimum that produces arbitrage in the fitted surface.
**Why it happens:** SVI needs 5+ liquid strikes per expiration to calibrate well. Many stocks have illiquid far-OTM options.
**Consequences:** Garbage vol surface leads to wrong skew analysis; agent makes recommendations based on fitted IV that does not reflect reality.
**Prevention:** Filter strikes by minimum open interest (>100) and maximum bid-ask spread (< 30% of mid). Fall back to linear interpolation when <5 liquid strikes. Add arbitrage-free constraints to SVI calibration (Gatheral's no-butterfly-arbitrage conditions).
**Detection:** Fitted IV values that differ >10% from market mid IV at liquid strikes. Negative total variance at any point.

### Pitfall 3: GEX Sign Convention Confusion

**What goes wrong:** The GEX formula's sign convention for puts is a common source of bugs. Dealer gamma exposure from puts is negative (dealers are short puts, so they have negative gamma), but the formula `Net_GEX = sum(Call_GEX) - sum(Put_GEX)` already accounts for this. Getting the sign wrong inverts the entire analysis -- what should be a gamma wall becomes a flip zone and vice versa.
**Why it happens:** Different sources use different sign conventions. SpotGamma's published formula differs in sign treatment from some academic sources.
**Consequences:** Completely inverted market structure analysis. Agent tells user "market makers will buy the dip" when they will actually sell into it.
**Prevention:** Use a single, well-tested GEX function with explicit unit tests. Test against known SpotGamma outputs for SPY/SPX if available. The canonical formula: dealers are long gamma on calls they sold (positive GEX) and short gamma on puts they sold (negative GEX when viewed from dealer perspective).
**Detection:** Sanity check: for a typical equity, GEX should be positive at/above the current price and transition to negative below. If the opposite, the sign is wrong.

### Pitfall 4: Python Version Incompatibility with tastytrade SDK

**What goes wrong:** The tastytrade community SDK (tastyware/tastytrade v12.3.1) requires Python >=3.11. The project declares `requires-python = ">=3.10"`. If a user installs on Python 3.10, the tastytrade dependency will fail.
**Why it happens:** The project's minimum Python version is lower than the tastytrade SDK's requirement.
**Consequences:** Installation failure for Python 3.10 users; confusing error messages.
**Prevention:** Either bump `requires-python` to `>=3.11` or make tastytrade an optional dependency with graceful degradation (Tradier-only mode). Recommended: bump to >=3.11 since numpy/scipy latest versions also dropped 3.10.
**Detection:** CI testing on Python 3.10 would catch this immediately.

## Moderate Pitfalls

### Pitfall 1: LLM Hallucinating Option Contract Symbols

**What goes wrong:** When the LLM agent recommends specific contracts, it may hallucinate valid-looking but non-existent option symbols (wrong expiration dates, non-standard strikes).
**Prevention:** The strategy agent should select from actual contracts present in the chain data, not generate symbols from scratch. Pass the full list of available contracts to the agent and constrain output to only those symbols.

### Pitfall 2: IV Rank Calculation Window Ambiguity

**What goes wrong:** IV Rank and IV Percentile are often confused, and the lookback window (52 weeks vs 1 year vs rolling) affects the value significantly. Different sources define them differently.
**Prevention:** Be explicit about definitions in agent prompts and code:
- IV Rank = (Current IV - 52wk Low IV) / (52wk High IV - 52wk Low IV) -- range 0-100
- IV Percentile = % of trading days in the past year where IV was below current IV -- range 0-100
Use consistent 252-trading-day lookback. Document the definition in code comments.

### Pitfall 3: Options Expiration Date Edge Cases

**What goes wrong:** Not all options expire on the third Friday. Weekly options, quarterly options, end-of-month options, and index options (AM vs PM settlement) have different expiration rules. Assuming standard monthly expiration leads to wrong DTE calculations.
**Prevention:** Use the actual expiration dates returned by Tradier API rather than computing them. Never assume expiration day of week.

### Pitfall 4: GEX Across Expirations Without Weighting

**What goes wrong:** Naively summing GEX across all expirations treats a 1-day option the same as a 90-day option. Short-dated options have much higher gamma and dominate the GEX calculation, potentially masking important positioning at longer expirations.
**Prevention:** Weight GEX by relevance. SpotGamma focuses on the nearest 4 expirations. Consider computing GEX separately for 0-7 DTE, 7-30 DTE, and 30+ DTE buckets.

### Pitfall 5: Rate Limiting with Multiple Tradier Calls

**What goes wrong:** Each ticker analysis needs calls for: expirations list, chain per expiration (multiple), historical data. For a single ticker with 8 expirations, that is 9+ API calls. At 120 req/min, analyzing 10+ tickers hits limits.
**Prevention:** Cache expirations (they change weekly at most). Batch chain requests. Implement exponential backoff with retry. Consider only fetching the 4 nearest expirations (sufficient for most analysis per SpotGamma methodology).

## Minor Pitfalls

### Pitfall 1: Displaying Raw Greeks Without Context

**What goes wrong:** Showing "Delta: 0.45" without context is meaningless to many users.
**Prevention:** Agent should explain what the Greek means in the current context: "Delta of 0.45 means the option moves ~$0.45 for every $1 move in the underlying."

### Pitfall 2: Ignoring Dividends in Greeks Calculation

**What goes wrong:** Black-Scholes assumes no dividends. For dividend-paying stocks, computed Greeks (especially for long-dated options) will be slightly off.
**Prevention:** Use Black-Scholes-Merton (which accounts for continuous dividend yield) via the blackscholes library. Pass dividend yield as input parameter.

### Pitfall 3: Weekend/Holiday Theta Decay

**What goes wrong:** Theta is quoted per calendar day, but options do not decay linearly over weekends/holidays.
**Prevention:** Note in agent output that theta acceleration happens approaching expiration and that weekend theta is priced in on Friday afternoon.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Tradier API integration | Sandbox vs production API differences (delayed data in sandbox) | Test with sandbox, document limitations, flag in output |
| Greeks computation (2nd order) | Numerical instability near expiration (gamma explosion) | Cap computed Greeks at reasonable bounds, warn on <3 DTE options |
| SVI calibration | Convergence failure on illiquid names | Fallback to interpolation, minimum liquidity filters |
| GEX implementation | Sign convention error | Comprehensive unit tests against known outputs |
| Flow detection | False positives on unusual activity (earnings, ex-div dates) | Check corporate calendar before flagging activity as "unusual" |
| Strategy recommendation | LLM recommending strategies inappropriate for IV environment | TastyTrade rules engine as guardrail (e.g., do not sell premium when IVR < 20) |
| Multi-leg construction | Recommending spreads wider than available liquidity | Check bid-ask spreads on recommended legs; warn if total spread cost is >10% of max profit |

## Sources

- [SpotGamma GEX methodology and sign conventions](https://spotgamma.com/gamma-exposure-gex/)
- [Gatheral SVI arbitrage-free conditions](https://mfe.baruch.cuny.edu/wp-content/uploads/2013/01/OsakaSVI2012.pdf)
- [Tradier API rate limits and sandbox](https://docs.tradier.com/)
- [tastytrade SDK Python requirements](https://pypi.org/project/tastytrade/)
- [IV Rank vs IV Percentile definitions](https://www.tastylive.com/)
