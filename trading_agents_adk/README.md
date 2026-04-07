# TradingAgents ADK

A multi-agent LLM trading framework built on [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/), ported from the original [TradingAgents](https://github.com/TauricResearch/TradingAgents) LangGraph implementation.

## Architecture

The system mirrors a real-world trading firm with specialized LLM-powered agents collaborating through a structured pipeline:

```
ParallelAgent[Analysts]  -->  InvestmentDebate  -->  Trader  -->  RiskDebate  -->  PortfolioManager
       |                          |                    |              |                  |
  Market Analyst            Bull <-> Bear          Trade Decision   Aggressive        Final
  Fundamentals Analyst      Research Manager                       Conservative      Rating +
  News Analyst                                                     Neutral           Action Plan
```

### LangGraph to ADK Mapping

| LangGraph Concept | ADK Equivalent | Notes |
|---|---|---|
| `StateGraph` | `SequentialAgent` | Main pipeline orchestration |
| Sequential analyst nodes | `ParallelAgent` | Analysts now run concurrently |
| Conditional debate loops | `LoopAgent` | Bull/Bear and Risk debates |
| `@tool` decorator | Plain Python functions | ADK wraps them as `FunctionTool` |
| State dict | `session.state` | Shared via `output_key` on each agent |
| `ToolNode` + conditionals | Automatic | ADK handles tool call routing |
| `ChatOpenAI` / LLM clients | `model` parameter | ADK manages model calls natively |

### Key Improvements over LangGraph Version

1. **Parallel Analysts**: All analysts run concurrently via `ParallelAgent` (was sequential)
2. **Simpler Tool Handling**: No `ToolNode` or conditional routing needed
3. **Cleaner State**: Uses ADK's `output_key` instead of manually managing a state dict
4. **Less Boilerplate**: No message management, deletion nodes, or prompt template chains
5. **Native Gemini**: First-class Gemini integration without adapter layers

## Project Structure

```
trading_agents_adk/
├── main.py                 # Entry point
├── config.py               # Default configuration
├── pyproject.toml           # Project dependencies
├── .env.example            # API key template
├── graph/
│   ├── __init__.py
│   └── trading_graph.py    # Main TradingAgentsGraph orchestrator
├── agents/
│   ├── __init__.py
│   ├── analysts.py         # Market, Fundamentals, News analysts
│   ├── researchers.py      # Bull/Bear researchers + Research Manager
│   ├── risk_analysts.py    # Aggressive/Conservative/Neutral analysts
│   ├── debate.py           # Debate orchestration (LoopAgent)
│   ├── trader.py           # Trader agent
│   └── portfolio_manager.py # Final decision maker
├── tools/
│   ├── __init__.py
│   ├── market_tools.py     # Stock data + technical indicators
│   ├── fundamental_tools.py # Financials, balance sheet, income
│   └── news_tools.py       # News + global news
└── dataflows/
    └── __init__.py         # Placeholder for data vendor routing
```

## Setup

```bash
# 1. Navigate to the project
cd trading_agents_adk

# 2. Set your Google API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
# Get one at https://aistudio.google.com/apikey

# 3. Run (uv handles dependency installation automatically)
uv run main.py --company NVDA --debug
```

> `uv run` automatically creates a virtual environment and installs all
> dependencies from `pyproject.toml` on first run. No manual `pip install` needed.

## Usage

### Command Line

```bash
# Basic usage
uv run main.py --company AAPL

# With all options
uv run main.py \
  --company TSLA \
  --date 2026-04-07 \
  --debug \
  --model gemini-2.5-flash \
  --deep-model gemini-2.5-pro \
  --debate-rounds 2 \
  --risk-rounds 1
```

### Python API

```python
import asyncio
from graph.trading_graph import TradingAgentsGraph

async def analyze():
    ta = TradingAgentsGraph(
        model="gemini-2.5-flash",
        deep_model="gemini-2.5-pro",
        max_debate_rounds=1,
        debug=True,
    )
    result = await ta.propagate("NVDA", "2026-04-07")
    print(result["final_decision"])

asyncio.run(analyze())
```

## Extending

### Adding a New Analyst

1. Create tools in `tools/` (plain Python functions with docstrings)
2. Create an `LlmAgent` in `agents/` with those tools and an `output_key`
3. Add it to the `ParallelAgent` in `graph/trading_graph.py`

### Adding Memory/Reflection

The original project uses `FinancialSituationMemory` for learning from past decisions. To add this in ADK, use `ToolContext.state` with persistent state prefixes (`user:*` or `app:*`) and a vector store for similarity search.

### Switching Models

ADK supports multiple models. Change the `model` parameter:

```python
ta = TradingAgentsGraph(
    model="gemini-2.5-flash",         # or any supported model
    deep_model="gemini-2.5-pro",
)
```
