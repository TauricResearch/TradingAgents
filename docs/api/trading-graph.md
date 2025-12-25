# TradingGraph API Reference

The `TradingAgentsGraph` class is the main entry point for the TradingAgents framework. It orchestrates all agents, manages state, and coordinates the analysis workflow.

## Class: TradingAgentsGraph

Location: `tradingagents/graph/trading_graph.py`

### Constructor

```python
TradingAgentsGraph(
    selected_analysts: List[str] = ["market", "social", "news", "fundamentals"],
    debug: bool = False,
    config: Dict[str, Any] = None
)
```

#### Parameters

- **selected_analysts** (List[str], optional): List of analyst types to include in analysis
  - Default: `["market", "social", "news", "fundamentals"]`
  - Available: `"market"`, `"social"`, `"news"`, `"fundamentals"`
  - Example: `["market", "fundamentals"]` for technical and fundamental analysis only

- **debug** (bool, optional): Enable debug mode with verbose logging
  - Default: `False`
  - When `True`: Prints detailed execution traces and intermediate states

- **config** (Dict[str, Any], optional): Configuration dictionary
  - Default: `None` (uses `DEFAULT_CONFIG`)
  - See [Configuration Reference](../guides/configuration.md) for all options

#### Returns

- Instance of `TradingAgentsGraph`

#### Example

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Basic initialization
ta = TradingAgentsGraph()

# With custom analysts
ta = TradingAgentsGraph(
    selected_analysts=["market", "fundamentals"],
    debug=True
)

# With custom configuration
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-sonnet-4-20250514"

ta = TradingAgentsGraph(config=config)
```

### Methods

#### propagate()

Run the complete trading analysis workflow for a company on a specific date.

```python
propagate(
    company_name: str,
    trade_date: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]
```

##### Parameters

- **company_name** (str): Ticker symbol of the company to analyze
  - Example: `"NVDA"`, `"AAPL"`, `"TSLA"`
  - Must be a valid US stock ticker

- **trade_date** (str): Date for analysis in YYYY-MM-DD format
  - Example: `"2024-05-10"`
  - Must be a valid trading day (not weekend or holiday)

##### Returns

Tuple of two dictionaries:

1. **Final State** (Dict[str, Any]): Complete agent state after analysis
   - Contains all analyst reports, debate outcomes, risk assessments
   - Useful for debugging and detailed inspection

2. **Trading Decision** (Dict[str, Any]): The final trading recommendation
   - `action`: `"BUY"`, `"SELL"`, or `"HOLD"`
   - `confidence_score`: Float between 0.0 and 1.0
   - `reasoning`: Detailed explanation of the decision
   - `position_size`: Recommended position size (if applicable)
   - `risk_assessment`: Risk evaluation summary

##### Example

```python
ta = TradingAgentsGraph(debug=True)

# Run analysis
final_state, decision = ta.propagate("NVDA", "2024-05-10")

# Access decision
print(f"Action: {decision['action']}")
print(f"Confidence: {decision['confidence_score']:.2%}")
print(f"Reasoning: {decision['reasoning']}")

# Access detailed state
print(f"Analyst Reports: {final_state['analyst_reports']}")
print(f"Research Synthesis: {final_state['research_synthesis']}")
```

##### Raises

- **ValueError**: Invalid ticker or date format
- **LLMRateLimitError**: LLM API rate limit exceeded
- **DataUnavailableError**: Required data not available for the ticker/date
- **APIError**: Generic API error from LLM or data provider

## Configuration

### Default Configuration

The default configuration is defined in `tradingagents/default_config.py`:

```python
DEFAULT_CONFIG = {
    # Directories
    "project_dir": "<auto-detected>",
    "results_dir": "./results",
    "data_cache_dir": "./dataflows/data_cache",

    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",

    # Workflow settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,

    # Data vendors
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage"
    }
}
```

### Customizing Configuration

```python
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()

# Change LLM provider
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-sonnet-4-20250514"

# Increase debate rounds
config["max_debate_rounds"] = 2

# Change data vendors
config["data_vendors"]["news_data"] = "google"

# Initialize with custom config
ta = TradingAgentsGraph(config=config)
```

## Workflow Stages

The `propagate()` method executes these stages:

### 1. Data Collection

All selected analysts collect relevant data in parallel:

- **Market Analyst**: Stock prices, technical indicators
- **Fundamentals Analyst**: Financial statements, ratios
- **Sentiment Analyst**: Social media sentiment
- **News Analyst**: News articles, events

### 2. Analyst Reports

Each analyst generates a specialized report:

```python
state.analyst_reports = {
    "market": "Technical analysis shows bullish MACD crossover...",
    "fundamentals": "Strong balance sheet with P/E ratio of 35...",
    "sentiment": "Positive social sentiment with score 0.75...",
    "news": "Recent product launch expected to boost revenue..."
}
```

### 3. Research Debate

Bull and Bear researchers debate the analyst findings:

```python
# Round 1
bull_researcher: "Strong fundamentals support upside potential..."
bear_researcher: "High valuation creates downside risk..."

# Round 2 (if configured)
bull_researcher: "Growth prospects justify premium valuation..."
bear_researcher: "Market volatility increases uncertainty..."

