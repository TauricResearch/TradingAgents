# CLAUDE.md - TradingAgents Project Guide

## Project Overview

TradingAgents is a multi-agent LLM trading framework built on LangGraph. It mirrors real-world trading firms by deploying specialized agents (analysts, researchers, traders, risk managers) that collaboratively analyze markets and make trading decisions.

**Decision Pipeline:**
```
Analyst Team → Bull/Bear Debate → Trader → Risk 3-way Debate → Final Signal → (Optional) Broker Execution
```

## Quick Start

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
pip install -r requirements.txt

# Set API keys
export OPENAI_API_KEY=...
export OPENDART_API_KEY=...  # Korean market support

# CLI
python -m cli.main

# Programmatic
python main.py
```

## Project Structure

```
TradingAgents/
├── cli/                          # Interactive CLI wizard
│   ├── main.py                   # Entry point, 9-step config wizard + analysis runner
│   ├── models.py                 # AnalystType enum
│   └── utils.py                  # Questionary prompts (ticker, date, LLM, persona, broker)
├── tradingagents/
│   ├── default_config.py         # DEFAULT_CONFIG dict — all configuration options
│   ├── agents/
│   │   ├── analysts/             # Market, News, Social, Fundamentals analysts
│   │   ├── researchers/          # Bull & Bear researchers for investment debate
│   │   ├── trader/trader.py      # Trader agent — produces BUY/SELL/HOLD
│   │   ├── managers/             # Research Manager (debate judge), Risk Manager
│   │   ├── risk_mgmt/            # Aggressive, Conservative, Neutral debaters
│   │   ├── personas.py           # Investment persona prompts (Buffett, Dalio, Lynch)
│   │   └── utils/
│   │       ├── agent_states.py   # AgentState, InvestDebateState, RiskDebateState
│   │       ├── agent_utils.py    # Tool wrappers (get_stock_data, get_news, etc.)
│   │       └── memory.py         # BM25-based FinancialSituationMemory
│   ├── dataflows/
│   │   ├── interface.py          # Vendor routing: route_to_vendor(), TOOLS_CATEGORIES
│   │   ├── config.py             # Runtime config for data vendor selection
│   │   ├── y_finance.py          # yfinance data provider
│   │   ├── alpha_vantage*.py     # Alpha Vantage data providers
│   │   ├── opendart.py           # Korean DART financials/disclosures
│   │   └── stockstats_utils.py   # Technical indicator calculations
│   ├── graph/
│   │   ├── trading_graph.py      # TradingAgentsGraph — main orchestrator class
│   │   ├── setup.py              # GraphSetup — builds LangGraph StateGraph
│   │   ├── propagation.py        # Propagator — creates initial state, graph args
│   │   ├── conditional_logic.py  # Edge routing (analyst → tool → analyst cycle)
│   │   ├── reflection.py         # Post-trade reflection + memory updates
│   │   └── signal_processing.py  # Extracts BUY/SELL/HOLD from LLM output
│   ├── execution/                # Broker execution layer
│   │   ├── __init__.py           # create_broker() factory
│   │   ├── models.py             # OrderRequest, OrderResult, Position, PortfolioSnapshot
│   │   ├── base_broker.py        # BaseBroker ABC
│   │   ├── engine.py             # ExecutionEngine — safety checks + order orchestration
│   │   ├── safety.py             # SafetyGuard — position/loss/market-hours limits
│   │   └── kis/                  # KIS (한국투자증권) broker implementation
│   │       ├── constants.py      # API URLs, tr_ids for paper/real trading
│   │       ├── client.py         # KISClient — HTTP + token mgmt + rate limiting
│   │       └── broker.py         # KISBroker(BaseBroker) implementation
│   └── llm_clients/
│       ├── factory.py            # create_llm_client() — provider routing
│       ├── base_client.py        # BaseLLMClient ABC
│       ├── openai_client.py      # OpenAI/xAI/OpenRouter/Ollama (ChatOpenAI)
│       ├── anthropic_client.py   # Anthropic (ChatAnthropic)
│       └── google_client.py      # Google (ChatGoogleGenerativeAI)
└── main.py                       # Simple programmatic entry point
```

## Key Architecture Concepts

### Config System
All configuration flows through `DEFAULT_CONFIG` in `tradingagents/default_config.py`. The config dict is passed to `TradingAgentsGraph` and threaded through all components.

Key config sections:
- `llm_provider`, `deep_think_llm`, `quick_think_llm` — LLM selection
- `backend_url` — API endpoint (switches per provider)
- `max_debate_rounds`, `max_risk_discuss_rounds` — debate depth
- `data_vendors` — category-level vendor routing (yfinance/alpha_vantage)
- `tool_vendors` — tool-level vendor overrides
- `persona` — investment persona (None, "warren_buffett", "ray_dalio", "peter_lynch")
- `broker` — trade execution config (enabled, mode, safety limits)

### Data Vendor Routing
`tradingagents/dataflows/interface.py` routes data calls to the correct vendor:
- `TOOLS_CATEGORIES` maps tool names → category
- `VENDOR_METHODS` maps (tool, vendor) → implementation function
- `route_to_vendor(tool_name)` reads config to pick the right implementation
- Category-level defaults in `data_vendors`, tool-level overrides in `tool_vendors`

### Agent Creation Pattern
All agents follow a factory pattern:
```python
def create_<agent>(llm, memory=None, persona=None):
    def agent_node(state, name):
        # Read from state, build prompt, call llm.invoke()
        return {"messages": [...], "<field>": result, "sender": name}
    return functools.partial(agent_node, name="<AgentName>")
