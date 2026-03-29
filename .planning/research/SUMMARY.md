# Project Research Summary

**Project:** TradingAgents Options Trading Module
**Domain:** Options analysis module for multi-agent LLM trading system
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Summary

TradingAgents is extending its multi-agent stock analysis system to support options trading analysis. The approach follows an established pattern in the codebase: specialized LangGraph agents with focused roles, a vendor-routed data layer, and LLM-driven interpretation of pre-computed quantitative signals. The options module slots in as a parallel agent team alongside the stock analysis team, using Tradier's REST API as the primary data source for options chains, Greeks, and IV, supplemented by the community-maintained tastytrade SDK for real-time streaming when needed.

The recommended stack is deliberately minimal and coherent with existing dependencies. Tradier provides options chains with ORATS-sourced 1st-order Greeks via simple REST calls -- no SDK needed, `requests` is already a project dependency. The `blackscholes` library (actively maintained, v0.2.0 Dec 2024) computes 2nd/3rd-order Greeks that Tradier does not return. GEX and flow detection are custom numpy/pandas computations -- no dedicated library exists and the math is straightforward enough to implement directly. SVI volatility surface fitting uses scipy's optimization routines, already an indirect dependency. The only net-new dependencies are `blackscholes`, `tastytrade` (optional), and optionally `matplotlib` for visualization.

The principal risks are: (1) stale Greeks from Tradier's hourly ORATS refresh causing wrong delta-neutral recommendations; (2) SVI calibration failure on illiquid options producing garbage vol surfaces; (3) GEX sign convention bugs that completely invert market structure analysis; and (4) the LLM hallucinating non-existent option contract symbols. All four have clear, implementation-level mitigations documented in the pitfalls research.

## Key Findings

### Recommended Stack

The core data stack is two vendors: Tradier for REST-based chains, Greeks, and IV (direct `requests` calls, no SDK needed), and tastytrade community SDK for optional real-time streaming via DXLink WebSocket. Tradier's free sandbox makes development straightforward; production requires a brokerage account. The official tastytrade SDK was archived in March 2026, making the `tastyware/tastytrade` community SDK (v12.3.1, 95%+ test coverage, full Pydantic typing) the only viable maintained option. It requires Python >=3.11, so the project's `requires-python` should be bumped from `>=3.10` to `>=3.11`.

