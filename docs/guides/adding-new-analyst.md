# Guide: Adding a New Analyst

This guide shows you how to extend TradingAgents with a custom analyst agent.

## Overview

Creating a new analyst involves:
1. Creating the analyst class
2. Defining analysis logic
3. Integrating data access tools
4. Registering the analyst
5. Testing the implementation

## Step 1: Create Analyst Class

Create a new file in `tradingagents/agents/analysts/`:

```python
# tradingagents/agents/analysts/momentum_analyst.py

from typing import List, Dict, Any
from langchain.schema import HumanMessage

class MomentumAnalyst:
    """Analyzes multi-timeframe momentum and trend strength."""

    def __init__(self, llm, tools: List):
        """
        Initialize momentum analyst.

        Args:
            llm: Language model for analysis
            tools: List of data access tools
        """
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        self.name = "momentum"

    def analyze(self, ticker: str, date: str) -> str:
        """
        Perform momentum analysis.

        Args:
            ticker: Stock ticker symbol
            date: Analysis date (YYYY-MM-DD)

        Returns:
            Analysis report as string
        """
        # Step 1: Gather data
        data = self._gather_data(ticker, date)

        # Step 2: Create analysis prompt
        prompt = self._create_prompt(ticker, date, data)

        # Step 3: Generate analysis
        response = self.llm.invoke([HumanMessage(content=prompt)])

        return response.content

    def _gather_data(self, ticker: str, date: str) -> Dict[str, Any]:
        """Gather required data for analysis."""
        # Get stock data for multiple timeframes
        stock_data = self.tools["get_stock_data"](
            ticker,
            start_date=self._get_start_date(date, days=90),
            end_date=date
        )

        # Get momentum indicators
        indicators = self.tools["get_indicators"](
            ticker,
            indicators=["MACD", "RSI", "ADX"]
        )

        return {
            "stock_data": stock_data,
            "indicators": indicators
        }

    def _create_prompt(self, ticker: str, date: str, data: Dict[str, Any]) -> str:
        """Create analysis prompt for LLM."""
        return f"""
You are a Momentum Analyst specializing in multi-timeframe trend analysis.

Analyze the momentum and trend strength for {ticker} as of {date}.

Data provided:
- Stock prices (90 days): {data['stock_data']}
- MACD: {data['indicators']['MACD']}
- RSI: {data['indicators']['RSI']}
- ADX: {data['indicators']['ADX']}

Provide analysis covering:
1. Short-term momentum (daily/weekly)
2. Medium-term trend (monthly)
3. Trend strength assessment
4. Potential reversal signals
5. Momentum-based trading recommendation

Format your response as a concise report.
"""

    def _get_start_date(self, end_date: str, days: int) -> str:
        """Calculate start date for data retrieval."""
        from datetime import datetime, timedelta
        end = datetime.strptime(end_date, "%Y-%m-%d")
        start = end - timedelta(days=days)
        return start.strftime("%Y-%m-%d")
```

## Step 2: Register Data Tools

Ensure your analyst has access to required data tools:

```python
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_news
)

# Tools will be passed to analyst constructor
tools = [
    get_stock_data,
    get_indicators,
    # Add other tools as needed
]
```

## Step 3: Integrate into TradingGraph

Modify `tradingagents/graph/trading_graph.py` to include your analyst:

```python
# Import your analyst
from tradingagents.agents.analysts.momentum_analyst import MomentumAnalyst

class TradingAgentsGraph:
    def __init__(self, selected_analysts=None, debug=False, config=None):
        # ... existing initialization ...

        # Initialize analysts
        self.analysts = {}

        if "momentum" in selected_analysts:
            self.analysts["momentum"] = MomentumAnalyst(
                llm=self.quick_thinking_llm,
                tools=self.analyst_tools
            )

        # ... rest of initialization ...
```

## Step 4: Update Analyst Selection

Allow users to select your analyst:

```python
# In main.py or CLI
selected_analysts = ["market", "fundamentals", "momentum"]

ta = TradingAgentsGraph(
    selected_analysts=selected_analysts,
    debug=True
)
```

## Step 5: Test Your Analyst

Create a test file `tests/unit/test_momentum_analyst.py`:

```python
import pytest
from tradingagents.agents.analysts.momentum_analyst import MomentumAnalyst
from unittest.mock import Mock

def test_momentum_analyst_initialization():
    """Test analyst can be initialized."""
    llm = Mock()
    tools = []

    analyst = MomentumAnalyst(llm, tools)

    assert analyst.name == "momentum"
    assert analyst.llm == llm

def test_momentum_analyst_analyze():
    """Test analyst can perform analysis."""
    # Mock LLM
    llm = Mock()
    llm.invoke.return_value = Mock(
        content="Momentum analysis: Strong uptrend..."
    )

    # Mock tools
    get_stock_data = Mock(return_value={
        "dates": ["2024-01-01", "2024-01-02"],
        "close": [150.0, 152.0]
    })
    get_indicators = Mock(return_value={
        "MACD": {"macd": [0.5], "signal": [0.4]},
        "RSI": {"rsi": [65.0]},
        "ADX": {"adx": [30.0]}
    })

    get_stock_data.name = "get_stock_data"
    get_indicators.name = "get_indicators"

    tools = [get_stock_data, get_indicators]

    # Create analyst
    analyst = MomentumAnalyst(llm, tools)

    # Run analysis
    report = analyst.analyze("NVDA", "2024-01-02")

    # Verify
    assert "Momentum analysis" in report
    assert llm.invoke.called
    assert get_stock_data.called
    assert get_indicators.called
```

