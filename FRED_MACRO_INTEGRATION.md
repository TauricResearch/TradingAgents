# FRED API Macro Data Integration

## Summary
Added FRED (Federal Reserve Economic Data) API support to the TradingAgents vendor methods system for macroeconomic analysis, including a new **Macro Analyst** agent.

## Files Added

### 1. `tradingagents/dataflows/macro_utils.py`
New module providing FRED API integration with the following functions:

- **`get_fred_api_key()`** - Get FRED API key from config or environment
- **`get_fred_data(series_id, start_date, end_date)`** - Core FRED API wrapper
- **`get_treasury_yield_curve(curr_date)`** - Treasury yield curve data with inversion analysis
- **`get_economic_indicators_report(curr_date, lookback_days=90)`** - Comprehensive economic indicators
  - Federal Funds Rate
  - Consumer Price Index (CPI)
  - Producer Price Index (PPI)
  - Unemployment Rate
  - Nonfarm Payrolls
  - GDP Growth Rate
  - ISM Manufacturing PMI
  - Consumer Confidence
  - VIX (Market Volatility)
- **`get_fed_calendar_and_minutes(curr_date)`** - Federal Reserve meeting calendar and policy updates
- **`get_macro_economic_summary(curr_date, lookback_days=90)`** - Complete macro economic analysis combining all components

### 2. `tradingagents/agents/analysts/macro_analyst.py`
New macro analyst agent that uses FRED API tools to analyze economic conditions:
- Analyzes Federal Reserve policy and economic indicators
- Evaluates inflation, employment, and growth trends
- Assesses Treasury yield curve and recession signals
- Provides market implications and trading considerations

### 3. `tradingagents/agents/utils/macro_data_tools.py`
Tool wrapper functions for LangChain integration:
- **`get_economic_indicators(curr_date, lookback_days)`** - Comprehensive economic indicators
- **`get_yield_curve(curr_date)`** - Treasury yield curve with inversion analysis
- **`get_fed_calendar(curr_date)`** - Fed meeting calendar and policy updates

## Files Modified

### 4. `tradingagents/dataflows/interface.py`
Updated vendor routing system to include FRED macro data:

**Added Imports:**
```python
from .macro_utils import get_economic_indicators_report, get_treasury_yield_curve, get_fed_calendar_and_minutes
```

**Updated VENDOR_LIST:**
```python
VENDOR_LIST = [
    "local",
    "yfinance",
    "openai",
    "google",
    "fred"  # New
]
```

**New TOOLS_CATEGORIES Entry:**
```python
"macro_data": {
    "description": "Macroeconomic indicators and Federal Reserve data",
    "tools": [
        "get_economic_indicators",
        "get_yield_curve",
        "get_fed_calendar"
    ]
}
```

**New VENDOR_METHODS Entries:**
```python
# macro_data
"get_economic_indicators": {
    "fred": get_economic_indicators_report,
},
"get_yield_curve": {
    "fred": get_treasury_yield_curve,
},
"get_fed_calendar": {
    "fred": get_fed_calendar_and_minutes,
},
```

### 5. `tradingagents/agents/__init__.py`
Added macro analyst to exports:
```python
from .analysts.macro_analyst import create_macro_analyst

__all__ = [
    # ... existing exports ...
    "create_macro_analyst",
]
```

### 6. `tradingagents/agents/utils/agent_utils.py`
Added macro tool imports:
```python
from tradingagents.agents.utils.macro_data_tools import (
    get_economic_indicators,
    get_yield_curve,
    get_fed_calendar
)
```

### 7. `tradingagents/graph/setup.py`
Added macro analyst option to graph setup:
```python
def setup_graph(
    self, selected_analysts=["market", "social", "news", "fundamentals"]
):
    """Set up and compile the agent workflow graph.

    Args:
        selected_analysts (list): List of analyst types to include. Options are:
            - "market": Market analyst
            - "social": Social media analyst
            - "news": News analyst
            - "fundamentals": Fundamentals analyst
            - "macro": Macro economic analyst  # New!
    """
    # ... existing analyst setup ...
    
    if "macro" in selected_analysts:
        analyst_nodes["macro"] = create_macro_analyst(
            self.quick_thinking_llm
        )
        delete_nodes["macro"] = create_msg_delete()
        tool_nodes["macro"] = self.tool_nodes["macro"]
```

