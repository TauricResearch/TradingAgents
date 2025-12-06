# Integrated Agentic Architecture - Implementation Guide

## Overview

The screening and pump detection agents have been fully integrated into your langgraph-based agentic architecture. They now work alongside all existing agents (market analyst, bull/bear researchers, traders, risk managers, etc.) as part of a unified multi-agent system.

## Architecture

### Agent Hierarchy

```
START
  ├─ Screening Agent (Optional)
  │  ├─ Uses: Market Movers, Earnings Calendar, Trending Social, Insider Activity
  │  └─ Output: Stock candidates for deeper analysis
  │
  ├─ Pump Detection Agent (Optional)
  │  ├─ Uses: Volume Spike, Price Acceleration, Social Sentiment, RSI, Catalysts
  │  └─ Output: Pump probability score (0-100)
  │
  ├─ Market Analyst
  │  └─ Technical analysis: RSI, MACD, Moving Averages
  │
  ├─ Social Media Analyst
  │  └─ Sentiment analysis: Reddit, Twitter, StockTwits
  │
  ├─ News Analyst
  │  └─ News sentiment: Recent news, insider activity
  │
  ├─ Fundamentals Analyst
  │  └─ Financial analysis: P/E, Growth, Statements
  │
  ├─ Bull Researcher
  │  └─ Bullish thesis based on all findings
  │
  ├─ Bear Researcher
  │  └─ Bearish thesis based on all findings
  │
  ├─ Research Manager
  │  └─ Synthesizes debate into investment recommendation
  │
  ├─ Trader
  │  └─ Creates trading plan (entry, stop, targets)
  │
  └─ Risk Managers (Risky/Neutral/Safe)
     └─ Final risk-adjusted decision
END
```

## Files Modified

1. **tradingagents/agents/screening_agent.py**
   - Updated to follow langgraph pattern
   - Exports `create_screening_agent()` function
   - Integrates with agent state

2. **tradingagents/agents/pump_detection_agent.py**
   - Updated to follow langgraph pattern
   - Exports `create_pump_detection_agent()` function
   - Integrates with agent state

3. **tradingagents/agents/__init__.py**
   - Added exports for screening and pump detection agents

4. **tradingagents/graph/trading_graph.py**
   - Added pump detection tool imports
   - Added screening and pump detection tool nodes
   - Added `include_screening` parameter
   - Added `include_pump_detection` parameter

5. **tradingagents/graph/setup.py**
   - Updated `setup_graph()` to accept new agent flags
   - Integrated agents into graph flow
   - Added conditional edges for optional agents

## Usage

### Basic Usage - All Agents

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Create graph with ALL agents (screening, pump detection, analysts, researchers, traders)
graph = TradingAgentsGraph(
    selected_analysts=["market", "social", "news", "fundamentals"],
    include_screening=True,
    include_pump_detection=True,
)

# Run analysis
ticker = "NVDA"
trade_date = "2025-12-05"
final_state, signal = graph.propagate(ticker, trade_date)

# Access results
print(f"Pump Report: {final_state.get('pump_report')}")
print(f"Screening Report: {final_state.get('screening_report')}")
print(f"Final Decision: {final_state.get('final_trade_decision')}")
```

### Usage - Pump Detection Only

```python
graph = TradingAgentsGraph(
    include_pump_detection=True,
    # Skip screening, but keep analysis agents
    selected_analysts=["market", "social", "news", "fundamentals"],
)

final_state, signal = graph.propagate("NVDA", "2025-12-05")
```

### Usage - Screening Only

```python
graph = TradingAgentsGraph(
    include_screening=True,
    selected_analysts=["market"],  # Minimal analysis
)

# Get screening recommendations
screening_output = final_state.get('screening_report')
```

### Usage - Original Graph (No Screening/Pump Detection)

```python
graph = TradingAgentsGraph(
    # Defaults: include_screening=False, include_pump_detection=False
    selected_analysts=["market", "social", "news", "fundamentals"],
)

