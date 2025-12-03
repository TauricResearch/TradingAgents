# Tool System Architecture

## Overview

The TradingAgents tool system has been redesigned with a **registry-based architecture** that eliminates code duplication, reduces complexity, and makes it easy to add new tools.

## Key Improvements

### Before (Old System)
- **6-7 layers** of function calls for a single data fetch
- Tools defined in **4+ places** (duplicated)
- **Dual registry systems** (new unused, legacy used)
- **Complex 3-level config lookup** (tool → category → vendor)
- **Manual agent-tool mapping** scattered across files
- Unnecessary re-export layer (agent_utils.py)
- Adding a tool required changes in **6 files**

### After (New System)
- **3 layers** for tool execution (clean, predictable)
- **Single source of truth** for all tool metadata
- **One registry** (TOOL_REGISTRY)
- **Simplified routing** with optional fallbacks
- **Auto-generated** agent-tool mappings
- Auto-generated LangChain @tool wrappers
- Adding a tool requires changes in **1 file**

## Architecture Components

### 1. Tool Registry (`tradingagents/tools/registry.py`)

The **single source of truth** for all tools. Each tool is defined once with complete metadata:

```python
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "get_stock_data": {
        "description": "Retrieve stock price data (OHLCV) for a given ticker symbol",
        "category": "core_stock_apis",
        "agents": ["market"],              # Which agents can use this tool
        "primary_vendor": "yfinance",      # Primary data vendor
        "fallback_vendors": ["alpha_vantage"],  # Optional fallbacks
        "parameters": {
            "symbol": {"type": "str", "description": "Ticker symbol"},
            "start_date": {"type": "str", "description": "Start date yyyy-mm-dd"},
            "end_date": {"type": "str", "description": "End date yyyy-mm-dd"},
        },
        "returns": "str: Formatted dataframe containing stock price data",
    },
    # ... 15 more tools
}
```

**Helper Functions:**
- `get_tools_for_agent(agent_name)` → List of tool names for agent
- `get_tool_metadata(tool_name)` → Complete metadata dict
- `get_vendor_config(tool_name)` → Vendor configuration
- `get_agent_tool_mapping()` → Full agent→tools mapping
- `validate_registry()` → Check for issues

### 2. Tool Executor (`tradingagents/tools/executor.py`)

Simplified tool execution that replaces the complex `route_to_vendor()`:

```python
def execute_tool(tool_name: str, *args, **kwargs) -> Any:
    """Execute a tool using registry-based routing.

    Workflow:
    1. Get vendor config from registry
    2. Build vendor list (primary + fallbacks)
    3. Try each vendor in order
    4. Return result or raise ToolExecutionError
    """
    vendor_config = get_vendor_config(tool_name)
    vendors_to_try = [vendor_config["primary"]] + vendor_config["fallbacks"]

    for vendor in vendors_to_try:
        try:
            result = _execute_with_vendor(tool_name, vendor, *args, **kwargs)
            return result
        except Exception:
            continue  # Try next vendor

    raise ToolExecutionError("All vendors failed")
```

**Features:**
- Clear error messages
- Debug logging
- Optional fallback support
- Backward compatible with old `route_to_vendor()`

### 3. Tool Generator (`tradingagents/tools/generator.py`)

Auto-generates LangChain `@tool` wrappers from the registry:

```python
def generate_langchain_tool(tool_name: str, metadata: Dict[str, Any]) -> Callable:
    """Generate a LangChain @tool wrapper for a specific tool.

    This eliminates the need for manual @tool definitions.
    """
    # Build parameter annotations from registry
    param_annotations = {}
    for param_name, param_info in metadata["parameters"].items():
        param_type = _get_python_type(param_info["type"])
        param_annotations[param_name] = Annotated[param_type, param_info["description"]]

    # Create tool function dynamically
    def tool_function(**kwargs):
        return execute_tool(tool_name, **kwargs)

    # Apply @tool decorator and return
    return tool(tool_function)
```

**Pre-Generated Tools:**
```python
# Generate all tools once at module import time
ALL_TOOLS = generate_all_tools()

# Export for easy import
get_stock_data = ALL_TOOLS["get_stock_data"]
get_news = ALL_TOOLS["get_news"]
# ... all 16 tools
```

**Agent-Specific Tools:**
```python
def get_agent_tools(agent_name: str) -> list:
    """Get list of tool functions for a specific agent."""
    agent_tools = generate_tools_for_agent(agent_name)
    return list(agent_tools.values())
```

## How to Add a New Tool

**Old way:** Edit 6 files (registry.py, vendor files, agent_utils.py, tools.py, config, tests)

**New way:** Edit **1 file** (registry.py)

### Example: Adding a "get_earnings" tool

1. Open `tradingagents/tools/registry.py`
2. Add one entry to `TOOL_REGISTRY`:

```python
"get_earnings": {
    "description": "Retrieve earnings data for a ticker",
    "category": "fundamental_data",
    "agents": ["fundamentals"],
    "primary_vendor": "alpha_vantage",
    "fallback_vendors": ["yfinance"],
    "parameters": {
        "ticker": {"type": "str", "description": "Ticker symbol"},
        "quarters": {"type": "int", "description": "Number of quarters", "default": 4},
    },
    "returns": "str: Earnings data report",
},
```

3. Run `python -m tradingagents.tools.generator` to regenerate tools.py
4. Done! The tool is now available to all fundamentals agents

## Call Flow

### Old System (6-7 layers)
```
Agent calls tool
  → agent_utils.py re-export
    → tools.py @tool wrapper
      → route_to_vendor()
        → _get_vendor_for_category()
          → _get_vendor_for_tool()
            → VENDOR_METHODS lookup
              → vendor function
```

