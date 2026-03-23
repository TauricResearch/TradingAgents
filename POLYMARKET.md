# Polymarket Prediction Market Agent Module

## Quick Start

### Prerequisites

```bash
# Create virtual environment (Python 3.10+)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set up API keys (at least one LLM provider required)
cp .env.example .env
# Edit .env and fill in your API key
```

### Usage

```python
from tradingagents.prediction_market import PMTradingAgentsGraph
from tradingagents.prediction_market.pm_config import PM_DEFAULT_CONFIG
from dotenv import load_dotenv

load_dotenv()

config = PM_DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"          # openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "claude-sonnet-4-6"
config["quick_think_llm"] = "claude-sonnet-4-6"

pm = PMTradingAgentsGraph(debug=True, config=config)

# market_id from Polymarket website or Gamma API
_, decision = pm.propagate("<market_id>", "2026-03-23", "Market question (optional)")
print(decision)
```

### How to Get a Market ID

The market_id is a numeric ID from the Polymarket Gamma API. You can find it by:

```python
import requests

# Option 1: Browse top markets by volume
resp = requests.get("https://gamma-api.polymarket.com/markets", params={
    "active": "true",
    "closed": "false",
    "order": "volume24hr",
    "ascending": "false",
    "limit": 10,
})
for m in resp.json():
    print(f'{m["id"]} | {m["question"]}')

# Option 2: Look up from a Polymarket web URL slug
# e.g. https://polymarket.com/event/xxx → use the slug to search
```

### CLI Usage

You can also use the CLI, which supports pasting Polymarket URLs directly:

```bash
python -m cli.main
# Step 1: Select "Polymarket Market ID (prediction market)"
# Step 2: Paste a Polymarket URL or enter a numeric market ID
```

---

## Architecture Overview

The system is built as a **LangGraph** state machine with 4 phases and 10+ LLM agents:

```
Input: market_id + trade_date + market_question
         |
         v
+-------------------------------------+
|  Phase 1: Analyst Team (4 Analysts)  |
|  Event -> Odds -> Information -> Sent|
+----------------+--------------------+
                 v
+-------------------------------------+
|  Phase 2: Research Debate            |
|  YES Researcher <-> NO Researcher    |
|         -> Research Manager          |
+----------------+--------------------+
                 v
+-------------------------------------+
|  Phase 3: Trading Decision           |
|  PM Trader (Kelly Criterion)         |
+----------------+--------------------+
                 v
+-------------------------------------+
|  Phase 4: Risk Management            |
|  Aggressive <-> Conservative <-> Neut|
|         -> Risk Judge                |
+----------------+--------------------+
                 v
         Structured JSON Output
```

---

## Phase 1: Analyst Team

Four analysts run sequentially, each with a tool loop that calls Polymarket APIs until sufficient data is collected. Uses `quick_think_llm`.

| Analyst | Tools | Responsibility |
|---------|-------|----------------|
| **Event Analyst** | `get_market_info`, `get_resolution_criteria`, `get_event_context` | Analyze the event: what is being predicted, resolution criteria clarity, timeline |
| **Odds Analyst** | `get_market_info`, `get_market_price_history`, `get_order_book` | Market microstructure: current prices, liquidity, bid/ask spread, pricing efficiency |
| **Information Analyst** | `get_news`, `get_global_news`, `get_related_markets`, `search_markets` | Find information not yet priced in, cross-reference related markets |
| **Sentiment Analyst** | `get_news`, `get_global_news` | Public opinion analysis: news, social sentiment, expert vs crowd divergence |

Each analyst produces a report (`event_report`, `odds_report`, `information_report`, `sentiment_report`) that feeds into subsequent phases.

---

## Phase 2: Research Debate

| Role | LLM | Responsibility |
|------|-----|----------------|
| **YES Researcher** | `quick_think_llm` | Build the case for the event occurring, citing analyst reports |
| **NO Researcher** | `quick_think_llm` | Build the case against, rebutting YES arguments |
| **Research Manager** | `deep_think_llm` | Synthesize both sides into an `investment_plan` |

- YES and NO debate for `max_debate_rounds` rounds (default 1 round = 2 turns)
- Both researchers have a **BM25 memory system** that recalls lessons from past similar markets
- Research Manager uses the stronger `deep_think_llm` for final synthesis

---

## Phase 3: Trading Decision

The **PM Trader** (using `quick_think_llm`) receives all reports and the investment plan, then:

1. Estimates the **true probability** based on all analysis
2. Compares against the **market price** from the Odds report
3. Calculates **edge** = |estimated probability - market price|
4. If edge < **5% threshold** -> **PASS**
5. If edge >= 5% -> calculate position size using **0.25x Fractional Kelly Criterion**:
   - Kelly fraction = edge / odds_against
   - Position size = 0.25 x Kelly fraction x bankroll

Decision options:
- **BUY_YES**: Estimated probability > market price + 5% (event more likely than market implies)
- **BUY_NO**: Estimated probability < market price - 5% (event less likely than market implies)
- **PASS**: Edge below threshold or uncertainty too high

---

## Phase 4: Risk Management

Three-way debate + final ruling:

