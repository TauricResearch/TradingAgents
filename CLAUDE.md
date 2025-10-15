# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents is a multi-agent LLM financial trading framework built with LangGraph that mirrors real-world trading firm dynamics. The framework uses specialized LLM agents (analysts, researchers, traders, and risk managers) to collaboratively evaluate market conditions and make informed trading decisions.

**Research Paper**: arXiv:2412.20138

## Core Architecture

### Multi-Agent Pipeline Flow

The system follows a sequential pipeline mimicking institutional trading:

```
Analyst Team → Research Team → Trader → Risk Management → Portfolio Manager
```

### Agent Teams Structure

**1. Analyst Team** (`tradingagents/agents/analysts/`)
- `market_analyst.py` - Technical analysis using MACD, RSI, price patterns
- `social_media_analyst.py` - Sentiment analysis from social media
- `news_analyst.py` - Global news and macroeconomic indicators
- `fundamentals_analyst.py` - Company financials and intrinsic values

**2. Research Team** (`tradingagents/agents/researchers/`)
- `bull_researcher.py` - Bullish perspective analysis
- `bear_researcher.py` - Bearish perspective analysis
- `research_manager.py` - Debate moderator and final decision maker

**3. Trading Team** (`tradingagents/agents/trader/`)
- `trader.py` - Composes reports and makes trading decisions

**4. Risk Management** (`tradingagents/agents/risk_mgmt/`)
- `aggresive_debator.py` - High-risk tolerance perspective
- `conservative_debator.py` - Low-risk tolerance perspective
- `neutral_debator.py` - Balanced risk perspective

**5. Portfolio Management** (`tradingagents/agents/managers/`)
- `risk_manager.py` - Final approval/rejection of trades

### State Management

States are defined in `tradingagents/agents/utils/agent_states.py`:

- **AgentState**: Main state flowing through the graph (company, date, reports, decisions)
- **InvestDebateState**: Research team debate state (bull/bear history, judge decision)
- **RiskDebateState**: Risk management debate state (risky/safe/neutral perspectives)

### Graph Orchestration

The LangGraph workflow is managed in `tradingagents/graph/`:

- `trading_graph.py` - Main orchestration class (`TradingAgentsGraph`)
- `setup.py` - Graph construction and node configuration (`GraphSetup`)
- `propagation.py` - State initialization and execution (`Propagator`)
- `conditional_logic.py` - Routing logic between nodes (`ConditionalLogic`)
- `reflection.py` - Learning from past decisions (`Reflector`)
- `signal_processing.py` - Extract trading signals from decisions (`SignalProcessor`)

### Data Layer

Data flows through an abstraction layer in `tradingagents/dataflows/`:

**Configuration System**:
- `config.py` - Global config management with `set_config()` and `get_config()`
- `interface.py` - Abstract tool interface that routes to appropriate vendor
- `default_config.py` - Default settings including data vendors

**Vendor Implementations**:
- `alpha_vantage*.py` - Alpha Vantage API (fundamental, news, stock data)
- `y_finance.py` / `yfin_utils.py` - Yahoo Finance API (market data, indicators)
- `google.py` / `googlenews_utils.py` - Google News (alternative news source)
- `local.py` - Local data vendor for offline testing
- `openai.py` - LLM-based data vendor for fundamental/news analysis

**Tool Abstraction** (`tradingagents/agents/utils/agent_utils.py`):
Abstract functions automatically route to configured vendor:
- `get_stock_data()`, `get_indicators()` - Market data
- `get_fundamentals()`, `get_balance_sheet()`, `get_cashflow()`, `get_income_statement()` - Fundamental data
- `get_news()`, `get_global_news()` - News data
- `get_insider_sentiment()`, `get_insider_transactions()` - Insider data

## Installation and Setup

### Environment Setup

```bash
# Clone and create virtual environment
conda create -n tradingagents python=3.13
conda activate tradingagents

# Install dependencies
pip install -r requirements.txt
```

### API Keys Configuration

**Required APIs**:
- OpenAI API (for LLM agents)
- Alpha Vantage API (for fundamental and news data - default config)

**Setup via environment variables**:
```bash
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
export ALPHA_VANTAGE_API_KEY=$YOUR_ALPHA_VANTAGE_API_KEY
```

**Setup via .env file**:
```bash
cp .env.example .env
# Edit .env with your actual API keys
```

### Data Vendor Configuration

Modify `tradingagents/default_config.py` to change data sources:

