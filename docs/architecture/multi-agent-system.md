# Multi-Agent System Architecture

TradingAgents implements a multi-agent architecture that mirrors real-world trading firms, where specialized teams collaborate to make informed investment decisions.

## System Overview

The framework decomposes complex trading analysis into specialized agent roles, each with specific responsibilities and expertise. Agents collaborate through structured workflows orchestrated by LangGraph.

```
┌─────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                 │
├─────────────────────────────────────────────────────────────────────┤
│  yfinance │ Alpha Vantage │ FRED (NEW) │ Alpaca │ Multi-Timeframe  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ANALYSIS LAYER                               │
├─────────────────────────────────────────────────────────────────────┤
│  Market  │ Momentum │  Macro   │ Correlation │ News │ Fundamentals │
│ Analyst  │ Analyst  │ Analyst  │   Analyst   │      │              │
│          │  (NEW)   │  (NEW)   │    (NEW)    │      │              │
├─────────────────────────────────────────────────────────────────────┤
│              Bull ←── Debate ──→ Bear → Research Manager            │
├─────────────────────────────────────────────────────────────────────┤
│              Trader → Signal + Confidence Score                     │
├─────────────────────────────────────────────────────────────────────┤
│         Risk Debate → Position Sizing Manager (NEW)                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Agent Roles

### Analyst Team

The analyst team conducts specialized analysis, each agent focusing on a specific domain:

#### Market Analyst (Technical)
- **Responsibility**: Technical analysis using price patterns and indicators
- **Tools**: MACD, RSI, Bollinger Bands, moving averages
- **Output**: Technical trends, support/resistance levels, momentum signals
- **Location**: `tradingagents/agents/analysts/market_analyst.py`

#### Fundamentals Analyst
- **Responsibility**: Company financial health and valuation analysis
- **Tools**: Balance sheet, income statement, cash flow, financial ratios
- **Output**: Intrinsic value estimates, financial health assessment
- **Location**: `tradingagents/agents/analysts/fundamentals_analyst.py`

#### Sentiment Analyst
- **Responsibility**: Social media and public sentiment analysis
- **Tools**: Reddit data (PRAW), sentiment scoring algorithms
- **Output**: Public sentiment scores, trending topics, investor mood
- **Location**: `tradingagents/agents/analysts/sentiment_analyst.py`

#### News Analyst
- **Responsibility**: Global news and macroeconomic event analysis
- **Tools**: News APIs, event impact models
- **Output**: Event impact assessments, market-moving news identification
- **Location**: `tradingagents/agents/analysts/news_analyst.py`

### Researcher Team

Researchers engage in structured debates to evaluate analyst insights:

#### Bull Researcher
- **Responsibility**: Identify bullish opportunities and positive catalysts
- **Approach**: Seeks upside potential, growth drivers, favorable trends
- **Output**: Bull case arguments with supporting evidence

#### Bear Researcher
- **Responsibility**: Identify risks and potential downsides
- **Approach**: Seeks red flags, overvaluation signals, adverse conditions
- **Output**: Bear case arguments with risk assessments

#### Research Manager
- **Responsibility**: Moderate debates, synthesize perspectives
- **Process**: Coordinates debate rounds, ensures balanced analysis
- **Output**: Balanced research report with bull/bear synthesis

### Trader Agent

The trader makes final trading decisions based on comprehensive analysis:

- **Input**: Analyst reports, researcher debates, market conditions
- **Process**: Weighs evidence, assesses conviction levels
- **Output**: Trading signal (BUY/SELL/HOLD) with confidence score
- **Location**: `tradingagents/agents/trader.py`

### Risk Management Team

Risk agents evaluate portfolio impact and validate strategies:

#### Risk Analysts
- **Responsibility**: Assess volatility, liquidity, correlation risks
- **Tools**: Risk metrics, scenario analysis, stress testing
- **Output**: Risk assessments with mitigation recommendations

#### Portfolio Manager
- **Responsibility**: Final approval/rejection of trading proposals
- **Process**: Reviews risk reports, validates against portfolio constraints
- **Output**: Approved orders or rejection with reasoning
- **Location**: `tradingagents/agents/portfolio_manager.py`

## Agent Workflow

### 1. Data Collection

All analysts access data through the unified data vendor interface:

```python
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_news
)
```

### 2. Parallel Analysis

Analysts work in parallel, each producing specialized reports:

```
Market Analyst    → Technical Report
Fundamentals      → Financial Report
Sentiment         → Sentiment Report
News Analyst      → Event Report
```

### 3. Research Debate

Researchers debate analyst findings over multiple rounds:

```
Round 1: Bull presents arguments → Bear counters
Round 2: Bear presents risks → Bull defends
...
Final: Research Manager synthesizes
```

Configuration: `config["max_debate_rounds"]` (default: 1)

### 4. Trading Decision

Trader evaluates research synthesis:

```python
decision = {
    "action": "BUY" | "SELL" | "HOLD",
    "confidence_score": 0.0 to 1.0,
    "reasoning": "...",
    "position_size": float
}
```

### 5. Risk Validation

Risk team reviews the trading proposal:

```
Risk Analysts → Risk Assessment
Portfolio Manager → Approve or Reject
```

Configuration: `config["max_risk_discuss_rounds"]` (default: 1)

## State Management

TradingAgents uses LangGraph for state management across the agent workflow.

### AgentState

The main state object carries information through the graph:

```python
@dataclass
class AgentState:
    ticker: str
    date: str
    analyst_reports: Dict[str, str]
    research_synthesis: str
    trading_decision: Dict[str, Any]
    risk_assessment: str
    final_decision: Dict[str, Any]