### New System (3 layers)
```
Agent calls tool
  → execute_tool(tool_name, **kwargs)
    → vendor function
```

## Integration Points

### Trading Graph (`tradingagents/graph/trading_graph.py`)

```python
def _create_tool_nodes(self) -> Dict[str, ToolNode]:
    """Create tool nodes using registry-based system."""
    from tradingagents.tools.generator import get_agent_tools

    tool_nodes = {}
    for agent_name in ["market", "social", "news", "fundamentals"]:
        tools = get_agent_tools(agent_name)  # Auto-generated from registry
        if tools:
            tool_nodes[agent_name] = ToolNode(tools)
    return tool_nodes
```

### Discovery Graph (`tradingagents/graph/discovery_graph.py`)

```python
from tradingagents.tools.executor import execute_tool

# Old: reddit_report = route_to_vendor("get_trending_tickers", limit=15)
# New:
reddit_report = execute_tool("get_trending_tickers", limit=15)
```

### Agent Utils (`tradingagents/agents/utils/agent_utils.py`)

```python
from tradingagents.tools.generator import ALL_TOOLS

# Re-export for backward compatibility
get_stock_data = ALL_TOOLS["get_stock_data"]
get_news = ALL_TOOLS["get_news"]
# ...
```

## Testing

Run the comprehensive test suite:

```bash
python test_new_tool_system.py
```

This tests:
- Registry loading and validation
- Tool generation for all 16 tools
- Agent-specific tool mappings
- Tool executor functionality
- Integration with trading_graph

## Configuration

The new system uses the same configuration format as before:

```python
DEFAULT_CONFIG = {
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "reddit,alpha_vantage",  # Multi-vendor with fallback
    },
    "tool_vendors": {
        # Tool-level overrides (optional)
        "get_stock_data": "alpha_vantage",  # Override category default
    },
}
```

## Current Tools (16 Total)

### Core Stock APIs (2)
- `get_stock_data` - OHLCV price data
- `validate_ticker` - Ticker validation

### Technical Indicators (1)
- `get_indicators` - RSI, MACD, SMA, EMA

### Fundamental Data (5)
- `get_fundamentals` - Comprehensive fundamentals
- `get_balance_sheet` - Balance sheet data
- `get_cashflow` - Cash flow statement
- `get_income_statement` - Income statement
- `get_recommendation_trends` - Analyst recommendations

### News & Insider Data (4)
- `get_news` - Ticker-specific news
- `get_global_news` - Global market news
- `get_insider_sentiment` - Insider trading sentiment
- `get_insider_transactions` - Insider transaction history
- `get_reddit_discussions` - Reddit discussions

### Discovery Tools (4)
- `get_trending_tickers` - Reddit trending stocks
- `get_market_movers` - Top gainers/losers
- `get_tweets` - Twitter search

## Agent-Tool Mapping

| Agent | Tools | Count |
|-------|-------|-------|
| **market** | get_stock_data, get_indicators | 2 |
| **social** | get_news, get_reddit_discussions | 2 |
| **news** | get_news, get_global_news, get_insider_sentiment, get_insider_transactions | 4 |
| **fundamentals** | get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_recommendation_trends | 5 |

## Backward Compatibility

The new system maintains full backward compatibility:

1. **Old imports still work:**
   ```python
   from tradingagents.agents.utils.agent_utils import get_stock_data
   ```

2. **Legacy `route_to_vendor()` still works:**
   ```python
   from tradingagents.tools.executor import route_to_vendor  # Deprecated
   route_to_vendor("get_stock_data", symbol="AAPL")  # Still works
   ```

3. **Old configuration format supported**

## Migration Guide

If you have custom code using the old system:

### Before
```python
from tradingagents.dataflows.interface import route_to_vendor

data = route_to_vendor("get_stock_data", symbol="AAPL", start_date="2024-01-01")
```

### After
```python
from tradingagents.tools.executor import execute_tool

data = execute_tool("get_stock_data", symbol="AAPL", start_date="2024-01-01")
```

## Benefits Summary

✅ **Simpler** - 3 layers instead of 6-7
✅ **DRY** - Single source of truth, no duplication
✅ **Flexible** - Optional fallbacks per tool
✅ **Maintainable** - Add tools by editing 1 file instead of 6
✅ **Type-Safe** - Auto-generated type annotations
✅ **Testable** - Clear, isolated components
✅ **Documented** - Self-documenting registry
✅ **Backward Compatible** - Old code still works

## Developer Experience

**Adding a tool: Before vs After**

| Step | Old System | New System |
|------|------------|------------|
| 1. Define metadata | Edit `registry.py` | Edit `registry.py` |
| 2. Add vendor implementation | Edit vendor file | *(already exists)* |
| 3. Update VENDOR_METHODS | Edit `interface.py` | *(auto-handled)* |
| 4. Create @tool wrapper | Edit `tools.py` | *(auto-generated)* |
| 5. Re-export in agent_utils | Edit `agent_utils.py` | *(auto-generated)* |
| 6. Update agent mapping | Edit multiple files | *(auto-generated)* |
| 7. Update config schema | Edit `default_config.py` | *(optional)* |
| **Total files to edit** | **6 files** | **1 file** |
| **Lines of code** | ~100 lines | ~15 lines |

## Future Improvements

Potential enhancements:
- [ ] Add tool usage analytics
- [ ] Performance monitoring per vendor
- [ ] Auto-retry with exponential backoff
- [ ] Caching layer for repeated calls
- [ ] Rate limiting per vendor
- [ ] Vendor health checks
- [ ] Tool versioning support