# Synthesis
research_manager: "Balanced view: Bullish bias with risk management..."
```

### 4. Trading Decision

Trader agent synthesizes all inputs and makes a decision:

```python
decision = {
    "action": "BUY",
    "confidence_score": 0.75,
    "reasoning": "Strong fundamentals and positive momentum outweigh valuation concerns...",
    "position_size": 0.05  # 5% of portfolio
}
```

### 5. Risk Validation

Risk management team evaluates the proposal:

```python
risk_assessment = {
    "approved": True,
    "risk_score": 0.3,  # Low to medium risk
    "recommendations": [
        "Set stop-loss at -5%",
        "Monitor volatility",
        "Review position after earnings"
    ]
}
```

### 6. Final Decision

Portfolio manager approves or rejects:

```python
final_decision = {
    "approved": True,
    "action": "BUY",
    "confidence_score": 0.75,
    "execution_details": {
        "position_size": 0.05,
        "stop_loss": -0.05,
        "take_profit": 0.15
    }
}
```

## State Management

The graph maintains state through the `AgentState` class:

```python
@dataclass
class AgentState:
    ticker: str
    date: str
    analyst_reports: Dict[str, str]
    research_synthesis: str
    trading_decision: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    final_decision: Dict[str, Any]
```

Location: `tradingagents/agents/utils/agent_states.py`

## Memory System

The graph uses `FinancialSituationMemory` for context retention:

```python
from tradingagents.agents.utils.memory import FinancialSituationMemory

memory = FinancialSituationMemory(
    persist_directory="./memory_cache"
)

# Store analysis
memory.add_situation(
    ticker="NVDA",
    date="2024-05-10",
    analysis=state
)

# Retrieve similar past analyses
similar = memory.search_similar(
    query="NVDA technical analysis",
    k=5
)
```

## Error Handling

### Handling Rate Limits

```python
from tradingagents.utils.exceptions import LLMRateLimitError
import time

def run_with_retry(ta, ticker, date, max_retries=3):
    for attempt in range(max_retries):
        try:
            return ta.propagate(ticker, date)
        except LLMRateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = e.retry_after or 60
                print(f"Rate limit hit. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
```

### Handling Missing Data

```python
from tradingagents.utils.exceptions import DataUnavailableError

try:
    state, decision = ta.propagate("INVALID", "2024-05-10")
except DataUnavailableError as e:
    print(f"Data not available: {e}")
    # Fall back to alternative ticker or date
```

## Performance Considerations

### Execution Time

Typical execution times (single ticker):

- **1 debate round**: 30-60 seconds
- **2 debate rounds**: 60-120 seconds
- **3 debate rounds**: 120-180 seconds

Factors affecting speed:
- Number of selected analysts
- Number of debate rounds
- LLM provider and model choice
- Data vendor API latency

### Cost Optimization

Estimated costs per analysis:

| Configuration | LLM Calls | Cost (USD) |
|---------------|-----------|------------|
| Minimal (1 round, 2 analysts) | ~10-15 | $0.05-0.10 |
| Standard (1 round, 4 analysts) | ~20-25 | $0.10-0.20 |
| Deep (2 rounds, 4 analysts) | ~35-45 | $0.20-0.40 |

Cost reduction strategies:
- Use `gpt-4o-mini` instead of `o4-mini` for testing
- Reduce debate rounds
- Select only necessary analysts
- Enable caching

### Parallel Execution

Analyze multiple tickers in parallel:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

tickers = ["NVDA", "AAPL", "MSFT", "TSLA"]
date = "2024-05-10"

def analyze_ticker(ticker):
    ta = TradingAgentsGraph()
    return ta.propagate(ticker, date)

with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(analyze_ticker, tickers))
```

## Examples

### Basic Usage

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

ta = TradingAgentsGraph(debug=True)
state, decision = ta.propagate("NVDA", "2024-05-10")

print(f"Decision: {decision['action']}")
print(f"Confidence: {decision['confidence_score']:.2%}")
```

### Custom Analysts

```python
# Only technical and fundamental analysis
ta = TradingAgentsGraph(
    selected_analysts=["market", "fundamentals"],
    debug=True
)

state, decision = ta.propagate("AAPL", "2024-05-10")
```

### Multiple LLM Providers

```python
# Use different models for deep vs. quick thinking
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"
config["quick_think_llm"] = "openai/gpt-4o-mini"

ta = TradingAgentsGraph(config=config)
state, decision = ta.propagate("TSLA", "2024-05-10")
```

### Batch Analysis

```python
tickers = ["NVDA", "AAPL", "MSFT"]
date = "2024-05-10"

results = {}
ta = TradingAgentsGraph()

for ticker in tickers:
    state, decision = ta.propagate(ticker, date)
    results[ticker] = decision

# Compare decisions
for ticker, decision in results.items():
    print(f"{ticker}: {decision['action']} ({decision['confidence_score']:.2%})")
```

## See Also

- [Multi-Agent System Architecture](../architecture/multi-agent-system.md)
- [Agents API Reference](agents.md)
- [Configuration Guide](../guides/configuration.md)
- [Adding New Analyst](../guides/adding-new-analyst.md)
