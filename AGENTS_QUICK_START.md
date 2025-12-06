# Integrated Agents - Quick Start

## What Changed

✅ **Screening Agent** - Now a langgraph agent, part of the unified system
✅ **Pump Detection Agent** - Now a langgraph agent, part of the unified system
✅ Both agents work together with existing analysts and researchers
✅ Flexible enabling/disabling via parameters

## Quick Usage

### Minimal Example (1 Stock)
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Create graph
graph = TradingAgentsGraph(
    include_pump_detection=True,  # Enable pump detection
    selected_analysts=["market"],  # Just market analyst
)

# Analyze one stock
final_state, signal = graph.propagate("NVDA", "2025-12-05")

# Get results
print(final_state.get("pump_report"))  # Pump analysis
print(final_state.get("market_report"))  # Technical analysis
```

### Full Analysis (All Agents)
```python
graph = TradingAgentsGraph(
    include_screening=True,           # Find candidates
    include_pump_detection=True,       # Detect pumps
    selected_analysts=[
        "market",
        "social", 
        "news",
        "fundamentals"
    ],
)

final_state, signal = graph.propagate("NVDA", "2025-12-05")
```

### Just Screening
```python
graph = TradingAgentsGraph(
    include_screening=True,
    selected_analysts=["market"],
)

# Get screening recommendations
final_state, signal = graph.propagate("NVDA", "2025-12-05")
print(final_state.get("screening_report"))
```

## Key Agents

| Agent | Purpose | Key Tools | Output |
|-------|---------|-----------|--------|
| **Screening** | Find candidates | Market movers, trending, earnings | Ticker list |
| **Pump Detection** | Detect pre-pumps | Volume, price, social, RSI, catalyst | Pump score 0-100 |
| **Market** | Technical analysis | RSI, MACD, moving averages | Technical trends |
| **Social** | Sentiment | Social media mentions | Sentiment report |
| **News** | News sentiment | News, insider activity | News impact |
| **Fundamentals** | Financial analysis | P/E, growth, statements | Financial health |
| **Bull/Bear** | Debate | Analysis synthesis | Perspectives |
| **Research Manager** | Synthesize | Bull/bear debate | Investment decision |
| **Trader** | Trade plan | Decision | Entry/stop/target |
| **Risk** | Risk assess | Trade plan | Final decision |

## State Keys

```python
{
    # Inputs
    "company_of_interest": "NVDA",
    "trade_date": "2025-12-05",
    
    # Optional outputs
    "screening_report": "...",           # If include_screening=True
    "pump_report": "...",                # If include_pump_detection=True
    "market_report": "...",              # If "market" in selected_analysts
    "sentiment_report": "...",           # If "social" in selected_analysts
    "news_report": "...",                # If "news" in selected_analysts
    "fundamentals_report": "...",        # If "fundamentals" in selected_analysts
    
    # Always present
    "final_trade_decision": "BUY/HOLD/SELL",
    "trader_investment_plan": "Entry: $100, Stop: $97, Target: $105",
}
```

## Parameters

```python
TradingAgentsGraph(
    selected_analysts=["market", "social", "news", "fundamentals"],  # Which analysts to use
    debug=False,                  # Show detailed agent reasoning
    config=None,                  # Custom config dict
    include_screening=False,      # Enable screening agent
    include_pump_detection=False, # Enable pump detection agent
)
```

## Execution Flow

```
START
  │
  ├─ Screening Agent (if enabled)
  │   └─ Returns: Candidate stocks
  │
  ├─ Pump Detection Agent (if enabled)
  │   └─ Returns: Pump score 0-100
  │
  ├─ Analysts (market, social, news, fundamentals)
  │   ├─ Market Analyst → technical trends
  │   ├─ Social Analyst → sentiment
  │   ├─ News Analyst → news impact
  │   └─ Fundamentals Analyst → financial health
  │
  ├─ Researchers (Bull + Bear)
  │   ├─ Bull Researcher → bullish case
  │   └─ Bear Researcher → bearish case
  │
  ├─ Research Manager
  │   └─ Synthesizes → Investment decision
  │
  ├─ Trader
  │   └─ Creates → Trading plan
  │
  ├─ Risk Managers (Risky, Neutral, Safe)
  │   └─ Final risk → Assessment
  │
  └─ END (returns final_trade_decision)
```

## Common Use Cases

### Case 1: Find and Analyze Pump Candidates
```python
graph = TradingAgentsGraph(
    include_screening=True,
    include_pump_detection=True,
)
# Screening finds candidates, pump detection scores them
```

### Case 2: Quick Technical Analysis
```python
graph = TradingAgentsGraph(
    selected_analysts=["market"],
)
# Fast technical analysis only
```

### Case 3: Deep Fundamental Research
```python
graph = TradingAgentsGraph(
    selected_analysts=["fundamentals", "news", "market"],
)
# Focus on fundamentals with supporting analysis
```

### Case 4: Full Due Diligence
```python
graph = TradingAgentsGraph(
    include_screening=True,
    include_pump_detection=True,
    selected_analysts=["market", "social", "news", "fundamentals"],
)
# Complete analysis: screening → detection → analysis → decision
```

## Files to Know

- `tradingagents/agents/screening_agent.py` - Screening agent
- `tradingagents/agents/pump_detection_agent.py` - Pump detection agent
- `tradingagents/graph/trading_graph.py` - Main graph orchestrator
- `tradingagents/graph/setup.py` - Graph setup and flow
- `INTEGRATION_GUIDE.md` - Full integration documentation
- `PUMP_DETECTION_GUIDE.md` - Pump detection details
- `integrated_agents_demo.py` - Architecture demo

## Troubleshooting

**"ModuleNotFoundError"** - Ensure agents are imported in `__init__.py`

**"Node not found"** - Check `setup_graph()` includes the agent

**"Tool not found"** - Verify tool is added to tool node

**Slow execution** - Normal: ~30sec-2min total, disable debug mode

**API errors** - Use yfinance (free) instead of Alpha Vantage

## Next Steps

1. Read `INTEGRATION_GUIDE.md` for full details
2. Run `python integrated_agents_demo.py` to see architecture
3. Start with one agent, add more as needed
4. Customize agents for your trading strategy

Happy trading! 🚀
