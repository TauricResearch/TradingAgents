# PROJECT.md - TradingAgents Investment Platform

> Multi-Agent LLM Investment Platform with Execution Capabilities
> Last Updated: 2025-12-26

---

## PROJECT VISION

TradingAgents is evolving from a signal-generation research framework into a **complete investment platform** that:

1. **Analyzes markets** using multi-agent LLM collaboration (existing capability)
2. **Executes trades** via broker APIs (Alpaca, Interactive Brokers)
3. **Manages portfolios** with performance tracking and Australian CGT compliance
4. **Simulates strategies** to compare effectiveness before risking capital
5. **Learns from outcomes** using a layered memory system (FinMem pattern)

**Target Markets:** US Stocks, ETFs, Crypto, Futures, Australian Equities

**Patterns Borrowed From:**
- **FinMem**: Layered memory system (recency, relevancy, importance scoring)
- **Microsoft Qlib**: Modular loose-coupled architecture
- **Alpaca Bots**: Order execution, position tracking, risk controls

---

## GOALS

### Phase 1: Foundation (Current)
- [x] Multi-agent framework for financial analysis
- [x] Multiple LLM providers (OpenAI, Anthropic, Google, OpenRouter, Ollama)
- [x] Data vendors (yfinance, Alpha Vantage, Google News)
- [x] Analyst agents (fundamental, sentiment, news, technical)
- [x] Researcher debates (bull vs bear)
- [x] Risk management workflow
- [ ] **Database layer** for user persistence (#2-7)
- [ ] **Enhanced data layer** - FRED, multi-timeframe, benchmarks (#8-12)

### Phase 2: Enhanced Analysis
- [ ] **Momentum Analyst** - multi-timeframe momentum, ROC, ADX (#13)
- [ ] **Macro Analyst** - FRED interpretation, regime detection (#14)
- [ ] **Correlation Analyst** - cross-asset, sector rotation (#15)
- [ ] **Position Sizing Manager** - Kelly, risk parity, ATR (#16)
- [ ] **Memory System** - FinMem pattern for learning (#18-21)

### Phase 3: Execution & Portfolio
- [ ] **Broker Integration** - Alpaca (US), IBKR (futures, ASX) (#22-28)
- [ ] **Portfolio Management** - positions, performance, CGT (#29-32)
- [ ] **Simulation Mode** - strategy comparison without real money (#33-37)

### Phase 4: Alerts & Polish
- [ ] **Alert System** - Email, Slack, SMS (#38-41)
- [ ] **Backtest Engine** - historical simulation (#42-44)
- [ ] **REST API** - external access (#45-48)

---

## SCOPE

### In Scope
- Multi-agent LLM analysis (fundamentals, sentiment, news, technical, momentum, macro)
- **Live trade execution** via Alpaca and Interactive Brokers
- **Paper trading / simulation mode** for strategy testing
- Multi-asset support: US stocks, ETFs, crypto, futures, Australian equities
- Portfolio tracking with mark-to-market valuation
- **Australian CGT calculations** with 50% discount for >12 month holdings
- Multi-timeframe analysis (daily, weekly, monthly)
- Macro-economic data integration (FRED)
- User database for profiles, portfolios, settings
- Alert notifications (email, Slack, SMS)
- Backtesting with historical data
- CLI and programmatic Python interfaces
- Optional REST API

### Out of Scope
- Mobile or web UI (API only for now)
- Real-time streaming data (polling-based)
- Options trading
- Financial advice (investment decisions are user's responsibility)
- Tax advice (CGT calculations are informational only)

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

### System Overview (Extended)
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
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STRATEGY LAYER (NEW)                          │
├─────────────────────────────────────────────────────────────────────┤
│  Signal-to-Order │ Position Sizing │ Timeframe Coordinator          │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       EXECUTION LAYER (NEW)                          │
├─────────────────────────────────────────────────────────────────────┤
│  Order Validator │ Risk Controls │ Broker Router                    │
│                  │               │ (Paper / Alpaca / IBKR)          │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PORTFOLIO LAYER (NEW)                           │
├─────────────────────────────────────────────────────────────────────┤
│  Position Tracker │ Portfolio State │ Performance │ CGT Calculator  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MEMORY & LEARNING (Enhanced)                      │
├─────────────────────────────────────────────────────────────────────┤
│  Layered Memory (FinMem) │ Trade History │ Risk Profiles            │
└─────────────────────────────────────────────────────────────────────┘
```

### Broker Routing
```
Asset Type        →  Broker Selection
─────────────────────────────────────
US Stocks/ETFs    →  Alpaca
Crypto            →  Alpaca
Futures (GC, SI)  →  Interactive Brokers
ASX (Australia)   →  Interactive Brokers
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
├── tradingagents/           # Main package (existing + enhanced)
│   ├── agents/
│   │   ├── analysts/        # Analyst agents
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── sentiment_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── market_analyst.py (technical)
│   │   │   ├── momentum_analyst.py   # NEW
│   │   │   ├── macro_analyst.py      # NEW
│   │   │   └── correlation_analyst.py # NEW
│   │   ├── managers/
│   │   │   └── position_sizing_manager.py  # NEW
│   │   └── ...
│   ├── dataflows/
│   │   ├── fred.py              # NEW - Federal Reserve data
│   │   ├── multi_timeframe.py   # NEW - Weekly/Monthly
│   │   ├── benchmark.py         # NEW - SPY, sectors
│   │   └── ...
│   └── memory/                  # NEW - FinMem pattern
│       ├── layered_memory.py
│       ├── trade_history.py
│       └── risk_profiles.py
│
├── execution/                   # NEW - Broker integration
│   ├── brokers/
│   │   ├── base.py
│   │   ├── broker_router.py
│   │   ├── alpaca_broker.py
│   │   ├── ibkr_broker.py
│   │   └── paper_broker.py
│   ├── orders/
│   └── risk_controls/
│
├── portfolio/                   # NEW - Portfolio management
│   ├── portfolio_state.py
│   ├── position_tracker.py
│   ├── performance.py
│   └── tax_calculator.py        # Australian CGT
│
├── simulation/                  # NEW - Strategy testing
│   ├── scenario_runner.py
│   ├── strategy_comparator.py
│   └── economic_conditions.py
│
├── strategy/                    # NEW
│   ├── signal_to_order.py
│   ├── position_sizing.py
│   └── strategy_executor.py
│
├── backtest/                    # NEW
│   ├── backtest_engine.py
│   └── results_analyzer.py
│
├── alerts/                      # NEW
│   ├── alert_manager.py
│   └── channels/
│
├── database/                    # NEW - User persistence
│   ├── models/
│   │   ├── user.py
│   │   ├── portfolio.py
│   │   ├── settings.py
│   │   └── trade.py
│   ├── migrations/
│   └── db.py
│
├── api/                         # NEW - REST API (optional)
│   └── app.py
│
├── cli/                         # Existing CLI
├── main.py
└── scripts/
    └── create_issues.py         # GitHub issue creation
```

---

## TESTING STRATEGY

### Test Organization (REQUIRED)
All new code MUST include tests organized as follows:

```
tests/
├── conftest.py              # Shared fixtures (LLM mocks, env mocks)
├── unit/                    # Fast, mocked tests
│   ├── conftest.py         # Unit-specific fixtures
│   └── test_*.py
├── integration/             # Tests with real internal components
│   ├── conftest.py         # Integration fixtures
│   └── test_*.py
└── e2e/                     # End-to-end tests
    └── test_*.py
```

### Testing Requirements
1. **TDD Approach**: Write tests BEFORE implementation
2. **Unit Tests**: All new functions must have unit tests
3. **Integration Tests**: All new features must have integration tests
4. **Mocking**: Use fixtures in conftest.py for LLM and API mocking
5. **Markers**: Use `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`

### Test Fixtures (conftest.py)
Standard fixtures that MUST be used:
- `mock_env_openrouter`, `mock_env_openai`, `mock_env_anthropic` - Environment isolation
- `mock_langchain_classes` - LLM class mocking
- `mock_chromadb` - Database mocking (uses `get_or_create_collection`)
- `mock_yfinance`, `mock_alpha_vantage` - Data vendor mocking

### Running Tests
```bash
pytest tests/unit -m unit           # Fast unit tests only
pytest tests/integration -m integration  # Integration tests
pytest tests/ --tb=short           # All tests
```

---

## DOCUMENTATION MAP

| Document | Purpose |
|----------|---------|
| README.md | Installation, usage, API reference, feature overview |
| PROJECT.md | This file - project roadmap, architecture, configuration |
| LICENSE | MIT License |
| docs/ | Comprehensive documentation structure (see below) |
| assets/ | Architecture diagrams, CLI screenshots |

### Documentation Structure (`docs/`)
Located in `/docs/` directory with the following sections:

- **Getting Started**
  - `QUICKSTART.md` - Get up and running with TradingAgents
  - `development/setup.md` - Development environment setup
  - `guides/configuration.md` - Configuration reference for LLM providers and data vendors

- **Architecture & Design**
  - `architecture/multi-agent-system.md` - Agent roles and collaboration patterns
  - `architecture/data-flow.md` - System data flow and integrations
  - `architecture/llm-integration.md` - LLM provider abstraction and selection

- **API Reference**
  - `api/trading-graph.md` - Core TradingGraph orchestration API
  - `api/agents.md` - Agent interfaces and implementations
  - `api/dataflows.md` - Data vendor integrations and APIs

- **Developer Guides**
  - `guides/adding-new-analyst.md` - Extend framework with custom analysts
  - `guides/adding-llm-provider.md` - Integrate new LLM providers
  - `guides/adding-data-vendor.md` - Add new data vendor integrations

- **Testing**
  - `testing/README.md` - Testing philosophy and overview
  - `testing/running-tests.md` - Test suite execution guide
  - `testing/writing-tests.md` - Guidelines for writing new tests

- **Development**
  - `development/setup.md` - Development environment configuration
  - `development/contributing.md` - Contributing guidelines

**For full documentation index, see `docs/README.md`**

---

## CURRENT SPRINT

### Sprint: Platform Foundation

**Goal:** Build the foundation for the investment platform

### Active Work
See [GitHub Issues](https://github.com/akaszubski/TradingAgents/issues) for full backlog.

**Phase 1: Database (Issues #2-7)**
- [ ] #2 Database setup - SQLAlchemy + PostgreSQL/SQLite
- [ ] #3 User model - profiles, tax jurisdiction
- [ ] #4 Portfolio model - live, paper, backtest
- [ ] #5 Settings model - risk profiles, alerts
- [ ] #6 Trade model - CGT tracking
- [ ] #7 Alembic migrations

**Phase 2: Data Layer (Issues #8-12)**
- [ ] #8 FRED API integration
- [ ] #9 Multi-timeframe aggregation
- [ ] #10 Benchmark data
- [ ] #11 Interface routing
- [ ] #12 Data caching

### Backlog (47 total issues)
- Phase 3: New Analysts (#13-17)
- Phase 4: Memory System (#18-21)
- Phase 5: Execution Layer (#22-28)
- Phase 6: Portfolio Management (#29-32)
- Phase 7: Simulation (#33-37)
- Phase 8: Alerts (#38-41)
- Phase 9: Backtest (#42-44)
- Phase 10: API & Docs (#45-48)

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

### DeepSeek Configuration Example
DeepSeek provides cost-effective reasoning models with strong performance on quantitative analysis tasks. To use DeepSeek:

```python
config = {
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-reasoner",  # Extended reasoning model
    "quick_think_llm": "deepseek-chat",     # Fast responses for simple queries
    "backend_url": "https://api.deepseek.com/v1",
}
```

**Requirements:**
- DEEPSEEK_API_KEY environment variable must be set
- Get your API key from [DeepSeek Platform](https://platform.deepseek.com/)
- For embeddings, either set OPENAI_API_KEY (preferred) or install sentence-transformers package
- Model options: `deepseek-chat` (fast) and `deepseek-reasoner` (extended thinking)
- DeepSeek uses OpenAI API format (ChatOpenAI compatible)

**Embedding Fallback Chain:**
- Tries OPENAI_API_KEY for OpenAI embeddings (recommended for best quality)
- Falls back to HuggingFace sentence-transformers (all-MiniLM-L6-v2) if available and no OpenAI key
- Disables memory features with warning if no embedding backend available

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
