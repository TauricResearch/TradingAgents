# Agents API Reference

This document provides API reference for all agent types in the TradingAgents framework.

## Agent Types

All agents are located in `tradingagents/agents/`

### Analyst Agents

Analysts conduct specialized analysis on market data.

#### Base Analyst Interface

All analysts inherit from a common interface pattern:

```python
class BaseAnalyst:
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools

    def analyze(self, ticker: str, date: str) -> str:
        """Perform analysis and return report."""
        pass
```

#### Market Analyst

**Location**: `tradingagents/agents/analysts/market_analyst.py`

**Purpose**: Technical analysis using price patterns and indicators

**Tools**:
- `get_stock_data()` - Historical prices
- `get_indicators()` - Technical indicators (MACD, RSI, Bollinger Bands)

**Output**: Technical analysis report with trend identification and signals

**Example**:
```python
report = market_analyst.analyze("NVDA", "2024-05-10")
# Returns: "Technical analysis shows bullish MACD crossover..."
```

#### Fundamentals Analyst

**Location**: `tradingagents/agents/analysts/fundamentals_analyst.py`

**Purpose**: Company financial health and valuation analysis

**Tools**:
- `get_fundamentals()` - Financial ratios and metrics
- `get_balance_sheet()` - Balance sheet data
- `get_income_statement()` - Income statement
- `get_cashflow()` - Cash flow statement

**Output**: Financial health assessment and valuation analysis

**Example**:
```python
report = fundamentals_analyst.analyze("NVDA", "2024-05-10")
# Returns: "Strong balance sheet with P/E ratio of 35..."
```

#### Sentiment Analyst

**Location**: `tradingagents/agents/analysts/sentiment_analyst.py`

**Purpose**: Social media and public sentiment analysis

**Tools**:
- Reddit data via PRAW
- Sentiment scoring algorithms

**Output**: Sentiment score and trending topics

**Example**:
```python
report = sentiment_analyst.analyze("NVDA", "2024-05-10")
# Returns: "Positive social sentiment with score 0.75..."
```

#### News Analyst

**Location**: `tradingagents/agents/analysts/news_analyst.py`

**Purpose**: News and macroeconomic event analysis

**Tools**:
- `get_news()` - Company-specific news
- `get_global_news()` - Market-wide news

**Output**: Event impact assessment

**Example**:
```python
report = news_analyst.analyze("NVDA", "2024-05-10")
# Returns: "Recent product launch expected to boost revenue..."
```

### Researcher Agents

Researchers debate analyst findings to evaluate opportunities and risks.

#### Bull Researcher

**Purpose**: Identify bullish opportunities and positive catalysts

**Input**: Analyst reports

**Output**: Bull case arguments with supporting evidence

#### Bear Researcher

**Purpose**: Identify risks and potential downsides

**Input**: Analyst reports

**Output**: Bear case arguments with risk assessments

#### Research Manager

**Purpose**: Moderate debates and synthesize perspectives

**Input**: Bull/bear arguments from debate rounds

**Output**: Balanced research synthesis

### Trader Agent

**Location**: `tradingagents/agents/trader.py`

**Purpose**: Make final trading decisions based on comprehensive analysis

**Input**:
- Analyst reports
- Research synthesis
- Market conditions

**Output**:
```python
{
    "action": "BUY" | "SELL" | "HOLD",
    "confidence_score": 0.0 to 1.0,
    "reasoning": str,
    "position_size": float
}
```

**Example**:
```python
decision = trader.decide(state)
print(decision["action"])  # "BUY"
print(decision["confidence_score"])  # 0.75
```

### Risk Management Agents

#### Risk Analysts

**Purpose**: Assess portfolio risk (volatility, liquidity, correlation)

**Tools**: Risk metrics, scenario analysis

**Output**: Risk assessment with mitigation recommendations

#### Portfolio Manager

**Location**: `tradingagents/agents/portfolio_manager.py`

**Purpose**: Final approval/rejection of trading proposals

**Input**:
- Trading decision
- Risk assessment