```

Location: `tradingagents/agents/utils/agent_states.py`

### InvestDebateState

Manages researcher debate rounds:

```python
@dataclass
class InvestDebateState:
    bull_arguments: List[str]
    bear_arguments: List[str]
    debate_round: int
    synthesis: str
```

### RiskDebateState

Manages risk team discussions:

```python
@dataclass
class RiskDebateState:
    risk_assessments: List[str]
    discussion_round: int
    final_recommendation: str
```

## Memory System

Agents maintain context through a vector-based memory system:

### FinancialSituationMemory

- **Purpose**: Store and retrieve historical analysis context
- **Backend**: ChromaDB vector store
- **Features**:
  - Semantic search for relevant past analyses
  - Recency, relevancy, and importance scoring (FinMem pattern)
  - Persistent storage across runs
- **Location**: `tradingagents/agents/utils/memory.py`

## Tool Integration

Agents access data through a unified tool interface:

### Data Tools

Available to all analyst agents:

- `get_stock_data(ticker, start_date, end_date)` - Historical prices
- `get_indicators(ticker, indicators_list)` - Technical indicators
- `get_fundamentals(ticker)` - Financial metrics
- `get_balance_sheet(ticker)` - Balance sheet data
- `get_cashflow(ticker)` - Cash flow statements
- `get_income_statement(ticker)` - Income statements
- `get_news(ticker, date)` - Company-specific news
- `get_global_news(date)` - Market-wide news

Location: `tradingagents/agents/utils/agent_utils.py`

### Tool Nodes

LangGraph ToolNodes wrap data access functions:

```python
from langgraph.prebuilt import ToolNode

analyst_tools = ToolNode([
    get_stock_data,
    get_indicators,
    get_fundamentals
])
```

## Conditional Routing

The graph uses conditional logic to route between agents:

### Debate Continuation

```python
def should_continue_debate(state: InvestDebateState) -> str:
    if state.debate_round >= config["max_debate_rounds"]:
        return "finalize"
    return "continue_debate"
```

### Risk Approval

```python
def check_risk_approval(state: AgentState) -> str:
    if state.risk_assessment["approved"]:
        return "execute"
    return "reject"
```

Location: `tradingagents/graph/conditional_logic.py`

## Extensibility

The multi-agent architecture is designed for extensibility:

### Adding New Analysts

1. Create analyst class inheriting from base analyst
2. Implement `analyze()` method
3. Register in analyst list
4. Agent automatically joins parallel analysis

See [Adding New Analyst Guide](../guides/adding-new-analyst.md)

### Adding Custom Workflows

1. Define new state classes
2. Create agent nodes
3. Add conditional routing logic
4. Integrate into main graph

## Performance Considerations

### Parallel Execution

Analysts run in parallel to minimize latency:

```python
# Analysts execute simultaneously
analyst_nodes = {
    "market": market_analyst,
    "fundamentals": fundamentals_analyst,
    "sentiment": sentiment_analyst,
    "news": news_analyst
}
```

### Debate Rounds

More debate rounds increase analysis depth but also API costs:

- 1 round: Fast, lower cost, adequate for most cases
- 2-3 rounds: Deeper analysis, higher confidence
- 4+ rounds: Diminishing returns, significantly higher cost

### Memory Optimization

Vector store queries are batched and cached:

```python
memory = FinancialSituationMemory(
    persist_directory="./memory_cache"
)
```

## Best Practices

1. **Select Relevant Analysts**: Only enable analysts needed for your strategy
2. **Tune Debate Rounds**: Start with 1 round, increase only if needed
3. **Monitor API Usage**: Track LLM API calls and costs
4. **Use Memory Wisely**: Leverage past analyses for similar contexts
5. **Test Incrementally**: Validate each agent's output before full integration

## References

- [Data Flow Architecture](data-flow.md)
- [LLM Integration](llm-integration.md)
- [TradingGraph API](../api/trading-graph.md)
- [Agent APIs](../api/agents.md)
