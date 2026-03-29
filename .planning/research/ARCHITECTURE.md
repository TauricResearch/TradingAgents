# Architecture Patterns

**Domain:** Options trading analysis module for multi-agent AI trading system
**Researched:** 2026-03-29

## Recommended Architecture

The options module plugs into the existing TradingAgents architecture as a **parallel agent team** alongside the stock analysis team. It follows the same patterns: agent factory closures, LangGraph StateGraph, vendor-routed data layer.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `tradingagents/dataflows/tradier.py` | Options chain retrieval, expirations, strikes via Tradier REST API | Agent tools, config |
| `tradingagents/dataflows/tastytrade.py` | Real-time Greeks streaming via DXLink WebSocket (optional) | Agent tools, config |
| `tradingagents/options/greeks.py` | 2nd/3rd order Greeks calculation (Charm, Vanna, Volga) from 1st-order + spot | Greeks analysis agent |
| `tradingagents/options/volatility.py` | IV Rank, IV Percentile, SVI surface fitting, vol skew metrics | Volatility analysis agent |
| `tradingagents/options/gex.py` | GEX computation, Call/Put Walls, gamma flip zone, Vanna/Charm exposure | GEX analysis agent |
| `tradingagents/options/flow.py` | Volume/OI analysis, unusual activity detection heuristics | Flow analysis agent |
| `tradingagents/options/strategies.py` | Multi-leg strategy construction, P/L profiles, PoP estimation | Strategy selection agent |
| `tradingagents/options/scoring.py` | MenthorQ-style composite Options Score (0-5) | Options portfolio manager |
| `tradingagents/agents/options/` | Agent factory functions for each options analyst role | LangGraph StateGraph |
| `tradingagents/graph/options_team.py` | LangGraph StateGraph for the options analysis pipeline | Main graph (parallel branch) |

### Data Flow

```
User input (ticker, date range)
    |
    v
[Tradier API] --> options chain DataFrame (strikes, bids, asks, Greeks, IV, OI)
    |
    +---> [Volatility Agent] --> IV Rank, IV Percentile, vol skew, SVI surface
    |
    +---> [Greeks Agent] --> 2nd-order Greeks (Charm, Vanna, Volga) per strike
    |
    +---> [GEX Agent] --> Net GEX, Call/Put Walls, gamma flip zone, regime
    |
    +---> [Flow Agent] --> Unusual activity signals, volume/OI anomalies
    |
    v
[Strategy Selection Agent] <-- all analysis outputs
    |
    v
[Options Debate] (bull vs bear on options thesis, configurable rounds)
    |
    v
[Options Portfolio Manager] --> final recommendation
    |
    v
Output: specific contracts + alternative ranges + reasoning chain
```

## Patterns to Follow

### Pattern 1: Agent Factory Closures (existing pattern)

**What:** Each agent is created via a `create_*()` closure that captures LLM client and tools.
**When:** Always -- this is the established pattern in the codebase.
**Example:**
```python
def create_volatility_analyst(llm_client, tools):
    """Create volatility analysis agent with options-specific tools."""
    system_prompt = VOLATILITY_ANALYST_PROMPT

    def volatility_analyst(state):
        if "options_chain" not in state or "ticker" not in state:
            return {"volatility_analysis_error": "missing options_chain or ticker in state"}
        if "compute_iv_rank" not in tools:
            return {"volatility_analysis_error": "compute_iv_rank tool not registered"}
        chain_data = state["options_chain"]
        ticker = state["ticker"]
        try:
            iv_rank = tools["compute_iv_rank"](chain_data, ticker)
        except Exception as e:
            return {"volatility_analysis_error": f"compute_iv_rank failed: {e!s}"}
        try:
            response = llm_client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=format_iv_analysis(iv_rank, chain_data))
            ])
        except Exception as e:
            return {"volatility_analysis_error": f"llm invoke failed: {e!s}"}
        return {"volatility_analysis": response.content}

    return volatility_analyst
```

### Pattern 2: Vendor-Routed Data Layer (existing pattern)

**What:** Data retrieval goes through a routing layer that selects the vendor based on config.
**When:** For all options data retrieval -- Tradier is primary, tastytrade is fallback/supplement.
**Example:**
```python
# In tradingagents/dataflows/config.py (extend existing)
# Add "tradier" to data_vendors options

def get_options_chain(ticker, expiration, config):
    vendor = config.get("options_vendor", "tradier")
    if vendor == "tradier":
        return tradier.get_chain(ticker, expiration)
    elif vendor == "tastytrade":
        return tastytrade.get_chain(ticker, expiration)
    raise ValueError(f"Unsupported options_vendor={vendor!r}; expected 'tradier' or 'tastytrade'")
```

### Pattern 3: Computation Modules as Pure Functions