final_state, signal = graph.propagate("NVDA", "2025-12-05")
```

## Agent Descriptions

### Screening Agent
- **Purpose**: Scans the market for interesting stock candidates
- **Tools**: get_market_movers, get_earnings_calendar, get_insider_transactions, get_indicators, get_trending_social
- **Output**: Comma-separated list of recommended tickers
- **When to Use**: First step in market scanning
- **Enabled By**: `include_screening=True`

### Pump Detection Agent
- **Purpose**: Analyzes stocks for pre-pump signals
- **Tools**: detect_volume_spike, detect_price_acceleration, detect_social_sentiment_surge, detect_oversold_bounce, detect_catalyst_event, calculate_pump_score
- **Output**: Pump probability score (0-100) with risk assessment
- **When to Use**: For momentum/swing trading opportunities
- **Enabled By**: `include_pump_detection=True`

### Market Analyst
- **Purpose**: Technical analysis
- **Tools**: get_stock_data, get_indicators
- **Output**: Technical trends and signals

### Social Media Analyst
- **Purpose**: Social sentiment analysis
- **Tools**: get_news (for social mentions)
- **Output**: Sentiment report from social media

### News Analyst
- **Purpose**: News and insider sentiment
- **Tools**: get_news, get_global_news, get_insider_sentiment, get_insider_transactions
- **Output**: News impact and insider activity report

### Fundamentals Analyst
- **Purpose**: Company fundamental analysis
- **Tools**: get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement
- **Output**: Financial health and growth analysis

### Bull Researcher
- **Purpose**: Builds bullish investment case
- **Input**: All analyst reports
- **Output**: Bullish thesis and recommendations

### Bear Researcher
- **Purpose**: Builds bearish investment case
- **Input**: All analyst reports
- **Output**: Bearish thesis and concerns

### Research Manager
- **Purpose**: Synthesizes bull/bear debate
- **Input**: Bull and bear perspectives
- **Output**: Final investment recommendation (BUY/HOLD/SELL)

### Trader
- **Purpose**: Creates trading execution plan
- **Input**: Investment recommendation
- **Output**: Entry price, stop loss, profit targets, position sizing

### Risk Managers
- **Purpose**: Final risk assessment
- **Input**: Trading plan
- **Output**: Risk-adjusted final decision

## State Keys

The unified `AgentState` contains:

```python
{
    "messages": [...],                      # Conversation history
    "company_of_interest": "NVDA",          # Ticker symbol
    "trade_date": "2025-12-05",             # Analysis date
    
    # Optional agent outputs
    "screening_report": "...",              # From Screening Agent
    "pump_report": "...",                   # From Pump Detection Agent
    
    # Analyst outputs
    "market_report": "...",                 # From Market Analyst
    "sentiment_report": "...",              # From Social Analyst
    "news_report": "...",                   # From News Analyst
    "fundamentals_report": "...",           # From Fundamentals Analyst
    
    # Debate and decision
    "investment_debate_state": {...},       # Bull vs Bear debate
    "trader_investment_plan": "...",        # From Trader
    "risk_debate_state": {...},             # Risk assessment
    "final_trade_decision": "...",          # Final recommendation
}
```

## Tool Nodes in Graph

### Tools Available by Node Type

**market_tools**: get_stock_data, get_indicators

**social_tools**: get_news

**news_tools**: get_news, get_global_news, get_insider_sentiment, get_insider_transactions

**fundamentals_tools**: get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement

**screening_tools**: get_market_movers, get_earnings_calendar, get_insider_transactions, get_indicators, get_trending_social

**pump_detection_tools**: detect_volume_spike, detect_price_acceleration, detect_social_sentiment_surge, detect_oversold_bounce, detect_catalyst_event, calculate_pump_score

## Conditional Logic

The graph uses conditional edges to:

1. **Skip screening/pump detection** if not enabled
2. **Route to next agent** after each analysis
3. **Continue debate** between bull/bear researchers
4. **Finalize decision** through risk managers

## Integration Points

### Adding Custom Agents

To add your own agent to the architecture:

1. **Create agent function** in `tradingagents/agents/custom_agent.py`:
```python
def create_custom_agent(llm):
    def custom_agent_node(state):
        # Your agent logic
        return {"messages": state["messages"] + [result]}
    return custom_agent_node
