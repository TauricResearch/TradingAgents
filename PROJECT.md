# PROJECT.md - TradingAgents

> Multi-Agent LLM Financial Trading Framework
> Last Updated: 2025-12-25

---

## PROJECT VISION

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents—from fundamental analysts, sentiment experts, and technical analysts to traders and risk management teams—the platform collaboratively evaluates market conditions and informs trading decisions through dynamic agent discussions.

**Research Focus**: This framework is designed for research purposes to explore how multi-agent LLM systems can approach complex financial decision-making.

---

## GOALS

### Primary Goals
- [x] Provide a modular multi-agent framework for financial trading analysis
- [x] Support multiple LLM providers (OpenAI, Anthropic, Google, OpenRouter, Ollama)
- [x] Enable configurable data vendors (yfinance, Alpha Vantage, local)
- [x] Implement specialized analyst agents (fundamental, sentiment, news, technical)
- [x] Support researcher debates (bull vs bear perspectives)
- [x] Include risk management and portfolio approval workflow

### Secondary Goals
- [ ] Expand backtesting capabilities with Tauric TradingDB
- [ ] Add support for additional asset classes
- [ ] Improve caching and performance optimization
- [ ] Enhance CLI experience with more configuration options

---

## SCOPE

### In Scope
- Stock trading analysis and recommendations
- Multi-agent collaboration and debate mechanisms
- Integration with financial data APIs
- CLI and programmatic Python interfaces
- Configuration of LLM models and data sources
- Risk assessment and position management
- Support for multiple LLM providers (OpenAI, Anthropic, Google, OpenRouter, Ollama)

### Out of Scope
- Live trading execution (simulation only)
- Cryptocurrency or forex trading
- Real-time streaming data
- Mobile or web interfaces
- Financial advice (research purposes only)

---

## CONSTRAINTS

<!-- TODO: Define your specific constraints -->

### Performance Constraints
- API rate limits vary by data vendor (Alpha Vantage: 60 req/min with TradingAgents partnership)
- LLM API costs scale with model choice and debate rounds
- Memory usage scales with agent count and data volume

### Technical Constraints
- Requires Python >= 3.10
- Requires API keys for LLM provider (OpenAI recommended)
- Requires Alpha Vantage API key for fundamental/news data (free tier available)

### Regulatory Constraints
- Framework is NOT intended as financial, investment, or trading advice
- For research and educational purposes only

---

## ARCHITECTURE