```

### Persona System
`tradingagents/agents/personas.py` defines `PERSONAS` dict with role-specific prompt fragments. `get_persona_prompt(persona, role)` returns the fragment or "" if None. Only Trader, Research Manager, and Risk Manager get persona injections — analysts stay objective.

### Memory System
`FinancialSituationMemory` uses BM25 to store and retrieve past (situation, recommendation) pairs. Five separate memory stores: bull, bear, trader, invest_judge, risk_manager. After each trade, `Reflector` evaluates returns and updates memories.

### Broker Execution
When `config["broker"]["enabled"]` is True:
1. `create_broker(config)` → `KISBroker` (or future brokers)
2. `ExecutionEngine` wraps broker with `SafetyGuard` checks
3. Graph adds "Executor" node after "Risk Judge"
4. Portfolio context injected into Trader's prompt
5. `BaseBroker` ABC allows future broker implementations (Kiwoom, eBest, etc.)

## Development Patterns

### Adding a New Data Vendor
1. Create `tradingagents/dataflows/<vendor>.py` with matching function signatures
2. Register in `VENDOR_METHODS` in `interface.py`
3. Add vendor name to the relevant `TOOLS_CATEGORIES` entries

### Adding a New Persona
1. Add entry to `PERSONAS` dict in `tradingagents/agents/personas.py`
2. Keys: `"trader"`, `"research_manager"`, `"risk_manager"` — each is a prompt fragment string
3. Use the persona key in config: `config["persona"] = "your_persona"`

### Adding a New Broker
1. Create a new directory under `tradingagents/execution/<broker>/`
2. Implement `BaseBroker` ABC (connect, place_order, get_balance, get_portfolio, etc.)
3. Register in `create_broker()` factory in `execution/__init__.py`

### Adding a New LLM Provider
1. Create `tradingagents/llm_clients/<provider>_client.py` implementing `BaseLLMClient`
2. Register in `create_llm_client()` factory in `llm_clients/factory.py`
3. Add provider options in `cli/utils.py` selection functions

## CLI Steps (cli/main.py)

The interactive wizard has 9 steps:
1. Ticker symbol
2. Analysis date
3. Analyst team selection
4. LLM provider
5. Quick-thinking LLM model
6. Deep-thinking LLM model
7. Research depth
8. Investment persona
9. Broker execution mode

## Environment Variables

```bash
# LLM Providers (set the one you use)
OPENAI_API_KEY=
GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
XAI_API_KEY=
OPENROUTER_API_KEY=

# Data Providers
OPENDART_API_KEY=          # Korean DART disclosures
ALPHA_VANTAGE_API_KEY=     # Alternative to yfinance

# KIS Broker (한국투자증권)
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=            # Format: XXXXXXXX-XX
```

## Testing

```bash
# Verify imports
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"

# Verify execution module
python -c "from tradingagents.execution import create_broker, ExecutionEngine; print('OK')"

# Run CLI
python -m cli.main
```

## Coding Conventions

- Apache 2.0 license headers on new files: `Copyright 2026 herald.k, HongSoo Kim`
- Type hints on function signatures
- Factory pattern for pluggable components (LLM clients, brokers, data vendors)
- Config-driven behavior — no hardcoded provider/model references in core logic
- Korean comments acceptable for KIS broker-specific code