```

2. **Export from `__init__.py`**:
```python
from .custom_agent import create_custom_agent
__all__ = [..., "create_custom_agent"]
```

3. **Add to graph setup**:
```python
graph_setup.setup_graph(
    selected_analysts=["market"],
    include_custom_agent=True,  # Add your flag
)
```

### Adding Custom Tools

To add tools available to all agents:

1. **Create tool** in `tradingagents/agents/utils/`:
```python
@tool
def my_custom_tool(...):
    """Tool description"""
    return result
```

2. **Add to tool node** in `trading_graph.py`:
```python
def _create_tool_nodes(self):
    return {
        "market": ToolNode([get_stock_data, my_custom_tool]),
        ...
    }
```

## Testing

### Run Integrated Demo

```bash
python integrated_agents_demo.py
```

Shows architecture overview and usage examples.

### Run Full Analysis

```bash
from tradingagents.graph.trading_graph import TradingAgentsGraph

graph = TradingAgentsGraph(
    include_screening=True,
    include_pump_detection=True,
    selected_analysts=["market", "social", "news", "fundamentals"],
    debug=True,  # Enable debug mode to see agent thinking
)

final_state, signal = graph.propagate("NVDA", "2025-12-05")
```

## Performance Considerations

1. **Agent Execution Time**: Each agent runs sequentially, adding ~5-30 seconds per agent
2. **Total Time Estimate**:
   - Screening: 10-20 seconds
   - Pump Detection: 10-20 seconds
   - Each Analyst: 10-20 seconds
   - Researchers/Traders: 10-20 seconds
   - **Total**: 1-4 minutes for full analysis

3. **API Calls**: Each agent may call multiple APIs (yfinance, Alpha Vantage, etc.)

4. **Optimization**: Set `debug=False` to skip verbose output

## Troubleshooting

### "Agent not found" Error
- Check agent is exported from `agents/__init__.py`
- Verify parameter name matches (e.g., `include_pump_detection`)

### Missing Tool Error
- Ensure tool node is created in `_create_tool_nodes()`
- Verify tool is imported at top of file

### State Key Error
- Agent results are stored with specific keys (e.g., `pump_report`)
- Check key name matches agent output

### API Errors
- Ensure API keys are set (Alpha Vantage, etc.)
- Fall back to yfinance (free, no key needed)
- Check internet connection

## Best Practices

1. **Start Simple**: Enable one agent at a time to debug
2. **Use Debug Mode**: Set `debug=True` to see agent reasoning
3. **Monitor Performance**: Track execution time, adjust as needed
4. **Validate Results**: Check outputs make sense before trading
5. **Combine Signals**: Use multiple agent perspectives for better decisions
6. **Document Decisions**: Log final recommendations for analysis

## Summary

You now have a fully integrated multi-agent system where:

✅ **Screening Agent** finds opportunities market-wide
✅ **Pump Detection Agent** spots pre-pump signals
✅ **Analysis Agents** provide technical, social, news, fundamental insights
✅ **Research Agents** debate bull vs bear perspectives
✅ **Trading Agent** creates execution plans
✅ **Risk Managers** ensure proper risk management
✅ **All agents share state** and build on each other's analysis
✅ **Flexible architecture** lets you enable/disable agents as needed

This creates a sophisticated multi-perspective trading analysis system that combines:
- Market screening
- Momentum detection
- Technical analysis
- Social sentiment
- News analysis
- Fundamentals
- Debate and consensus
- Risk management

All working together in a unified langgraph-based agentic framework!