All quantitative computation uses libraries already present or easily added: `blackscholes` for 2nd/3rd-order Greeks, `scipy.optimize` for IV solving (Brent's method) and SVI calibration, `scipy.interpolate` for vol surface construction, `numpy` for vectorized GEX computation, and `pandas` for structured output. QuantLib and py_vollib are both explicitly not recommended -- the former is a 200MB over-engineered dependency, the latter is abandoned since 2017.

**Core technologies:**
- **Tradier REST API (requests)**: Options chain data, 1st-order Greeks, IV via ORATS -- free sandbox, fits existing vendor-routing pattern
- **tastyware/tastytrade SDK v12.3.1**: Real-time Greeks streaming via DXLink WebSocket -- only maintained tastytrade SDK after official SDK archived March 2026
- **blackscholes >=0.2.0**: 2nd/3rd-order Greeks (Charm, Vanna, Volga) -- actively maintained Dec 2024, lightweight, no C dependencies
- **scipy (optimize + interpolate)**: IV solving via Brent's method, SVI calibration, vol surface interpolation -- already an indirect dependency
- **numpy >=2.0.0**: Vectorized GEX computation across full options chains -- already an indirect dependency
- **pandas >=2.3.0**: Structured output for chains, GEX tables, flow signals -- core existing dependency

### Expected Features

**Must have (table stakes):**
- Options chain retrieval (strikes, expirations, bid/ask) -- foundation for all other analysis
- 1st-order Greeks display (Delta, Gamma, Theta, Vega) -- every options platform shows these; Tradier returns them via ORATS
- Implied volatility per contract (bid_iv, mid_iv, ask_iv) -- fundamental to options valuation
- IV Rank / IV Percentile -- core metric for sell-vs-buy-premium decisions; requires 52-week IV history
- Options strategy recommendation (verticals, iron condors, straddles) -- the core value proposition
- Max profit/loss and breakeven calculation -- users must understand risk before acting
- DTE-based filtering -- standard 30-60 DTE workflow for income strategies
- Probability of profit (PoP) estimation -- expected by tastytrade-style traders; approximated from delta

**Should have (competitive differentiators):**
- 2nd-order Greeks (Charm, Vanna, Volga) -- institutional-level insight not on retail platforms
- GEX analysis with Call/Put Walls and gamma flip zone -- SpotGamma equivalent ($199+/mo); free is high-value
- Volatility surface construction (SVI fitting) -- quantitative vol skew and term structure analysis
- TastyTrade methodology rules engine (IVR thresholds, 45 DTE entry, 21 DTE management, 50% profit targets)
- Unusual options activity detection -- smart money signal via volume/OI heuristics
- Multi-leg strategy construction with specific named contracts
- MenthorQ-style composite Options Score (0-5) -- single number summarizing the options environment

**Defer (v2+):**
- Real-time streaming dashboard -- batch `propagate()` flow does not support it architecturally
- 0DTE strategy analysis -- requires sub-second data; hourly Greeks are too stale
- Options backtesting engine -- separate domain requiring historical vol surfaces and fill simulation
- Portfolio-level Greeks aggregation -- requires position tracking; analysis-only scope has no position state
- Historical IV surface storage -- requires ORATS subscription or building own historical database

### Architecture Approach

The options module follows all three core patterns already established in the codebase: agent factory closures (each specialist agent created via a `create_*()` closure), vendor-routed data layer (new `get_options_chain()` function routes to Tradier or tastytrade based on config), and computation modules as pure stateless functions that take DataFrames and return DataFrames. The module hierarchy mirrors the existing stock analysis team: a parallel `options_team.py` LangGraph StateGraph with specialist agents consuming a shared options chain DataFrame fetched at the start of the pipeline.

The critical architectural rule from the research: **all math in Python, all interpretation by LLM.** The LLM must never be asked to calculate Greeks, GEX, or IV. A single wrong calculation cascades into bad strategy recommendations. Pre-compute everything numerically, then pass results to the agent for interpretation.

**Major components:**
1. `tradingagents/dataflows/tradier.py` -- Options chain retrieval, expirations, strikes via Tradier REST
2. `tradingagents/options/gex.py` -- GEX computation, Call/Put Walls, gamma flip zone (pure numpy functions)
3. `tradingagents/options/volatility.py` -- IV Rank/Percentile, SVI surface fitting, vol skew metrics
4. `tradingagents/options/greeks.py` -- 2nd/3rd order Greeks via blackscholes library
5. `tradingagents/options/flow.py` -- Volume/OI analysis, unusual activity heuristics
6. `tradingagents/options/strategies.py` -- Multi-leg construction, P/L profiles, PoP estimation
7. `tradingagents/options/scoring.py` -- MenthorQ-style composite Options Score (0-5)
8. `tradingagents/agents/options/` -- Agent factory functions for each options analyst role
9. `tradingagents/graph/options_team.py` -- LangGraph StateGraph composing the full options pipeline

### Critical Pitfalls

1. **Stale Greeks causing wrong directional recommendations** -- Always display the Greeks timestamp from Tradier response; warn in agent output if Greeks are >30 minutes old; compute IV from live bid/ask using scipy rather than relying solely on API-provided IV.
2. **SVI calibration failure on illiquid options** -- Filter strikes to minimum OI >100 and maximum bid-ask spread <30% of mid before calibrating; fall back to linear interpolation when fewer than 5 liquid strikes exist; apply Gatheral's no-butterfly-arbitrage constraints.
3. **GEX sign convention bugs inverting market structure analysis** -- Use a single canonical GEX function with comprehensive unit tests; add sanity check that net GEX is positive at/above spot and negative below for a typical equity.
4. **LLM hallucinating non-existent option contract symbols** -- Strategy agent must select only from contracts present in the actual chain DataFrame returned by Tradier; never let the LLM generate symbols from scratch.
5. **Python version incompatibility with tastytrade SDK** -- Bump `requires-python` to `>=3.11` when adding the options module; numpy/scipy latest versions also dropped 3.10 support.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Data Foundation and Core Analysis Pipeline
**Rationale:** Every feature depends on options chain data. Tradier integration is the prerequisite dependency for the entire module. GEX is the highest-value differentiator and is computationally simple (pure numpy arithmetic) once chain data flows -- there is no reason to defer it.
**Delivers:** Tradier data layer, IV Rank/Percentile, 1st-order Greeks display, GEX with Call/Put Walls and gamma flip zone, basic strategy recommendation agent with max P/L, breakeven, PoP.
**Addresses:** All table stakes features: chain retrieval, 1st-order Greeks, IV, IV Rank, DTE filtering, basic strategy recommendation, PoP estimation.
**Avoids:** GEX sign convention pitfall (unit tests required in this phase before LLM consumes GEX output); stale Greeks pitfall (timestamp display from day one).

### Phase 2: Advanced Analytics and Rules Engine
**Rationale:** With the data layer and basic analysis working, 2nd-order Greeks and the SVI vol surface add institutional depth. The TastyTrade rules engine requires IV Rank (Phase 1 output) as its primary input. Unusual flow detection is feasible with volume/OI heuristics despite Tradier's lack of trade-level data.
**Delivers:** 2nd/3rd-order Greeks (Charm, Vanna, Volga), volatility surface (SVI fitting), TastyTrade methodology rules engine with IVR thresholds and DTE management, unusual activity detection, specific multi-leg contract construction.
**Uses:** blackscholes >=0.2.0, scipy SVI calibration (SLSQP with no-arbitrage constraints), pandas flow heuristics.
**Implements:** `tradingagents/options/greeks.py`, `tradingagents/options/volatility.py`, `tradingagents/options/flow.py`.
**Avoids:** SVI calibration failure pitfall (liquidity filters and fallback to interpolation required here); IV Rank window ambiguity (explicit 252-day rolling definition in code and agent prompts).

### Phase 3: Composite Scoring, Debate, and Full Pipeline Integration
**Rationale:** The composite Options Score (0-5) and the Options Debate/Portfolio Manager require all analysis components as stable inputs. This phase assembles the full LangGraph StateGraph connecting all agents, adds the debate round, and produces the final portfolio manager recommendation with specific named contracts.
**Delivers:** MenthorQ-style composite Options Score synthesizing IV rank, GEX regime, flow signals, and vol skew; full Options Debate (bull vs bear on options thesis); Options Portfolio Manager producing final recommendations.
**Implements:** `tradingagents/options/scoring.py`, `tradingagents/agents/options/` full team, `tradingagents/graph/options_team.py` complete StateGraph.

### Phase 4: Streaming Enhancement and Multi-Ticker Scaling
**Rationale:** tastytrade DXLink streaming is an enhancement for sub-minute data freshness, not a core requirement for the batch `propagate()` flow. Multi-ticker support and Tradier rate limit management should only be tackled after the single-ticker pipeline is proven correct.
**Delivers:** tastytrade DXLink WebSocket integration, API rate limit management (exponential backoff, caching, 4-nearest-expirations optimization), multi-ticker batch analysis support.
**Avoids:** Premature optimization and synchronous WebSocket overhead pitfall (streaming only for persistent sessions, not per-call).

### Phase Ordering Rationale

- **Data before analysis:** Tradier integration is the prerequisite dependency for every other component. No agent can run without the chain DataFrame.
- **High-value, low-complexity first:** GEX computation is pure numpy arithmetic but delivers SpotGamma-level analysis ($199+/mo equivalent). Front-loading it in Phase 1 ensures differentiated value from the first working release.
- **SVI deferred to Phase 2:** SVI calibration has the highest implementation risk (convergence failures, illiquid edge cases). Deferring it avoids blocking the Phase 1 pipeline on the hardest numerical problem.
- **Composite scoring last among core features:** The Options Score is a synthesis of all other signals. Building it before the underlying signals are stable produces a meaningless number.
- **This ordering avoids the primary pitfalls:** GEX sign bugs are caught in Phase 1 unit tests before the LLM consumes the output; SVI failure modes are isolated to Phase 2 with explicit fallbacks; LLM contract hallucination is prevented in Phase 3 by constraining selection to the chain DataFrame.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (SVI calibration):** The Gatheral no-butterfly-arbitrage constraint implementation is non-trivial. Needs deeper research into exact scipy SLSQP constraint formulation and parameter bounds before implementation begins.
- **Phase 2 (flow detection heuristics):** True sweep/block detection is not possible with Tradier's data. The exact volume/OI thresholds and their false-positive rates on real data need validation -- may require empirical tuning during implementation.
- **Phase 3 (options debate agent design):** The debate agent pattern exists for stock analysis but options-specific bull/bear framing (IV environment, not just price direction) is novel and will likely need prompt iteration.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Tradier API integration):** REST API with official docs, straightforward vendor-pattern integration following existing `y_finance.py` and `alpha_vantage.py` models.
- **Phase 1 (GEX computation):** SpotGamma formula is published, numpy implementation is arithmetic, unit tests are sufficient validation.
- **Phase 2 (blackscholes integration):** Actively maintained library with clear API; standard function calls with no architectural complexity.
- **Phase 4 (LangGraph StateGraph):** Existing pattern in `tradingagents/graph/`; follow existing `trading_graph.py` structure.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core recommendations (Tradier, blackscholes, scipy, numpy) verified against official docs and PyPI; tastytrade SDK archival confirmed; py_vollib abandonment confirmed with 2017 last release date |
| Features | HIGH | Feature set derived from established methodologies (SpotGamma, TastyTrade) with documented formulas; anti-features clearly scoped with rationale |
| Architecture | HIGH | Options module mirrors existing codebase patterns directly; LangGraph StateGraph pattern is well-established in the project |
| Pitfalls | MEDIUM | GEX sign convention and SVI failure modes are from documented technical sources; LLM hallucination risk is inferred from general LLM behavior; flow detection limitations are well-understood data availability constraints |