### System Overview
```
┌─────────────────────────────────────────────────────────────────┐
│                      TradingAgents Graph                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │   Analyst Team   │    │  Researcher Team │                   │
│  ├──────────────────┤    ├──────────────────┤                   │
│  │ • Fundamentals   │───▶│ • Bull Researcher│                   │
│  │ • Sentiment      │    │ • Bear Researcher│                   │
│  │ • News           │    │   (Debates)      │                   │
│  │ • Technical      │    └────────┬─────────┘                   │
│  └──────────────────┘             │                             │
│                                   ▼                             │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │   Data Vendors   │    │   Trader Agent   │                   │
│  ├──────────────────┤    └────────┬─────────┘                   │
│  │ • yfinance       │             │                             │
│  │ • Alpha Vantage  │             ▼                             │
│  │ • OpenAI         │    ┌──────────────────┐                   │
│  │ • Google         │    │ Risk Management  │                   │
│  │ • Local          │    ├──────────────────┤                   │
│  └──────────────────┘    │ • Aggressive     │                   │
│                          │ • Conservative   │                   │
│                          │ • Neutral        │                   │
│                          └────────┬─────────┘                   │
│                                   │                             │
│                                   ▼                             │
│                          ┌──────────────────┐                   │
│                          │Portfolio Manager │                   │
│                          │ (Final Decision) │                   │
│                          └──────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### Technology Stack
| Layer | Technology |
|-------|------------|
| Framework | LangGraph, LangChain |
| LLM Providers | OpenAI (o4-mini, gpt-4o), Anthropic, Google GenAI, OpenRouter (unified access), Ollama (local) |
| Data Sources | yfinance, Alpha Vantage API, Reddit (PRAW) |
| Storage | ChromaDB (vector store), Redis (caching) |
| CLI | Rich, Questionary |
| Backtesting | Backtrader |
| Python Version | >= 3.10 (3.13 recommended) |

### Key Dependencies
- `langgraph` - Agent orchestration and state management
- `langchain-openai/anthropic/google-genai` - LLM integrations
- `yfinance` - Stock price and technical data
- `chromadb` - Vector storage for memory
- `rich` - CLI output formatting

---

## FILE ORGANIZATION

```
TradingAgents/
├── tradingagents/           # Main package
│   ├── agents/              # LLM agent implementations
│   │   ├── analysts/        # Analyst agents (fundamental, sentiment, news, technical)
│   │   ├── researchers/     # Bull/bear researcher debate agents
│   │   ├── risk_mgmt/       # Risk management debators
│   │   ├── trader/          # Trader agent
│   │   ├── managers/        # Research and risk managers
│   │   └── utils/           # Agent utilities, tools, states
│   ├── dataflows/           # Data vendor integrations
│   │   ├── alpha_vantage*.py  # Alpha Vantage API modules
│   │   ├── y_finance.py     # yfinance integration
│   │   ├── google.py        # Google news integration
│   │   └── local.py         # Local data vendor
│   ├── graph/               # LangGraph workflow
│   │   ├── trading_graph.py # Main graph definition
│   │   ├── propagation.py   # Forward propagation logic
│   │   ├── reflection.py    # Agent reflection
│   │   └── signal_processing.py
│   └── default_config.py    # Default configuration
├── cli/                     # Command-line interface
│   ├── main.py              # CLI entry point
│   ├── models.py            # CLI data models
│   └── utils.py             # CLI utilities
├── main.py                  # Quick start example
├── test.py                  # Basic tests
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Project metadata
└── assets/                  # Documentation images
```

---

## TESTING STRATEGY

### Current State
- Basic test file exists (`test.py`)
- No formal test framework configured

### Recommended Testing
- Unit tests for individual agents
- Integration tests for data vendor APIs
- End-to-end tests for trading graph propagation
- Mock LLM responses for deterministic testing

---

## DOCUMENTATION MAP

| Document | Purpose |
|----------|---------|
| README.md | Installation, usage, API reference |
| LICENSE | MIT License |
| PROJECT.md | This file - project overview |
| assets/ | Architecture diagrams, CLI screenshots |

---

## CURRENT SPRINT

<!-- TODO: Define your current sprint goals -->

### Active Work
- [ ] Define sprint goals here

### Backlog
- Expand data vendor options
- Improve caching performance
- Add more comprehensive testing
- Enhance CLI configuration options

---

## CONFIGURATION REFERENCE

### Environment Variables
```bash
# LLM Provider API Keys (choose one based on llm_provider config)
OPENAI_API_KEY=<optional>           # OpenAI API key (required for OpenAI provider or embeddings)
ANTHROPIC_API_KEY=<optional>        # Anthropic API key (required for Anthropic provider)
OPENROUTER_API_KEY=<optional>       # OpenRouter API key (required for OpenRouter provider)
GOOGLE_API_KEY=<optional>           # Google API key (required for Google provider)

# Data Vendor API Keys
ALPHA_VANTAGE_API_KEY=<required>    # Alpha Vantage for fundamental/news data

# Application Configuration
TRADINGAGENTS_RESULTS_DIR=./results # Output directory for results
```

### Default Config Options
```python
{
    "llm_provider": "openai",        # Options: openai, anthropic, google, openrouter, ollama
    "deep_think_llm": "o4-mini",     # For complex reasoning
    "quick_think_llm": "gpt-4o-mini", # For fast responses
    "backend_url": "https://api.openai.com/v1",  # API endpoint (varies by provider)
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage",
    }
}
```

### OpenRouter Configuration Example
OpenRouter provides unified access to multiple LLM models. To use OpenRouter:

```python
config = {
    "llm_provider": "openrouter",
    "deep_think_llm": "anthropic/claude-sonnet-4.5",  # provider/model-name format
    "quick_think_llm": "openai/gpt-4o-mini",
    "backend_url": "https://openrouter.ai/api/v1",
}
```

**Requirements:**
- OPENROUTER_API_KEY environment variable must be set
- OPENAI_API_KEY must also be set for embeddings (OpenRouter does not provide embeddings)
- Model names use the format: `provider/model-name` (e.g., `anthropic/claude-sonnet-4.5`, `openai/gpt-4o`)
- See [OpenRouter models list](https://openrouter.ai/docs/models) for available models

---

## DEVELOPMENT NOTES

### Getting Started
```bash
# Clone and setup
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
conda create -n tradingagents python=3.13
conda activate tradingagents
pip install -r requirements.txt

# Configure API keys
export OPENAI_API_KEY=your_key
export ALPHA_VANTAGE_API_KEY=your_key

# Run CLI
python -m cli.main

# Or use programmatically
python main.py
```

### Key Entry Points
- `python -m cli.main` - Interactive CLI
- `python main.py` - Programmatic example
- `TradingAgentsGraph.propagate(ticker, date)` - Core API

---

*Generated by autonomous-dev setup wizard*