### 8. `tradingagents/graph/trading_graph.py`
Added macro tools import and tool node:
```python
from tradingagents.agents.utils.agent_utils import (
    # ... existing imports ...
    get_economic_indicators,
    get_yield_curve,
    get_fed_calendar
)

def _create_tool_nodes(self) -> Dict[str, ToolNode]:
    return {
        # ... existing tool nodes ...
        "macro": ToolNode(
            [
                get_economic_indicators,
                get_yield_curve,
                get_fed_calendar,
            ]
        ),
    }
```

## Configuration Required

To use FRED API features, set the FRED API key via:

1. **Environment Variable:**
   ```bash
   export FRED_API_KEY="your_api_key_here"
   ```

2. **Or via Config System:**
   The `get_fred_api_key()` function will check:
   - Config system via `get_api_key("fred_api_key", "FRED_API_KEY")`
   - Environment variable `FRED_API_KEY`

3. **Get a Free API Key:**
   - Visit: https://fred.stlouisfed.org/
   - Register for a free account
   - Generate API key under "My Account" → "API Keys"

## Usage Examples

### Enable Macro Analyst in Graph

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Create graph with macro analyst enabled
graph = TradingAgentsGraph(
    selected_analysts=["market", "fundamentals", "macro"],  # Include "macro"
    debug=True,
    config=your_config
)

# Run analysis
result = graph.propagate("AAPL", "2025-10-06")
```

### Via Vendor Routing System

```python
from tradingagents.dataflows.interface import route_to_vendor

# Get economic indicators
indicators = route_to_vendor(
    "get_economic_indicators",
    curr_date="2025-10-06",
    lookback_days=90
)

# Get yield curve
yield_curve = route_to_vendor(
    "get_yield_curve",
    curr_date="2025-10-06"
)

# Get Fed calendar
fed_calendar = route_to_vendor(
    "get_fed_calendar",
    curr_date="2025-10-06"
)
```

### Direct Function Calls

```python
from tradingagents.dataflows.macro_utils import (
    get_economic_indicators_report,
    get_treasury_yield_curve,
    get_fed_calendar_and_minutes,
    get_macro_economic_summary
)

# Complete macro analysis
summary = get_macro_economic_summary(
    curr_date="2025-10-06",
    lookback_days=90
)

# Individual components
indicators = get_economic_indicators_report("2025-10-06", 90)
yield_curve = get_treasury_yield_curve("2025-10-06")
fed_data = get_fed_calendar_and_minutes("2025-10-06")
```

## Integration with Macro Analyst

The macro analyst can now use these tools through the vendor routing system. The tools are automatically available through the `macro_data` category:

```python
# In agent configuration
config = {
    "data_vendors": {
        "macro_data": "fred"  # Use FRED for macro data
    }
}
```

## Data Returned

All functions return formatted markdown strings suitable for LLM analysis:

- **Economic Indicators**: Markdown tables with current values, changes, and analysis
- **Yield Curve**: Markdown table with maturities, yields, and inversion warnings
- **Fed Calendar**: FOMC meeting schedule and policy trajectory
- **Trading Implications**: Actionable insights for different economic scenarios

## PR Compatibility Notes

Changes were made with minimal modifications to existing code:

1. ✅ **New files only** - `macro_utils.py`, `macro_analyst.py`, `macro_data_tools.py` are new additions
2. ✅ **Additive changes** - Only added new entries to existing dictionaries and imports
3. ✅ **No breaking changes** - Existing functionality unchanged
4. ✅ **Follows existing patterns** - Uses same vendor routing and analyst architecture
5. ✅ **Consistent naming** - Follows existing naming conventions (`get_*`, `create_*_analyst` patterns)
6. ✅ **Optional feature** - Macro analyst is opt-in via `selected_analysts` parameter

## Testing

To verify the integration works:

```python
# Test FRED API connection
from tradingagents.dataflows.macro_utils import get_fred_data

result = get_fred_data("FEDFUNDS", "2025-01-01", "2025-10-06")
print(result)

# Test vendor routing
from tradingagents.dataflows.interface import route_to_vendor

indicators = route_to_vendor(
    "get_economic_indicators",
    curr_date="2025-10-06",
    lookback_days=30
)
print(indicators)
```

## Dependencies

No new dependencies required. Uses existing dependencies:
- `requests` - For FRED API calls
- `pandas` - For data manipulation
- `datetime` - For date handling
- Existing config system for API key management

## Future Enhancements

Potential improvements:
- Add caching for FRED API responses (similar to YFinanceDataProvider)
- Add more FRED series (housing data, commodity prices, etc.)
- Add international economic indicators
- Add custom FRED series ID support for advanced users
