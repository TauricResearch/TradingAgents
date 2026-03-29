# Feature Landscape

**Domain:** Options trading analysis module for multi-agent AI trading system
**Researched:** 2026-03-29

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Options chain retrieval (strikes, expirations, bid/ask) | Cannot analyze options without the data | Low | Tradier API, single endpoint |
| 1st-order Greeks display (Delta, Gamma, Theta, Vega) | Every options platform shows these | Low | Tradier returns these via ORATS |
| Implied volatility per contract | Fundamental to options valuation | Low | Tradier returns bid_iv, mid_iv, ask_iv |
| IV Rank / IV Percentile | Core metric for deciding whether to sell or buy premium | Medium | Requires 52-week IV history; Tradier historical data or yfinance for underlying HV |
| Options strategy recommendation (verticals, iron condors, straddles) | The whole point of the module | High | LLM agent synthesis from Greeks + IV + directional bias |
| Max profit/loss and breakeven calculation | Users need to understand risk before entering | Medium | Arithmetic on strike prices and premiums for each strategy type |
| DTE-based filtering | Standard workflow: filter by 30-60 DTE for income strategies | Low | Simple date math on expiration dates |
| Probability of profit (PoP) estimation | Expected by anyone familiar with tastytrade methodology | Medium | Approximated from delta (1 - delta for short options) or from IV |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 2nd-order Greeks (Charm, Vanna, Volga) | Most retail platforms only show 1st-order; this provides institutional-level insight | Medium | Compute via blackscholes library from spot + 1st-order Greeks |
| Gamma Exposure (GEX) analysis with dealer positioning | SpotGamma-style analysis is premium ($199+/mo); providing this free is high-value | Medium | Numpy vectorized computation; interpretation via LLM agent |
| Volatility surface construction (SVI fitting) | Visual and quantitative understanding of vol skew and term structure | High | SVI calibration via scipy; requires enough strikes per expiration |
| Gamma flip zone / Vol Trigger identification | Identifies price levels where market maker hedging shifts from stabilizing to destabilizing | Medium | Derived from cumulative GEX sign change |
| Call Wall / Put Wall levels | Support/resistance levels derived from options positioning | Low | Max gamma exposure strikes from GEX computation |
| Unusual options activity detection | Identifies potential smart money positioning | Medium | Volume/OI heuristics; limited by lack of trade-level data |
| TastyTrade methodology rules engine | Proven decision framework (IVR thresholds, 45 DTE entry, 21 DTE management, 50% profit targets) | Medium | Rules-based logic layer feeding into strategy selection agent |
| Multi-leg strategy construction with specific contracts | Most analysis tools stop at "consider a put spread"; this names exact contracts | High | Agent must select strikes, expirations, and legs based on all analysis |
| Transparent reasoning chain | Shows WHY each strategy was selected, educational value | Medium | LLM agent chain-of-thought exposed to user |
| MenthorQ-style composite scoring (0-5 Options Score) | Single number summarizing options environment for quick decisions | Medium | Composite of IV rank, GEX regime, flow signals, vol skew |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Order execution / broker integration | Scope creep; regulatory complexity; analysis-only mandate | Output recommendation with contract symbols users can copy to their broker |
| Real-time streaming dashboard | Project uses batch `propagate()` flow; streaming requires different architecture | Provide point-in-time snapshots; tastytrade streaming is for data freshness, not live UI |
| 0DTE strategy analysis | Requires real-time infrastructure, sub-second data; batch analysis is stale before execution | Focus on 7-90 DTE strategies where hourly data refresh is sufficient |
| Historical IV surface storage | Requires ORATS subscription ($$$) or building own historical database | Use current IV surface; flag historical context as future enhancement |
| Options backtesting engine | Separate domain; options backtesting requires historical vol surfaces, fill simulation | Defer to future project; existing backtrader dependency is for equities |
| Custom volatility models (Heston, local vol) | Over-engineering; SVI is sufficient for equity options smile fitting | Use SVI parametric model; only consider Heston if pricing exotics |
| Portfolio-level Greeks aggregation | Would need to track user positions; analysis-only module has no position state | Analyze individual strategies, not portfolios |

## Feature Dependencies

```
Options chain retrieval --> 1st-order Greeks display
Options chain retrieval --> IV per contract --> IV Rank/Percentile
Options chain retrieval --> GEX computation --> Gamma flip zone, Call/Put Walls
1st-order Greeks + spot price --> 2nd-order Greeks (Charm, Vanna, Volga)
IV per contract --> Volatility surface (SVI fitting) --> Vol skew analysis
IV Rank/Percentile + directional bias --> TastyTrade rules engine --> Strategy selection
GEX regime + IV environment + flow signals --> Composite score (Options Score 0-5)
Strategy selection --> Multi-leg construction --> Max P/L + breakeven + PoP
All analysis agents --> Options debate --> Options portfolio manager --> Final recommendation
```

## MVP Recommendation

Prioritize (Phase 1 -- core analysis pipeline):
1. Options chain retrieval via Tradier API (foundation for everything)
2. 1st-order Greeks display (already in Tradier response)
3. IV Rank / IV Percentile calculation
4. GEX computation with Call/Put Wall levels
5. Basic strategy recommendation (single agent, 3-4 strategy types)

Defer:
- **2nd-order Greeks**: Phase 2 -- requires blackscholes library integration
- **Volatility surface (SVI)**: Phase 2 -- complex calibration, needs robust error handling
- **TastyTrade rules engine**: Phase 2 -- rules are well-defined but need IV Rank as input
- **Unusual activity detection**: Phase 2 -- limited by data availability without trade-level feed
- **Multi-leg specific contracts**: Phase 2 -- needs strategy selection working first
- **Composite scoring**: Phase 3 -- needs all analysis components as inputs
- **Tastytrade streaming**: Phase 3 -- enhancement for data freshness, not core functionality

## Sources

- [SpotGamma GEX methodology](https://spotgamma.com/gamma-exposure-gex/)
- [TastyTrade methodology](https://developer.tastytrade.com/)
- [Tradier options chain endpoint](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains)
- [Unusual options activity heuristics](https://intrinio.com/blog/how-to-read-unusual-options-activity-7-easy-steps)