Run tests:
```bash
pytest tests/unit/test_momentum_analyst.py -v
```

## Advanced Features

### Multi-Timeframe Analysis

```python
def _gather_multi_timeframe_data(self, ticker: str, date: str):
    """Get data for multiple timeframes."""
    return {
        "daily": self.tools["get_stock_data"](
            ticker,
            self._get_start_date(date, days=30),
            date
        ),
        "weekly": self._aggregate_weekly(
            self.tools["get_stock_data"](
                ticker,
                self._get_start_date(date, days=90),
                date
            )
        ),
        "monthly": self._aggregate_monthly(
            self.tools["get_stock_data"](
                ticker,
                self._get_start_date(date, days=365),
                date
            )
        )
    }
```

### Custom Indicators

```python
def _calculate_custom_indicators(self, data):
    """Calculate custom momentum indicators."""
    import numpy as np

    prices = np.array(data["close"])

    # Rate of Change
    roc = (prices[-1] - prices[-20]) / prices[-20] * 100

    # Momentum
    momentum = prices[-1] - prices[-10]

    return {
        "roc": roc,
        "momentum": momentum
    }
```

### Caching Analysis

```python
def analyze(self, ticker: str, date: str) -> str:
    """Analyze with caching."""
    # Check cache
    cache_key = f"momentum_{ticker}_{date}"
    if cached := self._get_from_cache(cache_key):
        return cached

    # Perform analysis
    result = self._perform_analysis(ticker, date)

    # Save to cache
    self._save_to_cache(cache_key, result)

    return result
```

## Best Practices

1. **Clear Responsibility**: Each analyst should have a focused domain
2. **Consistent Interface**: Follow the `analyze(ticker, date)` pattern
3. **Tool Usage**: Use the unified data interface for vendor independence
4. **Error Handling**: Handle missing data and API failures gracefully
5. **Structured Output**: Return well-formatted reports
6. **Testing**: Write unit tests for your analyst
7. **Documentation**: Add docstrings to all methods
8. **Performance**: Cache expensive calculations
9. **Logging**: Use logging for debugging
10. **Configuration**: Make analyst behavior configurable

## Common Patterns

### Comparative Analysis

```python
def compare_to_benchmark(self, ticker: str, benchmark: str, date: str):
    """Compare ticker performance to benchmark."""
    ticker_data = self.tools["get_stock_data"](ticker, ...)
    benchmark_data = self.tools["get_stock_data"](benchmark, ...)

    # Calculate relative strength
    relative_strength = self._calculate_relative_strength(
        ticker_data,
        benchmark_data
    )

    return relative_strength
```

### Sector Analysis

```python
def analyze_sector_context(self, ticker: str, date: str):
    """Analyze ticker in sector context."""
    sector = self._get_sector(ticker)
    peers = self._get_sector_peers(sector)

    # Compare to sector average
    sector_analysis = self._compare_to_peers(ticker, peers, date)

    return sector_analysis
```

### Historical Patterns

```python
def find_historical_patterns(self, ticker: str, date: str):
    """Find similar historical patterns."""
    current_pattern = self._extract_pattern(ticker, date)

    # Search memory for similar patterns
    similar = self.memory.search_similar(
        query=f"{ticker} pattern {current_pattern}",
        k=5
    )

    return similar
```

## Troubleshooting

### Analyst Not Running

**Issue**: Analyst not included in workflow

**Solution**: Check `selected_analysts` includes your analyst name

```python
selected_analysts = ["market", "fundamentals", "momentum"]
```

### Data Access Errors

**Issue**: Tools not available or returning errors

**Solution**: Verify tool registration and vendor configuration

```python
# Check tools are available
print(self.tools.keys())

# Verify vendor config
from tradingagents.dataflows.config import get_config
print(get_config()["data_vendors"])
```

### LLM Errors

**Issue**: LLM returning unexpected responses

**Solution**: Improve prompt clarity and structure

```python
def _create_prompt(self, ticker, date, data):
    """Create clear, structured prompt."""
    return f"""
You are a {self.name} analyst.

Task: Analyze {ticker} as of {date}

Data:
{self._format_data(data)}

Required output format:
1. Key findings
2. Specific metrics
3. Recommendation

Be concise and specific.
"""
```

## See Also

- [Multi-Agent System Architecture](../architecture/multi-agent-system.md)
- [Agents API Reference](../api/agents.md)
- [Data Flows API](../api/dataflows.md)
- [Testing Guide](../testing/writing-tests.md)
