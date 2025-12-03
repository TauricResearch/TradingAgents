# TradingAgents: Multi-Agent LLM Financial Trading Framework

A multi-agent LLM-powered financial trading framework that simulates the decision-making process of a professional trading firm through specialized AI agents.

[Framework](#tradingagents-framework) | [Installation](#installation) | [CLI Usage](#cli-usage) | [Package Usage](#package-usage) | [Attribution](#attribution)

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that simulates the dynamics of a professional trading firm. The system deploys specialized LLM-powered agents including fundamental analysts, sentiment experts, technical analysts, traders, and risk management teams that collaboratively evaluate market conditions and inform trading decisions. These agents engage in structured debates to determine optimal strategies through a LangGraph-based orchestration system.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

TradingAgents is designed for research purposes. Trading performance varies based on the chosen language models, model temperature, trading periods, data quality, and other non-deterministic factors. This framework is not intended as financial, investment, or trading advice.

The framework decomposes complex trading tasks into specialized roles, enabling a robust, scalable approach to market analysis and decision-making.

### Analyst Team

The analyst team consists of four specialized agents that gather and analyze different aspects of market data:

- **Fundamentals Analyst:** Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- **Sentiment Analyst:** Analyzes social media and public sentiment using sentiment scoring algorithms to gauge short-term market mood.
- **News Analyst:** Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- **Technical Analyst:** Utilizes technical indicators (such as MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team

The researcher team comprises both bullish and bearish researchers who critically assess insights from the analyst team. Through structured debates across multiple rounds, they balance potential gains against inherent risks to form a comprehensive investment thesis.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent

The trader agent synthesizes reports from analysts and researchers to formulate trading decisions. It determines the timing and magnitude of trades based on comprehensive market insights and the investment plan from the research team.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager

The risk management team evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. Three debaters with different risk perspectives (aggressive, conservative, and neutral) evaluate and adjust trading strategies, providing assessment reports to the Portfolio Manager.

The Portfolio Manager makes the final approval or rejection of transaction proposals. Approved orders are sent to the simulated exchange for execution.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd TradingAgents
```

Sync virtual environment:

```bash
uv sync
source .venv/bin/activate
```

### Required API Keys

The framework requires an OpenAI API key for powering the agents and at least one news data provider API key.

**Required:**
- `OPENAI_API_KEY` - Powers the LLM agents

**News Data Providers (at least one required):**
- `TAVILY_API_KEY` - Tavily search API (preferred for news discovery)
- `BRAVE_API_KEY` - Brave Search API (fallback option)
- `ALPHA_VANTAGE_API_KEY` - Alpha Vantage API (for fundamentals and news)

The news discovery system uses a fallback chain: Tavily → Brave → Alpha Vantage → OpenAI → Google. Configure the API keys for your preferred providers.

Set environment variables:

```bash
export OPENAI_API_KEY=your_openai_api_key
export ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
export TAVILY_API_KEY=your_tavily_api_key
export BRAVE_API_KEY=your_brave_api_key
```

Alternatively, create a `.env` file in the project root:

```bash
cp .env.example .env
```

Then edit the `.env` file with your API keys.

## CLI Usage

Run the CLI:

```bash
uv run python -m cli.main
```

The CLI provides two main modes:

### Discover Trending Stocks

The trending stock discovery feature uses LLM-powered entity extraction to identify stocks making news. This is the primary enhancement in this fork, enabling proactive discovery of trading opportunities.

Configuration options:

- **Lookback period:** 1h, 6h, 24h, or 7d
- **Sector filter:** Technology, Healthcare, Finance, Energy, Consumer Goods, Industrials
- **Event type filter:** Earnings, Merger/Acquisition, Regulatory, Product Launch, Executive Change

Results display includes scores, mention counts, and sentiment for each discovered stock. Stocks can be selected for full multi-agent analysis directly from the discovery results.

### Analyze Specific Ticker

Run full multi-agent analysis on a specific stock:

- Enter any ticker symbol and analysis date
- Select which analyst agents to deploy
- Configure research depth (debate rounds)
- Watch real-time progress as agents collaborate
- View comprehensive reports from each team

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

The interface displays results as they load, allowing tracking of agent progress during execution.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## Package Usage

### Implementation Overview

TradingAgents is built with LangGraph for flexibility and modularity in agent orchestration. For testing purposes, using smaller models reduces costs as the framework makes numerous API calls during analysis.

### Basic Usage

To use TradingAgents programmatically, import the `tradingagents` module and initialize a `TradingAgentsGraph` object:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

### Configuration Customization

The configuration can be customized to specify LLM models, debate rounds, and data vendors:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"
config["quick_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 1

config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage",
}

ta = TradingAgentsGraph(debug=True, config=config)

_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

### Trending Stock Discovery API

The trending stock discovery feature can be used programmatically through the discovery models:

#### DiscoveryRequest

| Field | Type | Description |
|-------|------|-------------|
| `lookback_period` | str | Time period to search (1h, 6h, 24h, 7d) |
| `sector_filter` | Optional[List[Sector]] | Filter by sector categories |
| `event_filter` | Optional[List[EventCategory]] | Filter by event types |
| `max_results` | int | Maximum number of stocks to return (default: 20) |

#### DiscoveryResult

| Field | Type | Description |
|-------|------|-------------|
| `request` | DiscoveryRequest | The original request parameters |
| `trending_stocks` | List[TrendingStock] | List of discovered trending stocks |
| `status` | DiscoveryStatus | Processing status (created, processing, completed, failed) |

#### TrendingStock

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | str | Stock ticker symbol |
| `company_name` | str | Company name |
| `score` | float | Relevance score |
| `mention_count` | int | Number of mentions in news |
| `sentiment` | float | Sentiment score |
| `sector` | Sector | Industry sector |
| `event_type` | EventCategory | Type of news event |
| `news_summary` | str | Summary of relevant news |
| `source_articles` | List[NewsArticle] | Source news articles |

#### Sector Enum

- `TECHNOLOGY`
- `HEALTHCARE`
- `FINANCE`
- `ENERGY`
- `CONSUMER_GOODS`
- `INDUSTRIALS`
- `OTHER`

#### EventCategory Enum

- `EARNINGS`
- `MERGER_ACQUISITION`
- `REGULATORY`
- `PRODUCT_LAUNCH`
- `EXECUTIVE_CHANGE`
- `OTHER`

#### Example

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.discovery.models import (
    DiscoveryRequest,
    Sector,
    EventCategory,
)
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

request = DiscoveryRequest(
    lookback_period="24h",
    sector_filter=[Sector.TECHNOLOGY, Sector.HEALTHCARE],
    event_filter=[EventCategory.EARNINGS],
    max_results=10,
)

result = ta.discover_trending(request)

for stock in result.trending_stocks:
    print(f"{stock.ticker}: {stock.company_name} (Score: {stock.score:.2f})")
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `llm_provider` | LLM provider (openai, anthropic, google, ollama, openrouter) | openai |
| `deep_think_llm` | Model for complex reasoning tasks | gpt-5 |
| `quick_think_llm` | Model for fast/simple tasks | gpt-5-mini |
| `max_debate_rounds` | Number of bull/bear debate iterations | 2 |
| `max_risk_discuss_rounds` | Number of risk assessment rounds | 2 |
| `discovery_max_results` | Maximum trending stocks to return | 20 |
| `discovery_min_mentions` | Minimum mentions to include stock | 2 |

See `tradingagents/default_config.py` for the full list of configuration options.

## Attribution

This project is based on research by Yijia Xiao, Edward Sun, Di Luo, and Wei Wang. Core agent implementation based on [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138).

```bibtex
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138},
}
```