**Output**:
```python
{
    "approved": bool,
    "reasoning": str,
    "modifications": dict  # Suggested changes if not approved
}
```

## Agent Tools

Location: `tradingagents/agents/utils/agent_utils.py`

### Data Access Tools

```python
get_stock_data(ticker: str, start_date: str, end_date: str) -> dict
```
Get historical stock prices (OHLCV data)

```python
get_indicators(ticker: str, indicators: List[str]) -> dict
```
Calculate technical indicators. Available: MACD, RSI, BollingerBands, SMA, EMA

```python
get_fundamentals(ticker: str) -> dict
```
Get company fundamental metrics (P/E, P/B, ROE, etc.)

```python
get_balance_sheet(ticker: str) -> dict
```
Get balance sheet data

```python
get_income_statement(ticker: str) -> dict
```
Get income statement

```python
get_cashflow(ticker: str) -> dict
```
Get cash flow statement

```python
get_news(ticker: str, date: str) -> dict
```
Get company-specific news articles

```python
get_global_news(date: str) -> dict
```
Get market-wide news and events

```python
get_insider_sentiment(ticker: str) -> dict
```
Get insider trading sentiment

```python
get_insider_transactions(ticker: str) -> dict
```
Get insider transaction history

## Agent State

Location: `tradingagents/agents/utils/agent_states.py`

### AgentState

Main state object passed through the workflow:

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

### InvestDebateState

State for research debate rounds:

```python
@dataclass
class InvestDebateState:
    bull_arguments: List[str]
    bear_arguments: List[str]
    debate_round: int
    synthesis: str
```

### RiskDebateState

State for risk management discussions:

```python
@dataclass
class RiskDebateState:
    risk_assessments: List[str]
    discussion_round: int
    final_recommendation: str
```

## Memory System

Location: `tradingagents/agents/utils/memory.py`

### FinancialSituationMemory

Vector-based memory for storing and retrieving analysis context:

```python
class FinancialSituationMemory:
    def __init__(self, persist_directory: str = "./memory_cache"):
        """Initialize memory with ChromaDB backend."""

    def add_situation(
        self,
        ticker: str,
        date: str,
        analysis: dict,
        metadata: dict = None
    ):
        """Store an analysis in memory."""

    def search_similar(
        self,
        query: str,
        k: int = 5,
        filter: dict = None
    ) -> List[dict]:
        """Search for similar past analyses."""

    def get_by_ticker(self, ticker: str, limit: int = 10) -> List[dict]:
        """Get all analyses for a specific ticker."""
```

**Example**:
```python
memory = FinancialSituationMemory()

# Store analysis
memory.add_situation(
    ticker="NVDA",
    date="2024-05-10",
    analysis=final_state,
    metadata={"confidence": 0.75}
)

# Retrieve similar analyses
similar = memory.search_similar(
    query="NVDA technical bullish",
    k=5
)
```

## Creating Custom Agents

### Step 1: Define Agent Class

```python
from typing import List

class CustomAnalyst:
    def __init__(self, llm, tools: List):
        self.llm = llm
        self.tools = tools

    def analyze(self, ticker: str, date: str) -> str:
        # Your analysis logic
        data = self.tools["get_stock_data"](ticker, date)
        prompt = f"Analyze {ticker} data: {data}"
        response = self.llm.invoke(prompt)
        return response.content
```

### Step 2: Register Tools

```python
from tradingagents.agents.utils.agent_utils import get_stock_data

tools = {
    "get_stock_data": get_stock_data,
    # Add more tools as needed
}

analyst = CustomAnalyst(llm, tools)
```

### Step 3: Integrate into Graph

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Register custom analyst
ta = TradingAgentsGraph()
ta.add_analyst("custom", custom_analyst)
```

See [Adding New Analyst Guide](../guides/adding-new-analyst.md) for complete details.

## See Also

- [Multi-Agent System Architecture](../architecture/multi-agent-system.md)
- [TradingGraph API](trading-graph.md)
- [Data Flows API](dataflows.md)
- [Adding New Analyst Guide](../guides/adding-new-analyst.md)