**What:** GEX, Greeks, vol surface calculations are stateless pure functions that take DataFrames and return DataFrames.
**When:** All options math modules.
**Why:** Testable without LLM calls, cacheable, composable.
```python
# tradingagents/options/gex.py
def compute_gex(chain_df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """Pure function: chain DataFrame in, GEX DataFrame out.
    Standard notional-scaled GEX: gamma * OI * 100 * spot**2 (per-share gamma → contract multiplier 100).
    """
    chain_df["call_gex"] = chain_df["gamma"] * chain_df["open_interest"] * 100 * spot**2
    chain_df["put_gex"] = -chain_df["gamma"] * chain_df["open_interest"] * 100 * spot**2
    # ... aggregate, find walls, flip zone
    return gex_df
```

### Pattern 4: 5-Tier Rating Scale (existing pattern)

**What:** All analysis outputs use BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL scale.
**When:** Options agents should output ratings consistent with existing stock analysts.
**Adaptation:** Options-specific interpretation:
- BUY = strong bullish options position recommended (long calls, bull spreads)
- OVERWEIGHT = moderately bullish (covered calls, bull put spreads)
- HOLD = neutral strategies (iron condors, straddles if high IV)
- UNDERWEIGHT = moderately bearish (bear call spreads, protective puts)
- SELL = strong bearish (long puts, bear spreads)

## Anti-Patterns to Avoid

### Anti-Pattern 1: Monolithic Options Agent

**What:** Single agent that does all options analysis (Greeks + GEX + flow + strategy).
**Why bad:** Unmanageable prompts, impossible to debug, cannot run analyses in parallel.
**Instead:** Separate specialized agents with focused prompts, composed via LangGraph.

### Anti-Pattern 2: LLM Doing Math

**What:** Asking the LLM to calculate Greeks, GEX, or IV metrics.
**Why bad:** LLMs are unreliable at arithmetic. A single wrong calculation cascades into bad recommendations.
**Instead:** All math in Python (blackscholes, numpy, scipy). LLM only interprets pre-computed results.

### Anti-Pattern 3: Hardcoded Strike Selection

**What:** Agent tools that select specific strikes based on rigid rules (e.g., "always pick ATM +/- 2 strikes").
**Why bad:** Different strategies need different strike selection logic. Iron condor wings vs vertical spread width depend on IV, premium targets, and risk tolerance.
**Instead:** Provide the LLM agent with a range of strikes and their computed metrics; let it reason about selection within the strategy context.

### Anti-Pattern 4: Synchronous Tastytrade Streaming in Batch Flow

**What:** Starting a DXLink WebSocket connection for every `propagate()` call.
**Why bad:** WebSocket setup overhead (auth, handshake, subscription) for a single snapshot is wasteful. Adds 2-5 seconds per call.
**Instead:** Use Tradier REST for batch flow. Only use tastytrade streaming if building a persistent session or needing sub-minute freshness.

## Scalability Considerations

| Concern | Current (single ticker) | Multi-ticker (10 tickers) | High volume (50+ tickers) |
|---------|------------------------|--------------------------|---------------------------|
| API rate limits | Tradier: ~2 req/ticker (chain + expirations), well within 120 req/min | 20 requests, still fine | 100+ requests, need queuing/throttling |
| Chain data size | ~200 strikes per expiry, 5-8 expiries = 1000-1600 rows | 10x = 10-16K rows, fine in memory | 50x = manageable but cache aggressively |
| GEX computation | Sub-second numpy vectorization | Still sub-second | Still sub-second; numpy handles millions of rows |
| LLM calls per analysis | **~6 + Ndebate** — Volatility, Greeks, GEX, Flow (4 analysis) + Strategy selection + Portfolio manager + **Options debate × rounds (N)** | Scales with debate rounds; 60+ calls multi-ticker | Batch where safe; parallelize independent agents; cap `max_debate_rounds` |
| Tastytrade WebSocket | Single subscription, minimal overhead | 10 subscriptions, fine | May hit subscription limits |

## Operational Concerns

- **Errors / retries:** Vendor routers (`get_options_chain`, `route_to_vendor`) should map HTTP/rate-limit failures to typed errors, retry with backoff where safe, and return actionable messages to agents (see REL-01/REL-02 in REQUIREMENTS.md).
- **Testing:** Prefer pure-function unit tests for `tradingagents/options/gex.py`, `greeks.py`, vol math; mock LLMs and external HTTP; integration tests for `options_team` / LangGraph wiring.
- **Observability:** LangGraph flows (`tradingagents/graph/options_team.py` when added) should emit structured step logs (node name, duration, tool calls) — align with OBS-01.
- **Cost:** Batch or cache LLM calls; avoid redundant chain fetches across nodes (session cache).
- **Security:** API keys via env only; rotate keys; least-privilege broker API tokens. Deep-dive docs TBD per subsystem.

## Sources

- Existing codebase patterns in `tradingagents/agents/`, `tradingagents/graph/`, `tradingagents/dataflows/`
- [LangGraph StateGraph documentation](https://langchain-ai.github.io/langgraph/)
- [Tradier API rate limits](https://docs.tradier.com/)