**Overall confidence:** HIGH

### Gaps to Address

- **Historical IV data endpoint:** IV Rank requires 52-week historical IV. Tradier provides historical options data but the exact endpoint and data quality for building a consistent IV history need validation before Phase 1 planning finalizes the approach. Fallback: compute historical IV from underlying historical price data using yfinance (already a dependency).
- **Tradier sandbox vs production fidelity:** The sandbox uses delayed/simulated data. ORATS Greeks quality differences between sandbox and production should be documented during Phase 1 implementation to prevent surprises at launch.
- **SVI no-arbitrage constraint implementation:** Gatheral's conditions are referenced but the exact scipy parameter bounds and constraint functions for SLSQP need to be worked out during Phase 2 planning -- this is a known implementation complexity, not a blocker.
- **Multi-expiration GEX weighting:** SpotGamma's exact weighting methodology across expirations is proprietary. The 4-nearest-expirations approach is documented; the optimal weighting scheme needs empirical validation during Phase 1.
- **Trade-level flow data:** Tradier does not provide individual fills or exchange sweep data. The "unusual activity detection" feature must be scoped as volume/OI heuristics and this limitation must be surfaced explicitly in agent output rather than marketed as sweep detection.

## Sources

### Primary (HIGH confidence)
- [Tradier Options Chain API docs](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains) -- chain endpoints, Greeks fields, rate limits
- [tastyware/tastytrade SDK v12.3.1](https://github.com/tastyware/tastytrade) -- DXLink streaming, Python version requirements, test coverage
- [tastytrade-sdk-python archived March 2026](https://github.com/tastytrade/tastytrade-sdk-python) -- archival confirmed
- [blackscholes v0.2.0](https://github.com/CarloLepelaars/blackscholes) -- Greek coverage, maintenance status, Python version support
- [py_vollib v1.0.1 on PyPI](https://pypi.org/project/py_vollib/) -- last released 2017, confirmed abandoned
- [NumPy 2.x release notes](https://numpy.org/news/) -- version compatibility
- [SciPy 1.14+ release notes](https://docs.scipy.org/doc/scipy/release.html) -- optimize and interpolate API

### Secondary (MEDIUM confidence)
- [SpotGamma GEX methodology](https://spotgamma.com/gamma-exposure-gex/) -- GEX formula, sign conventions, wall/flip zone definitions
- [Gatheral SVI arbitrage-free conditions](https://mfe.baruch.cuny.edu/wp-content/uploads/2013/01/OsakaSVI2012.pdf) -- SVI no-butterfly-arbitrage constraints
- [TastyTrade methodology](https://developer.tastytrade.com/) -- IVR thresholds, DTE management rules, PoP approximation from delta
- [SVI vs SABR comparison (2025 thesis, UPF)](https://repositori.upf.edu/items/eceeb187-f169-483e-bf67-416fd9e00d70) -- model choice rationale for equity options
- [Unusual options activity heuristics](https://intrinio.com/blog/how-to-read-unusual-options-activity-7-easy-steps) -- volume/OI ratio thresholds

### Tertiary (LOW confidence)
- [Python vol surface modeling blog post](https://tradingtechai.medium.com/python-volatility-surface-modeling-data-fetching-iv-calculation-svi-fitting-and-visualization-80be58328ac6) -- SVI fitting implementation example; methodology is standard even if source is a blog

---
*Research completed: 2026-03-29*
*Ready for roadmap: yes*