| Role | LLM | Stance |
|------|-----|--------|
| **Aggressive Analyst** | `quick_think_llm` | Advocates for the trade, emphasizes edge and upside |
| **Conservative Analyst** | `quick_think_llm` | Argues against, emphasizes downside risk and uncertainty |
| **Neutral Analyst** | `quick_think_llm` | Balanced perspective, proposes compromise |
| **Risk Judge** | `deep_think_llm` | Final ruling after hearing all sides |

The three analysts debate for `max_risk_discuss_rounds` rounds (default 1 round = 3 turns, one per analyst).

---

## Output Format

The Risk Judge's natural language output is converted to structured JSON by the **Signal Processor**:

```json
{
  "signal": "BUY_YES | BUY_NO | PASS",
  "estimated_probability": 0.65,
  "market_price": 0.50,
  "edge": 0.15,
  "position_size": 0.03,
  "confidence": "high | medium | low"
}
```

---

## Reflection & Learning

After a trade resolves, invoke the reflection mechanism to let agents learn from outcomes:

```python
# After the trade resolves, pass the actual returns
pm.reflect_and_remember(returns_losses=1000)
```

The system will:
1. Review each agent's decisions (YES/NO Researcher, Trader, Research Manager, Risk Judge)
2. Analyze which judgments were correct or incorrect, and why
3. Store lessons learned in a BM25 memory system
4. Automatically reference past experience when encountering similar markets in the future

---

## Configuration

All parameters are in `tradingagents/prediction_market/pm_config.py`:

```python
PM_DEFAULT_CONFIG = {
    # LLM settings
    "llm_provider": "openai",           # openai, google, anthropic, xai, openrouter, ollama
    "deep_think_llm": "gpt-5.2",       # For Research Manager, Risk Judge (deep reasoning)
    "quick_think_llm": "gpt-5-mini",   # For Analysts, Researchers, Trader (speed priority)

    # Polymarket API
    "polymarket_gamma_url": "https://gamma-api.polymarket.com",
    "polymarket_clob_url": "https://clob.polymarket.com",

    # Trading parameters
    "kelly_fraction": 0.25,             # Conservative Kelly multiplier (quarter Kelly)
    "min_edge_threshold": 0.05,         # Minimum edge threshold (5%)
    "max_position_pct": 0.05,           # Max single position as % of bankroll (5%)
    "max_cluster_exposure_pct": 0.15,   # Max exposure to correlated markets (15%)
    "bankroll": 10000,                  # Simulated bankroll

    # Debate settings
    "max_debate_rounds": 1,             # YES/NO debate rounds
    "max_risk_discuss_rounds": 1,       # Risk management debate rounds
}
```

---

## Data Sources

| Source | Purpose | API Key Required |
|--------|---------|-----------------|
| **Polymarket Gamma API** | Market info, resolution criteria, event context, search | No (public API) |
| **Polymarket CLOB API** | Price history, order book | No (public API) |
| **yfinance News** | News search (`get_news`, `get_global_news`) | No |

> **Note**: The news tools are shared with the stock analysis module (yfinance-based), so coverage for political markets may be limited.

---

## Current Limitations

- **Analysis only, no order execution**: v1 does not place actual trades on Polymarket
- **Binary markets only**: Supports Yes/No outcomes; multi-outcome and numeric markets are not supported
- **REST API only**: Uses polling, no WebSocket real-time streaming
- **No backtesting**: No historical backtesting framework included
- **Limited news coverage**: Political market news search is limited since the news tools are designed for stocks

---

## File Structure

```
tradingagents/prediction_market/
├── __init__.py                      # Exports PMTradingAgentsGraph
├── pm_config.py                     # Default configuration
├── agents/
│   ├── analysts/
│   │   ├── event_analyst.py         # Event analysis
│   │   ├── odds_analyst.py          # Odds/pricing analysis
│   │   ├── information_analyst.py   # Information gathering
│   │   └── sentiment_analyst.py     # Sentiment analysis
│   ├── researchers/
│   │   ├── yes_researcher.py        # YES-side researcher
│   │   └── no_researcher.py         # NO-side researcher
│   ├── trader/
│   │   └── pm_trader.py             # Trading decisions (Kelly Criterion)
│   ├── managers/
│   │   ├── research_manager.py      # Research manager (debate synthesis)
│   │   └── risk_manager.py          # Risk manager (final ruling)
│   ├── risk_mgmt/
│   │   ├── aggressive_debator.py    # Aggressive stance
│   │   ├── conservative_debator.py  # Conservative stance
│   │   └── neutral_debator.py       # Neutral stance
│   └── utils/
│       ├── pm_agent_states.py       # LangGraph state definitions
│       ├── pm_agent_utils.py        # Shared utilities
│       └── pm_tools.py              # @tool decorator wrappers
├── dataflows/
│   └── polymarket.py                # Polymarket API client (Gamma + CLOB)
└── graph/
    ├── pm_trading_graph.py          # Main graph class
    ├── setup.py                     # Graph construction logic
    ├── propagation.py               # State initialization & propagation
    ├── conditional_logic.py         # Conditional branching (tool loop, debate control)
    ├── signal_processing.py         # JSON output structuring
    └── reflection.py                # Reflection & learning mechanism
```