```python
"data_vendors": {
    "core_stock_apis": "yfinance",       # yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",  # yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage", # openai, alpha_vantage, local
    "news_data": "alpha_vantage",        # openai, alpha_vantage, google, local
}
```

## Running the Framework

### CLI Mode (Interactive)

```bash
python -m cli.main
```

This launches an interactive CLI with:
- Ticker selection
- Date selection
- Analyst team selection
- Research depth configuration (debate rounds)
- LLM provider and model selection
- Real-time progress tracking

### Python API Mode

**Basic usage** (`main.py`):
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# Run analysis
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

**Custom configuration**:
```python
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"      # Deep thinking model
config["quick_think_llm"] = "gpt-4o-mini"     # Quick thinking model
config["max_debate_rounds"] = 1               # Research debate rounds
config["max_risk_discuss_rounds"] = 1         # Risk debate rounds

# LLM provider options: "openai", "anthropic", "google", "ollama", "openrouter"
config["llm_provider"] = "openai"
config["backend_url"] = "https://api.openai.com/v1"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("AAPL", "2024-05-10")
```

**Reflection and learning**:
```python
# After getting returns, reflect and update memory
ta.reflect_and_remember(returns_losses=1000)  # Positive returns
```

## LLM Provider Support

The framework supports multiple LLM providers (configured in `tradingagents/graph/trading_graph.py:75-85`):

- **OpenAI**: `llm_provider: "openai"`, backend_url: `https://api.openai.com/v1`
- **Anthropic**: `llm_provider: "anthropic"`
- **Google**: `llm_provider: "google"`
- **Ollama**: `llm_provider: "ollama"` (local models)
- **OpenRouter**: `llm_provider: "openrouter"`

## Key Configuration Parameters

Located in `tradingagents/default_config.py`:

- `results_dir` - Output directory for results (default: `./results`)
- `deep_think_llm` - Model for complex reasoning (default: `o4-mini`)
- `quick_think_llm` - Model for quick tasks (default: `gpt-4o-mini`)
- `max_debate_rounds` - Research team debate rounds (default: `1`)
- `max_risk_discuss_rounds` - Risk team debate rounds (default: `1`)
- `data_vendors` - Data source configuration per category

## Output Structure

Results are saved to:
```
results/
└── {TICKER}/
    └── {DATE}/
        ├── reports/
        │   ├── market_report.md
        │   ├── sentiment_report.md
        │   ├── news_report.md
        │   ├── fundamentals_report.md
        │   ├── investment_plan.md
        │   ├── trader_investment_plan.md
        │   └── final_trade_decision.md
        └── message_tool.log

eval_results/
└── {TICKER}/
    └── TradingAgentsStrategy_logs/
        └── full_states_log_{DATE}.json
```

## Memory System

The framework includes a reflection-based learning system (`tradingagents/agents/utils/memory.py`):

- **FinancialSituationMemory**: Stores past decisions and outcomes
- Memories are agent-specific (bull, bear, trader, judge, risk manager)
- Uses ChromaDB for vector storage
- Enables learning from past trading mistakes

Memory is updated via:
```python
ta.reflect_and_remember(returns_losses)
```

## Testing and Development

**Cost-saving for testing**:
- Use `gpt-4o-mini` or `gpt-4.1-mini` instead of `o1-preview`/`gpt-4o`
- Set `max_debate_rounds: 1` to reduce API calls
- Use `local` data vendor with pre-downloaded data

**Debug mode**:
```python
ta = TradingAgentsGraph(debug=True, config=config)
```
This enables:
- LangGraph state tracing
- Pretty-printed message outputs
- Detailed logging

## Important Notes

1. **API Rate Limits**: The framework makes many API calls. Consider Alpha Vantage Premium for production use.

2. **Data Vendor Fallbacks**: The system has fallback logic when primary vendors fail (see `tradingagents/agents/utils/core_stock_tools.py:23-45`).

3. **Research Disclaimer**: This framework is designed for research purposes. Trading performance varies based on LLM models, temperature, data quality, and other factors. Not intended as financial advice.

4. **Analyst Selection**: When initializing `TradingAgentsGraph`, you can select specific analysts:
   ```python
   ta = TradingAgentsGraph(
       selected_analysts=["market", "news", "fundamentals"],  # Skip social
       config=config
   )
   ```

5. **State Logging**: All states are automatically logged to JSON files for analysis and debugging.
