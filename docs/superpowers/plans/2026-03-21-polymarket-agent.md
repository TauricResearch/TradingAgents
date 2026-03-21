# Polymarket Prediction Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert TradingAgents stock analysis framework into a Polymarket prediction market analysis agent.

**Architecture:** Incremental layer-by-layer replacement. Data tools first, then agent states, graph workflow, agent prompts, signal processing, and finally CLI. Each task produces a working (or at least non-breaking) commit.

**Tech Stack:** Python 3.11, LangGraph, LangChain, py-clob-client, tavily-python, Pydantic, questionary, Rich

**Spec:** `docs/superpowers/specs/2026-03-21-polymarket-agent-design.md`

---

## File Structure

### New Files
- `tradingagents/agents/utils/polymarket_tools.py` — All Polymarket API tool functions
- `tradingagents/agents/researchers/yes_advocate.py` — YES Advocate (replaces bull)
- `tradingagents/agents/researchers/no_advocate.py` — NO Advocate (replaces bear)
- `tradingagents/agents/researchers/timing_advocate.py` — Timing Advocate (new)
- `tradingagents/agents/analysts/odds_analyst.py` — Odds Analyst (replaces market)
- `tradingagents/agents/analysts/event_analyst.py` — Event Analyst (replaces fundamentals)
- `tests/test_polymarket_tools.py` — Tool function tests
- `tests/test_agent_states.py` — State definition tests
- `tests/test_conditional_logic.py` — Routing logic tests
- `tests/test_signal_processing.py` — Output parsing tests

### Modified Files
- `tradingagents/agents/utils/agent_states.py` — InvestDebateState + AgentState field changes
- `tradingagents/agents/utils/agent_utils.py` — Import new tools, remove old tool re-exports
- `tradingagents/agents/__init__.py` — Update exports
- `tradingagents/agents/analysts/news_analyst.py` — Prompt update for prediction markets
- `tradingagents/agents/analysts/social_media_analyst.py` — Prompt + tool update
- `tradingagents/agents/managers/research_manager.py` — Prompt update for 3-way debate
- `tradingagents/agents/managers/risk_manager.py` — Prompt update for prediction markets
- `tradingagents/agents/trader/trader.py` — Prompt + output format change
- `tradingagents/graph/conditional_logic.py` — 3-way debate routing + method renames
- `tradingagents/graph/setup.py` — Node/edge rewrite for new agents
- `tradingagents/graph/propagation.py` — Initial state field changes
- `tradingagents/graph/signal_processing.py` — JSON output parsing
- `tradingagents/graph/trading_graph.py` — Memory/tool/method updates
- `tradingagents/graph/reflection.py` — Method renames + field name updates
- `tradingagents/default_config.py` — New config fields
- `cli/models.py` — AnalystType enum update
- `cli/utils.py` — Event input + scan mode
- `cli/main.py` — MessageBuffer + display updates
- `requirements.txt` — New dependencies

### Deleted Files (after new equivalents are in place)
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/analysts/fundamentals_analyst.py`
- `tradingagents/agents/utils/core_stock_tools.py`
- `tradingagents/agents/utils/technical_indicators_tools.py`
- `tradingagents/agents/utils/fundamental_data_tools.py`
- `tradingagents/agents/utils/news_data_tools.py`

---

## Task 1: Dependencies and Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `tradingagents/default_config.py:3-34`
- Modify: `.env`

- [ ] **Step 1: Add new dependencies to requirements.txt**

Append to `requirements.txt`:
```
py-clob-client
tavily-python
tweepy
praw
pydantic
```

- [ ] **Step 2: Install new dependencies**

Run: `source .venv/bin/activate && pip install py-clob-client tavily-python tweepy praw pydantic`

- [ ] **Step 3: Update default_config.py**

Replace the entire `DEFAULT_CONFIG` dict in `tradingagents/default_config.py`:

```python
import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openrouter",
    "deep_think_llm": "z-ai/glm-4.5-air:free",
    "quick_think_llm": "nvidia/nemotron-3-nano-30b-a3b:free",
    "backend_url": "https://openrouter.ai/api/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": None,
    "openai_reasoning_effort": None,
    # Debate and discussion settings
    "max_debate_rounds": 1,       # 1 round = 3 turns in 3-way debate
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # API keys (loaded from env)
    "tavily_api_key": os.getenv("TAVILY_API_KEY"),
    "twitter_bearer_token": os.getenv("TWITTER_BEARER_TOKEN"),
    "reddit_client_id": os.getenv("REDDIT_CLIENT_ID"),
    "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
    "polymarket_relayer_key": os.getenv("POLYMARKET_RELAYER_KEY"),
    # Auto-scan defaults
    "scan_defaults": {
        "min_volume_24h": 10000,
        "min_liquidity": 5000,
        "max_days_to_end": 30,
        "categories": [],
    },
}
```

- [ ] **Step 4: Add TAVILY_API_KEY to .env**

Append to `.env`:
```
TAVILY_API_KEY=<user's key>
```

- [ ] **Step 5: Verify imports work**

Run: `source .venv/bin/activate && python -c "from py_clob_client.client import ClobClient; from tavily import TavilyClient; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tradingagents/default_config.py
git commit -m "chore: add Polymarket dependencies and update config"
```

Note: Do NOT commit `.env` — it contains secrets. Ensure `.env` is in `.gitignore`.

---

## Task 2: Polymarket Data Tools

**Files:**
- Create: `tradingagents/agents/utils/polymarket_tools.py`
- Create: `tests/test_polymarket_tools.py`

- [ ] **Step 1: Write failing tests for tool functions**

Create `tests/test_polymarket_tools.py`:

```python
"""Tests for Polymarket API tool functions."""
import pytest
from unittest.mock import patch, MagicMock


def test_get_market_data_returns_string():
    """get_market_data should return a formatted string report."""
    from tradingagents.agents.utils.polymarket_tools import get_market_data
    # Mock the HTTP call
    mock_response = {
        "id": "test-id",
        "question": "Will X happen?",
        "outcomes": '["Yes","No"]',
        "outcomePrices": '[0.65, 0.35]',
        "volume": 100000,
        "volume24hr": 5000,
        "liquidity": 20000,
        "spread": 0.02,
        "bestBid": 0.64,
        "bestAsk": 0.66,
        "lastTradePrice": 0.65,
        "endDate": "2026-04-01T00:00:00Z",
        "description": "Test event",
        "active": True,
        "closed": False,
    }
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_response)
        result = get_market_data(event_id="test-id")
    assert isinstance(result, str)
    assert "Will X happen?" in result
    assert "0.65" in result


def test_get_price_history_returns_string():
    """get_price_history should return formatted price history."""
    from tradingagents.agents.utils.polymarket_tools import get_price_history
    mock_history = {"history": [{"t": 1710000000, "p": 0.5}, {"t": 1710003600, "p": 0.55}]}
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_history)
        result = get_price_history(token_id="test-token", interval="1d")
    assert isinstance(result, str)
    assert "0.5" in result


def test_get_event_details_returns_string():
    """get_event_details should return event metadata."""
    from tradingagents.agents.utils.polymarket_tools import get_event_details
    mock_event = {
        "id": "evt-1",
        "title": "Test Event",
        "description": "Detailed desc",
        "endDate": "2026-04-01",
        "markets": [{"id": "m1", "question": "Will X?", "outcomePrices": '[0.6, 0.4]'}],
    }
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_event)
        result = get_event_details(event_id="evt-1")
    assert isinstance(result, str)
    assert "Test Event" in result


def test_get_orderbook_returns_string():
    """get_orderbook should return formatted bid/ask data."""
    from tradingagents.agents.utils.polymarket_tools import get_orderbook
    mock_book = {
        "bids": [{"price": "0.64", "size": "1000"}, {"price": "0.63", "size": "500"}],
        "asks": [{"price": "0.66", "size": "800"}, {"price": "0.67", "size": "300"}],
    }
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_book)
        result = get_orderbook(token_id="test-token")
    assert isinstance(result, str)
    assert "0.64" in result


def test_get_event_news_returns_string():
    """get_event_news should return news search results."""
    from tradingagents.agents.utils.polymarket_tools import get_event_news
    mock_results = {
        "results": [
            {"title": "Breaking News", "url": "https://example.com", "content": "News content"}
        ]
    }
    with patch("tradingagents.agents.utils.polymarket_tools.TavilyClient") as MockTavily:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        MockTavily.return_value = mock_client
        result = get_event_news(query="test event", api_key="fake-key")
    assert isinstance(result, str)
    assert "Breaking News" in result


def test_get_whale_activity_returns_string():
    """get_whale_activity should return whale position data."""
    from tradingagents.agents.utils.polymarket_tools import get_whale_activity
    mock_holders = [
        {"address": "0xabc", "amount": "50000", "side": "YES"},
        {"address": "0xdef", "amount": "30000", "side": "NO"},
    ]
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_holders)
        result = get_whale_activity(market_id="test-market")
    assert isinstance(result, str)
    assert "0xabc" in result or "50000" in result


def test_get_market_stats_returns_string():
    """get_market_stats should return OI and volume stats."""
    from tradingagents.agents.utils.polymarket_tools import get_market_stats
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"openInterest": "75000"})
        result = get_market_stats(market_id="test-market")
    assert isinstance(result, str)
    assert "75000" in result


def test_search_markets_returns_list():
    """search_markets should return formatted market list."""
    from tradingagents.agents.utils.polymarket_tools import search_markets
    mock_events = [
        {
            "id": "e1",
            "title": "Event One",
            "volume": 100000,
            "liquidity": 50000,
            "markets": [{"question": "Will X?", "outcomePrices": '[0.7, 0.3]'}],
        }
    ]
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_events)
        result = search_markets(min_volume=1000)
    assert isinstance(result, str)
    assert "Event One" in result


def test_get_market_data_handles_api_error():
    """get_market_data should return error message on API failure."""
    from tradingagents.agents.utils.polymarket_tools import get_market_data
    with patch("tradingagents.agents.utils.polymarket_tools.requests.get") as mock_get:
        mock_get.side_effect = Exception("Connection timeout")
        result = get_market_data(event_id="test-id")
    assert isinstance(result, str)
    assert "error" in result.lower() or "unavailable" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_polymarket_tools.py -v 2>&1 | head -30`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement polymarket_tools.py**

Create `tradingagents/agents/utils/polymarket_tools.py`:

```python
"""Polymarket API tool functions for prediction market analysis.

All functions are decorated with @tool for LangChain tool binding.
Each returns a formatted string report suitable for LLM consumption.
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from langchain_core.tools import tool

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

MAX_RETRIES = 3
TIMEOUT = 30


def _api_get(url: str, params: dict = None) -> dict:
    """Make a GET request with retry and error handling."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)


@tool
def get_market_data(event_id: str) -> str:
    """Get Polymarket event/market metadata including current price, spread, and volume.

    Args:
        event_id: The Polymarket event ID or slug.
    """
    try:
        data = _api_get(f"{GAMMA_BASE}/events/{event_id}")
        if not data:
            data = _api_get(f"{GAMMA_BASE}/events", params={"slug": event_id})
            if isinstance(data, list) and data:
                data = data[0]

        question = data.get("question", data.get("title", "Unknown"))
        markets = data.get("markets", [data]) if "markets" in data else [data]

        lines = [f"# Market Data for: {question}\n"]
        for m in markets:
            q = m.get("question", question)
            prices = m.get("outcomePrices", "[]")
            if isinstance(prices, str):
                prices = json.loads(prices)
            outcomes = m.get("outcomes", "[]")
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)

            lines.append(f"## {q}")
            lines.append(f"- **Outcomes**: {', '.join(outcomes)}")
            lines.append(f"- **Prices**: {', '.join(str(p) for p in prices)}")
            lines.append(f"- **Volume (24h)**: ${m.get('volume24hr', 'N/A'):,}" if isinstance(m.get('volume24hr'), (int, float)) else f"- **Volume (24h)**: {m.get('volume24hr', 'N/A')}")
            lines.append(f"- **Total Volume**: ${m.get('volume', 'N/A'):,}" if isinstance(m.get('volume'), (int, float)) else f"- **Total Volume**: {m.get('volume', 'N/A')}")
            lines.append(f"- **Liquidity**: ${m.get('liquidity', 'N/A'):,}" if isinstance(m.get('liquidity'), (int, float)) else f"- **Liquidity**: {m.get('liquidity', 'N/A')}")
            lines.append(f"- **Spread**: {m.get('spread', 'N/A')}")
            lines.append(f"- **Best Bid**: {m.get('bestBid', 'N/A')}")
            lines.append(f"- **Best Ask**: {m.get('bestAsk', 'N/A')}")
            lines.append(f"- **Last Trade**: {m.get('lastTradePrice', 'N/A')}")
            lines.append(f"- **1h Change**: {m.get('oneHourPriceChange', 'N/A')}")
            lines.append(f"- **24h Change**: {m.get('oneDayPriceChange', 'N/A')}")
            lines.append(f"- **1w Change**: {m.get('oneWeekPriceChange', 'N/A')}")
            lines.append(f"- **End Date**: {m.get('endDate', 'N/A')}")
            lines.append(f"- **Active**: {m.get('active', 'N/A')}")
            lines.append(f"- **Token IDs**: {m.get('clobTokenIds', 'N/A')}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching market data: {e}. Data unavailable."


@tool
def get_price_history(token_id: str, interval: str = "1w") -> str:
    """Get historical price timeseries for a Polymarket token.

    Args:
        token_id: The CLOB token ID.
        interval: Time interval (1h, 6h, 1d, 1w, 1m, all).
    """
    try:
        data = _api_get(f"{CLOB_BASE}/prices-history", params={
            "market": token_id,
            "interval": interval,
            "fidelity": 60,
        })
        history = data.get("history", [])
        if not history:
            return "No price history available for this token."

        lines = [f"# Price History (interval: {interval})\n"]
        lines.append(f"Total data points: {len(history)}\n")
        lines.append("| Timestamp | Price |")
        lines.append("|-----------|-------|")

        for point in history:
            ts = datetime.fromtimestamp(point["t"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            lines.append(f"| {ts} | {point['p']:.4f} |")

        # Summary stats
        prices = [p["p"] for p in history]
        lines.append(f"\n**Summary:**")
        lines.append(f"- Current: {prices[-1]:.4f}")
        lines.append(f"- High: {max(prices):.4f}")
        lines.append(f"- Low: {min(prices):.4f}")
        lines.append(f"- Start: {prices[0]:.4f}")
        lines.append(f"- Change: {(prices[-1] - prices[0]):.4f} ({((prices[-1] - prices[0]) / max(prices[0], 0.001)) * 100:.1f}%)")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching price history: {e}. Data unavailable."


@tool
def get_event_details(event_id: str) -> str:
    """Get detailed event information including resolution criteria and deadline.

    Args:
        event_id: The Polymarket event ID or slug.
    """
    try:
        data = _api_get(f"{GAMMA_BASE}/events/{event_id}")
        if not data:
            data = _api_get(f"{GAMMA_BASE}/events", params={"slug": event_id})
            if isinstance(data, list) and data:
                data = data[0]

        lines = [f"# Event Details\n"]
        lines.append(f"**Title**: {data.get('title', 'N/A')}")
        lines.append(f"**Description**: {data.get('description', 'N/A')}")
        lines.append(f"**End Date**: {data.get('endDate', 'N/A')}")
        lines.append(f"**Start Date**: {data.get('startDate', 'N/A')}")
        lines.append(f"**Resolution Source**: {data.get('resolutionSource', 'N/A')}")
        lines.append(f"**Active**: {data.get('active', 'N/A')}")
        lines.append(f"**Closed**: {data.get('closed', 'N/A')}")

        markets = data.get("markets", [])
        if markets:
            lines.append(f"\n## Markets ({len(markets)} total)\n")
            for m in markets:
                prices = m.get("outcomePrices", "[]")
                if isinstance(prices, str):
                    prices = json.loads(prices)
                outcomes = m.get("outcomes", "[]")
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                lines.append(f"- **{m.get('question', 'N/A')}**: {dict(zip(outcomes, prices))}")
                lines.append(f"  Volume: {m.get('volume', 'N/A')} | Liquidity: {m.get('liquidity', 'N/A')}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching event details: {e}. Data unavailable."


@tool
def get_orderbook(token_id: str) -> str:
    """Get orderbook depth (bid/ask distribution) for a Polymarket token.

    Args:
        token_id: The CLOB token ID.
    """
    try:
        data = _api_get(f"{CLOB_BASE}/book", params={"token_id": token_id})
        bids = data.get("bids", [])
        asks = data.get("asks", [])

        lines = [f"# Orderbook\n"]

        lines.append("## Bids (Buy Orders)")
        lines.append("| Price | Size |")
        lines.append("|-------|------|")
        total_bid_size = 0
        for b in bids[:20]:
            lines.append(f"| {b['price']} | {b['size']} |")
            total_bid_size += float(b['size'])

        lines.append(f"\nTotal bid depth (top 20): ${total_bid_size:,.0f}")

        lines.append("\n## Asks (Sell Orders)")
        lines.append("| Price | Size |")
        lines.append("|-------|------|")
        total_ask_size = 0
        for a in asks[:20]:
            lines.append(f"| {a['price']} | {a['size']} |")
            total_ask_size += float(a['size'])

        lines.append(f"\nTotal ask depth (top 20): ${total_ask_size:,.0f}")

        if bids and asks:
            best_bid = float(bids[0]['price'])
            best_ask = float(asks[0]['price'])
            lines.append(f"\n**Spread**: {best_ask - best_bid:.4f}")
            lines.append(f"**Midpoint**: {(best_bid + best_ask) / 2:.4f}")
            bid_ask_ratio = total_bid_size / max(total_ask_size, 1)
            lines.append(f"**Bid/Ask Size Ratio**: {bid_ask_ratio:.2f}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching orderbook: {e}. Data unavailable."


@tool
def get_event_news(query: str, api_key: str = None) -> str:
    """Search for recent news related to a Polymarket event.

    Args:
        query: Search query (event question or keywords).
        api_key: Tavily API key. Uses env TAVILY_API_KEY if not provided.
    """
    try:
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            return "Tavily API key not available. News data unavailable."

        from tavily import TavilyClient
        client = TavilyClient(api_key=key)
        results = client.search(query=query, max_results=10, search_depth="advanced")

        articles = results.get("results", [])
        if not articles:
            return f"No news found for query: {query}"

        lines = [f"# News Search: {query}\n"]
        for i, article in enumerate(articles, 1):
            lines.append(f"## {i}. {article.get('title', 'N/A')}")
            lines.append(f"**URL**: {article.get('url', 'N/A')}")
            content = article.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching news: {e}. Data unavailable."


@tool
def get_global_news(query: str = "global markets prediction markets polymarket", api_key: str = None) -> str:
    """Search for broad macro/global news relevant to prediction markets.

    Args:
        query: Search query for global news.
        api_key: Tavily API key. Uses env TAVILY_API_KEY if not provided.
    """
    try:
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            return "Tavily API key not available. Global news data unavailable."

        from tavily import TavilyClient
        client = TavilyClient(api_key=key)
        results = client.search(query=query, max_results=8, search_depth="basic")

        articles = results.get("results", [])
        if not articles:
            return "No global news found."

        lines = ["# Global News & Macro Trends\n"]
        for i, article in enumerate(articles, 1):
            lines.append(f"## {i}. {article.get('title', 'N/A')}")
            lines.append(f"**URL**: {article.get('url', 'N/A')}")
            content = article.get("content", "")
            if len(content) > 400:
                content = content[:400] + "..."
            lines.append(f"{content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching global news: {e}. Data unavailable."


@tool
def get_whale_activity(market_id: str) -> str:
    """Get whale/smart money positions for a Polymarket market.

    Args:
        market_id: The Polymarket market condition ID.
    """
    try:
        data = _api_get(f"{DATA_BASE}/holders", params={"market": market_id})
        if not data:
            return "No whale activity data available."

        holders = data if isinstance(data, list) else data.get("holders", [])

        lines = ["# Whale Activity & Top Holders\n"]
        lines.append("| Address | Amount | Side |")
        lines.append("|---------|--------|------|")

        total_yes = 0
        total_no = 0
        for h in holders[:20]:
            addr = h.get("address", "unknown")
            amount = h.get("amount", h.get("size", "0"))
            side = h.get("side", "N/A")
            lines.append(f"| {addr[:10]}... | ${float(amount):,.0f} | {side} |")
            if side == "YES":
                total_yes += float(amount)
            else:
                total_no += float(amount)

        lines.append(f"\n**Total YES positions (top 20)**: ${total_yes:,.0f}")
        lines.append(f"**Total NO positions (top 20)**: ${total_no:,.0f}")
        if total_yes + total_no > 0:
            lines.append(f"**YES/NO ratio**: {total_yes / max(total_no, 1):.2f}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching whale activity: {e}. Data unavailable."


@tool
def get_market_stats(market_id: str) -> str:
    """Get open interest, volume trends, and liquidity stats for a market.

    Args:
        market_id: The Polymarket market condition ID.
    """
    try:
        oi_data = _api_get(f"{DATA_BASE}/openInterest", params={"market": market_id})

        lines = ["# Market Statistics\n"]
        oi = oi_data if isinstance(oi_data, (int, float, str)) else oi_data.get("openInterest", "N/A")
        lines.append(f"**Open Interest**: ${float(oi):,.0f}" if oi != "N/A" else f"**Open Interest**: {oi}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching market stats: {e}. Data unavailable."


@tool
def get_leaderboard_signals(category: str = "OVERALL", time_period: str = "WEEK") -> str:
    """Get top trader leaderboard for smart money signals.

    Args:
        category: Leaderboard category (OVERALL, POLITICS, SPORTS, CRYPTO, etc.).
        time_period: Time period (DAY, WEEK, MONTH, ALL).
    """
    try:
        data = _api_get(f"{DATA_BASE}/v1/leaderboard", params={
            "category": category,
            "timePeriod": time_period,
            "orderBy": "pnl",
            "limit": 10,
        })

        traders = data if isinstance(data, list) else data.get("leaderboard", data.get("results", []))
        if not traders:
            return "No leaderboard data available."

        lines = [f"# Top Traders Leaderboard ({category}, {time_period})\n"]
        lines.append("| Rank | Trader | Volume | PnL |")
        lines.append("|------|--------|--------|-----|")
        for t in traders[:10]:
            rank = t.get("rank", "N/A")
            name = t.get("userName", t.get("name", "Anonymous"))
            vol = t.get("vol", t.get("volume", 0))
            pnl = t.get("pnl", t.get("profit", 0))
            lines.append(f"| {rank} | {name} | ${float(vol):,.0f} | ${float(pnl):,.0f} |")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching leaderboard: {e}. Data unavailable."


@tool
def get_social_sentiment(query: str) -> str:
    """Get social media sentiment for a prediction market event.

    Args:
        query: Search query (event question or keywords).
    """
    lines = [f"# Social Sentiment Analysis: {query}\n"]

    # Try Twitter/X
    twitter_token = os.getenv("TWITTER_BEARER_TOKEN")
    if twitter_token:
        try:
            import tweepy
            client = tweepy.Client(bearer_token=twitter_token)
            tweets = client.search_recent_tweets(query=query, max_results=20, tweet_fields=["public_metrics", "created_at"])
            if tweets.data:
                lines.append("## X/Twitter Sentiment\n")
                positive = neutral = negative = 0
                for tweet in tweets.data:
                    lines.append(f"- {tweet.text[:200]}...")
                    metrics = tweet.public_metrics or {}
                    likes = metrics.get("like_count", 0)
                    if likes > 5:
                        positive += 1
                    else:
                        neutral += 1
                lines.append(f"\n**Tweet count**: {len(tweets.data)}")
                lines.append(f"**Positive/Neutral/Negative**: {positive}/{neutral}/{negative}")
            else:
                lines.append("No relevant tweets found.")
        except Exception as e:
            lines.append(f"Twitter data unavailable: {e}")
    else:
        lines.append("Twitter API key not configured. Skipping X/Twitter data.")

    # Try Reddit
    reddit_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if reddit_id and reddit_secret:
        try:
            import praw
            reddit = praw.Reddit(
                client_id=reddit_id,
                client_secret=reddit_secret,
                user_agent="polymarket-agent/1.0",
            )
            results = list(reddit.subreddit("all").search(query, limit=10, sort="relevance", time_filter="week"))
            if results:
                lines.append("\n## Reddit Sentiment\n")
                for post in results:
                    lines.append(f"- **r/{post.subreddit}** [{post.score} pts]: {post.title[:150]}")
                lines.append(f"\n**Post count**: {len(results)}")
                avg_score = sum(p.score for p in results) / len(results)
                lines.append(f"**Avg score**: {avg_score:.0f}")
            else:
                lines.append("No relevant Reddit posts found.")
        except Exception as e:
            lines.append(f"Reddit data unavailable: {e}")
    else:
        lines.append("Reddit API keys not configured. Skipping Reddit data.")

    if len(lines) == 1:
        lines.append("No social media data sources configured. Set TWITTER_BEARER_TOKEN and/or REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in .env.")

    return "\n".join(lines)


@tool
def search_markets(
    min_volume: int = 10000,
    min_liquidity: int = 5000,
    max_days_to_end: int = 30,
    category: str = "",
    limit: int = 20,
) -> str:
    """Search for active Polymarket events matching criteria.

    Args:
        min_volume: Minimum 24h volume.
        min_liquidity: Minimum liquidity.
        max_days_to_end: Maximum days until event end.
        category: Filter by tag/category (empty = all).
        limit: Max results.
    """
    try:
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false",
        }
        if category:
            params["tag_id"] = category

        data = _api_get(f"{GAMMA_BASE}/events", params=params)
        events = data if isinstance(data, list) else []

        lines = ["# Market Scan Results\n"]
        lines.append(f"Filters: min_volume={min_volume}, min_liquidity={min_liquidity}, max_days={max_days_to_end}\n")

        count = 0
        for evt in events:
            markets = evt.get("markets", [])
            for m in markets:
                vol24 = m.get("volume24hr", 0) or 0
                liq = m.get("liquidity", 0) or 0
                if float(vol24) < min_volume or float(liq) < min_liquidity:
                    continue

                prices = m.get("outcomePrices", "[]")
                if isinstance(prices, str):
                    prices = json.loads(prices)

                count += 1
                lines.append(f"## {count}. {m.get('question', evt.get('title', 'N/A'))}")
                lines.append(f"- **Event ID**: {evt.get('id', 'N/A')}")
                lines.append(f"- **Market ID**: {m.get('id', 'N/A')}")
                lines.append(f"- **Prices**: {prices}")
                lines.append(f"- **24h Volume**: ${float(vol24):,.0f}")
                lines.append(f"- **Liquidity**: ${float(liq):,.0f}")
                lines.append(f"- **End Date**: {m.get('endDate', evt.get('endDate', 'N/A'))}")
                lines.append("")

        if count == 0:
            lines.append("No markets matching the criteria found.")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching markets: {e}. Data unavailable."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_polymarket_tools.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/polymarket_tools.py tests/test_polymarket_tools.py
git commit -m "feat: add Polymarket API tool functions with tests"
```

---

## Task 3: Agent State Definitions

**Files:**
- Modify: `tradingagents/agents/utils/agent_states.py:11-77`
- Create: `tests/test_agent_states.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_states.py`:

```python
"""Tests for updated agent state definitions."""


def test_invest_debate_state_has_timing_fields():
    from tradingagents.agents.utils.agent_states import InvestDebateState
    keys = InvestDebateState.__annotations__
    assert "yes_history" in keys
    assert "no_history" in keys
    assert "timing_history" in keys
    assert "latest_speaker" in keys
    assert "current_yes_response" in keys
    assert "current_no_response" in keys
    assert "current_timing_response" in keys
    # Old fields should not exist
    assert "bull_history" not in keys
    assert "bear_history" not in keys


def test_agent_state_has_polymarket_fields():
    from tradingagents.agents.utils.agent_states import AgentState
    keys = AgentState.__annotations__
    assert "event_id" in keys
    assert "event_question" in keys
    assert "odds_report" in keys
    assert "event_report" in keys
    assert "trader_plan" in keys
    assert "final_decision" in keys
    # Old fields should not exist
    assert "company_of_interest" not in keys
    assert "market_report" not in keys
    assert "fundamentals_report" not in keys
    assert "trader_investment_plan" not in keys
    assert "final_trade_decision" not in keys
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_agent_states.py -v`
Expected: FAIL (old field names still present)

- [ ] **Step 3: Update agent_states.py**

Replace the content of `tradingagents/agents/utils/agent_states.py`:

```python
from typing import Annotated, Sequence
import operator

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from typing_extensions import TypedDict


class InvestDebateState(TypedDict):
    """State for the YES/NO/Timing investment debate."""
    yes_history: str
    no_history: str
    timing_history: str
    history: str
    current_yes_response: str
    current_no_response: str
    current_timing_response: str
    latest_speaker: str
    judge_decision: str
    count: int


class RiskDebateState(TypedDict):
    """State for the Aggressive/Conservative/Neutral risk debate."""
    aggressive_history: str
    conservative_history: str
    neutral_history: str
    history: str
    latest_speaker: str
    current_aggressive_response: str
    current_conservative_response: str
    current_neutral_response: str
    judge_decision: str
    count: int


class AgentState(MessagesState):
    """Main agent state for Polymarket prediction analysis."""
    event_id: str
    event_question: str
    trade_date: str
    sender: str
    odds_report: str
    sentiment_report: str
    news_report: str
    event_report: str
    investment_debate_state: InvestDebateState
    investment_plan: str
    trader_plan: str
    risk_debate_state: RiskDebateState
    final_decision: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_agent_states.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/agent_states.py tests/test_agent_states.py
git commit -m "feat: update AgentState and InvestDebateState for Polymarket"
```

---

## Task 4: Conditional Logic (3-Way Debate Routing)

**Files:**
- Modify: `tradingagents/graph/conditional_logic.py:6-68`
- Create: `tests/test_conditional_logic.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_conditional_logic.py`:

```python
"""Tests for conditional logic routing."""


def test_debate_routes_yes_to_no():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {
        "investment_debate_state": {
            "count": 1,
            "latest_speaker": "YES Advocate",
        }
    }
    assert cl.should_continue_debate(state) == "NO Advocate"


def test_debate_routes_no_to_timing():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {
        "investment_debate_state": {
            "count": 2,
            "latest_speaker": "NO Advocate",
        }
    }
    assert cl.should_continue_debate(state) == "Timing Advocate"


def test_debate_routes_timing_to_yes():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=1)
    state = {
        "investment_debate_state": {
            "count": 3,
            "latest_speaker": "Timing Advocate",
        }
    }
    assert cl.should_continue_debate(state) == "YES Advocate"


def test_debate_routes_to_manager_after_max_rounds():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {
        "investment_debate_state": {
            "count": 3,  # 1 round * 3 speakers = 3
            "latest_speaker": "Timing Advocate",
        }
    }
    assert cl.should_continue_debate(state) == "Research Manager"


def test_debate_initial_routes_to_yes():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {
        "investment_debate_state": {
            "count": 0,
            "latest_speaker": "",
        }
    }
    assert cl.should_continue_debate(state) == "YES Advocate"


def test_should_continue_odds_routes_to_tools():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    # Simulate state with tool calls
    from unittest.mock import MagicMock
    msg = MagicMock()
    msg.tool_calls = [{"name": "get_market_data", "args": {}}]
    state = {"messages": [msg]}
    assert cl.should_continue_odds(state) == "tools_odds"


def test_should_continue_odds_routes_to_clear():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    from unittest.mock import MagicMock
    msg = MagicMock()
    msg.tool_calls = []
    state = {"messages": [msg]}
    assert cl.should_continue_odds(state) == "Msg Clear Odds"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_conditional_logic.py -v`
Expected: FAIL

- [ ] **Step 3: Update conditional_logic.py**

Replace `tradingagents/graph/conditional_logic.py`:

```python
"""Conditional routing logic for the trading agents graph."""

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional routing decisions in the graph."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_odds(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_odds"
        return "Msg Clear Odds"

    def should_continue_social(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_event(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_event"
        return "Msg Clear Event"

    def should_continue_debate(self, state):
        """Route 3-way YES/NO/Timing debate. Mirrors risk debate pattern."""
        count = state["investment_debate_state"]["count"]
        if count >= 3 * self.max_debate_rounds:
            return "Research Manager"
        latest = state["investment_debate_state"].get("latest_speaker", "")
        if latest.startswith("YES"):
            return "NO Advocate"
        elif latest.startswith("NO"):
            return "Timing Advocate"
        else:
            return "YES Advocate"

    def should_continue_risk_analysis(self, state):
        """Route 3-way risk debate. Unchanged from original."""
        count = state["risk_debate_state"]["count"]
        if count >= 3 * self.max_risk_discuss_rounds:
            return "Risk Judge"
        latest = state["risk_debate_state"].get("latest_speaker", "")
        if latest.startswith("Aggressive"):
            return "Conservative Analyst"
        elif latest.startswith("Conservative"):
            return "Neutral Analyst"
        else:
            return "Aggressive Analyst"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_conditional_logic.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/conditional_logic.py tests/test_conditional_logic.py
git commit -m "feat: update conditional logic for 3-way YES/NO/Timing debate"
```

---

## Task 5: Agent Prompts — Analysts

**Files:**
- Create: `tradingagents/agents/analysts/odds_analyst.py`
- Create: `tradingagents/agents/analysts/event_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/social_media_analyst.py`

- [ ] **Step 1: Create odds_analyst.py**

Create `tradingagents/agents/analysts/odds_analyst.py` based on the structure of `market_analyst.py`, but with Polymarket-specific prompt and tools (`get_market_data`, `get_price_history`, `get_orderbook`). The prompt should instruct the analyst to analyze prediction market odds, price trends, orderbook asymmetry, volume patterns, and spread changes. Output a Markdown table summary.

- [ ] **Step 2: Create event_analyst.py**

Create `tradingagents/agents/analysts/event_analyst.py` based on the structure of `fundamentals_analyst.py`, but with tools (`get_event_details`, `get_market_stats`, `get_leaderboard_signals`). The prompt should analyze resolution criteria, deadline proximity, base probability estimation, and top trader signals.

- [ ] **Step 3: Update news_analyst.py**

Replace tool bindings: `get_news` → `get_event_news`, `get_global_news` stays. Update prompt: "news researcher tasked with analyzing recent news" → "news researcher analyzing news relevant to a Polymarket prediction event". Remove `get_insider_transactions`.

- [ ] **Step 4: Update social_media_analyst.py**

Replace tool bindings: `get_news` → `get_social_sentiment`, `get_whale_activity`. Update prompt to focus on social media opinion, whale positions, and smart money signals for prediction markets.

- [ ] **Step 5: Verify all 4 analysts import correctly**

Run: `source .venv/bin/activate && python -c "from tradingagents.agents.analysts.odds_analyst import create_odds_analyst; from tradingagents.agents.analysts.event_analyst import create_event_analyst; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/analysts/
git commit -m "feat: add Polymarket analyst agents (odds, event, news, social)"
```

---

## Task 6: Agent Prompts — Researchers (3-Way Debate)

**Files:**
- Create: `tradingagents/agents/researchers/yes_advocate.py`
- Create: `tradingagents/agents/researchers/no_advocate.py`
- Create: `tradingagents/agents/researchers/timing_advocate.py`
- Modify: `tradingagents/agents/managers/research_manager.py`

- [ ] **Step 1: Create yes_advocate.py**

Based on `bull_researcher.py` structure. Replace "Bull Analyst advocating for investing in the stock" → "YES Advocate arguing that the event WILL occur." Read `no_history`, `timing_history`, `yes_history`. Write only `yes_history`, `current_yes_response`, `latest_speaker = "YES Advocate"`. Use `event_question` in prompt. Reference `odds_report`, `sentiment_report`, `news_report`, `event_report`.

- [ ] **Step 2: Create no_advocate.py**

Based on `bear_researcher.py`. Replace "Bear Analyst" → "NO Advocate arguing the event will NOT occur." Same 3-way state preservation pattern. Write `no_history`, `current_no_response`, `latest_speaker = "NO Advocate"`.

- [ ] **Step 3: Create timing_advocate.py**

New agent. Same structure as yes/no advocates. Prompt: "Timing Advocate analyzing whether the current market price accurately reflects the probability. Even if the outcome is likely YES or NO, the market may have already priced it in. Focus on: edge vs current odds, time decay, market efficiency, liquidity traps." Write `timing_history`, `current_timing_response`, `latest_speaker = "Timing Advocate"`.

- [ ] **Step 4: Update research_manager.py**

Update prompt: 3-way debate evaluation (YES/NO/Timing). Read `yes_history`, `no_history`, `timing_history`. The recommendation should include confidence level and estimated probability, not just BUY/SELL/HOLD.

- [ ] **Step 5: Verify imports**

Run: `source .venv/bin/activate && python -c "from tradingagents.agents.researchers.yes_advocate import create_yes_advocate; from tradingagents.agents.researchers.no_advocate import create_no_advocate; from tradingagents.agents.researchers.timing_advocate import create_timing_advocate; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/researchers/ tradingagents/agents/managers/research_manager.py
git commit -m "feat: add 3-way YES/NO/Timing debate agents"
```

---

## Task 7: Agent Prompts — Trader and Risk Team

**Files:**
- Modify: `tradingagents/agents/trader/trader.py`
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`
- Modify: `tradingagents/agents/managers/risk_manager.py`

- [ ] **Step 1: Update trader.py**

Change prompt: "trading agent analyzing market data to make investment decisions" → "prediction market trader analyzing event probability to make betting decisions." Output format: "FINAL PREDICTION: **YES/NO/SKIP** | Confidence: X.X | Edge: X.X". Reference `odds_report`, `event_report`, `investment_plan`, `trader_plan`.

- [ ] **Step 2: Update aggressive_debator.py**

Change prompt context from stock trading to prediction market betting. Reference `odds_report`, `event_report` instead of `market_report`, `fundamentals_report`. Reference `trader_plan` instead of `trader_investment_plan`.

- [ ] **Step 3: Update conservative_debator.py**

Same field name changes as aggressive. Prompt stays conservative risk perspective.

- [ ] **Step 4: Update neutral_debator.py**

Same field name changes. Prompt stays neutral/balanced.

- [ ] **Step 5: Update risk_manager.py**

Update prompt to reference prediction market context. Field name: `trader_plan`. Output should produce structured reasoning for `final_decision`.

- [ ] **Step 6: Verify imports**

Run: `source .venv/bin/activate && python -c "from tradingagents.agents.trader.trader import create_trader; from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add tradingagents/agents/trader/ tradingagents/agents/risk_mgmt/ tradingagents/agents/managers/risk_manager.py
git commit -m "feat: update trader and risk team prompts for Polymarket"
```

---

## Task 8: Agent Exports and Tool Imports

**Files:**
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`

- [ ] **Step 1: Update agent_utils.py**

Replace all stock tool imports with Polymarket tool imports:

```python
from langchain_core.messages import HumanMessage, RemoveMessage
from tradingagents.agents.utils.agent_states import AgentState

from tradingagents.agents.utils.polymarket_tools import (
    get_market_data,
    get_price_history,
    get_event_news,
    get_global_news,
    get_whale_activity,
    get_event_details,
    get_orderbook,
    get_market_stats,
    get_leaderboard_signals,
    get_social_sentiment,
)


def create_msg_delete():
    """Create a message deletion node."""
    def msg_delete(state: AgentState):
        return {"messages": [RemoveMessage(id=m.id) for m in state["messages"]]}
    return msg_delete
```

- [ ] **Step 2: Update agents/__init__.py**

```python
from .utils.agent_utils import create_msg_delete
from .utils.agent_states import AgentState, InvestDebateState, RiskDebateState
from .utils.memory import FinancialSituationMemory

from .analysts.odds_analyst import create_odds_analyst
from .analysts.social_media_analyst import create_social_media_analyst
from .analysts.news_analyst import create_news_analyst
from .analysts.event_analyst import create_event_analyst

from .researchers.yes_advocate import create_yes_advocate
from .researchers.no_advocate import create_no_advocate
from .researchers.timing_advocate import create_timing_advocate

from .managers.research_manager import create_research_manager
from .managers.risk_manager import create_risk_manager

from .risk_mgmt.aggressive_debator import create_aggressive_debator
from .risk_mgmt.conservative_debator import create_conservative_debator
from .risk_mgmt.neutral_debator import create_neutral_debator

from .trader.trader import create_trader

__all__ = [
    "FinancialSituationMemory",
    "AgentState",
    "InvestDebateState",
    "RiskDebateState",
    "create_msg_delete",
    "create_yes_advocate",
    "create_no_advocate",
    "create_timing_advocate",
    "create_research_manager",
    "create_odds_analyst",
    "create_event_analyst",
    "create_news_analyst",
    "create_social_media_analyst",
    "create_neutral_debator",
    "create_aggressive_debator",
    "create_conservative_debator",
    "create_risk_manager",
    "create_trader",
]
```

- [ ] **Step 3: Verify all exports import**

Run: `source .venv/bin/activate && python -c "from tradingagents.agents import *; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tradingagents/agents/__init__.py tradingagents/agents/utils/agent_utils.py
git commit -m "feat: update agent exports for Polymarket agents"
```

---

## Task 9: Graph Workflow (setup.py, propagation.py, trading_graph.py)

**Files:**
- Modify: `tradingagents/graph/setup.py:14-202`
- Modify: `tradingagents/graph/propagation.py:11-70`
- Modify: `tradingagents/graph/trading_graph.py`

- [ ] **Step 1: Update propagation.py**

Update `create_initial_state` to use new field names:
- `company_of_interest` → `event_id`
- Add `event_question`
- `market_report` → `odds_report`, `fundamentals_report` → `event_report`
- `trader_investment_plan` → `trader_plan`
- `final_trade_decision` → `final_decision`
- `InvestDebateState`: add `timing_history`, `latest_speaker`, `current_yes_response`, `current_no_response`, `current_timing_response`. Remove `bull_history`, `bear_history`, `current_response`.
- Method signature: `create_initial_state(self, event_id, event_question, trade_date)`

- [ ] **Step 2: Update setup.py**

Major rewrite:
- Replace analyst node names: `"Market Analyst"` → `"Odds Analyst"`, `"Fundamentals Analyst"` → `"Event Analyst"`
- Replace researcher nodes: `"Bull Researcher"` → `"YES Advocate"`, `"Bear Researcher"` → `"NO Advocate"`, add `"Timing Advocate"`
- Update `__init__` to accept `timing_memory`
- Update all `add_node`, `add_edge`, `add_conditional_edges` calls
- 3-way debate edges: YES → {NO, Manager}, NO → {Timing, Manager}, Timing → {YES, Manager}
- Tool node keys: `"market"` → `"odds"`, `"fundamentals"` → `"event"`

- [ ] **Step 3: Update trading_graph.py**

- Update imports at top of file: replace all stock tool imports (lines 24-34) with Polymarket tool imports from `tradingagents.agents.utils.agent_utils`
- `_create_tool_nodes`: use new Polymarket tools
- Add `timing_memory = FinancialSituationMemory("timing_memory", self.config)`
- Pass `timing_memory` to `GraphSetup`
- Update `_log_state`: all field names
- Update `propagate` signature: `(self, event_id, event_question, trade_date)`
- Update `reflect_and_remember`: add `reflect_timing_advocate`
- `process_signal`: reference `final_decision`

- [ ] **Step 4: Verify graph compiles**

Run: `source .venv/bin/activate && python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"`
Expected: `OK` (may warn about missing API keys, but should not error)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/
git commit -m "feat: update graph workflow for Polymarket 3-way debate"
```

---

## Task 10: Signal Processing and Reflection

**Files:**
- Modify: `tradingagents/graph/signal_processing.py:6-31`
- Modify: `tradingagents/graph/reflection.py:7-122`
- Create: `tests/test_signal_processing.py`

- [ ] **Step 1: Write failing test for signal processing**

Create `tests/test_signal_processing.py`:

```python
"""Tests for Polymarket signal processing."""
import json


def test_process_signal_extracts_yes():
    from tradingagents.graph.signal_processing import SignalProcessor
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content='{"action": "YES", "confidence": 0.75, "edge": 0.1, "position_size": 0.05, "reasoning": "Strong evidence", "time_horizon": "2 weeks"}')

    processor = SignalProcessor(mock_llm)
    result = processor.process_signal("Some long analysis text recommending YES")
    parsed = json.loads(result)
    assert parsed["action"] == "YES"
    assert parsed["confidence"] == 0.75


def test_process_signal_handles_invalid_response():
    from tradingagents.graph.signal_processing import SignalProcessor
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="This is not JSON")

    processor = SignalProcessor(mock_llm)
    result = processor.process_signal("Some analysis")
    parsed = json.loads(result)
    assert parsed["action"] in ("YES", "NO", "SKIP")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_signal_processing.py -v`
Expected: FAIL

- [ ] **Step 3: Update signal_processing.py**

Replace `tradingagents/graph/signal_processing.py`:

```python
"""Signal processing for extracting structured prediction decisions."""

import json
import re


class SignalProcessor:
    """Processes raw LLM output into structured prediction decisions."""

    def __init__(self, quick_thinking_llm):
        self.llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """Extract structured JSON decision from the final trade decision text.

        Returns a JSON string with: action, confidence, edge, position_size, reasoning, time_horizon.
        """
        prompt = f"""Extract the final prediction decision from the following analysis.
Return ONLY a valid JSON object with these exact fields:
- "action": one of "YES", "NO", or "SKIP"
- "confidence": a float between 0.0 and 1.0
- "edge": estimated probability minus market price (float, can be negative)
- "position_size": recommended bet size as fraction of bankroll (float 0.0-1.0)
- "reasoning": one sentence summary
- "time_horizon": time until event resolution

Analysis:
{full_signal}

Return ONLY the JSON object, no other text."""

        response = self.llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Try to parse JSON from response
        try:
            # Find JSON in response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                # Validate required fields
                required = ["action", "confidence", "edge", "position_size", "reasoning", "time_horizon"]
                if all(k in parsed for k in required):
                    # Normalize action
                    parsed["action"] = parsed["action"].upper().strip()
                    if parsed["action"] not in ("YES", "NO", "SKIP"):
                        parsed["action"] = "SKIP"
                    return json.dumps(parsed)
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: extract what we can from text
        action = "SKIP"
        text_upper = content.upper()
        if "YES" in text_upper and "NO" not in text_upper:
            action = "YES"
        elif "NO" in text_upper and "YES" not in text_upper:
            action = "NO"

        return json.dumps({
            "action": action,
            "confidence": 0.5,
            "edge": 0.0,
            "position_size": 0.0,
            "reasoning": "Could not parse structured output from LLM response.",
            "time_horizon": "unknown",
        })
```

- [ ] **Step 4: Update reflection.py**

In `tradingagents/graph/reflection.py`:
- Rename `reflect_bull_researcher` → `reflect_yes_advocate`
- Rename `reflect_bear_researcher` → `reflect_no_advocate`
- Add `reflect_timing_advocate` (same pattern)
- In `_extract_current_situation`: `market_report` → `odds_report`, `fundamentals_report` → `event_report`
- In `reflect_trader`: `current_state["trader_investment_plan"]` → `current_state["trader_plan"]`
- **Disable reflection for Phase 1**: In `trading_graph.py`, make `reflect_and_remember` a no-op:

```python
def reflect_and_remember(self, returns_losses):
    """Disabled in Phase 1 (no realized returns for prediction markets)."""
    pass
```

- [ ] **Step 5: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_signal_processing.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tradingagents/graph/signal_processing.py tradingagents/graph/reflection.py tests/test_signal_processing.py
git commit -m "feat: update signal processing for structured JSON output"
```

---

## Task 11: CLI Updates

**Files:**
- Modify: `cli/models.py:6-10`
- Modify: `cli/utils.py`
- Modify: `cli/main.py`

- [ ] **Step 1: Update cli/models.py**

```python
from enum import Enum


class AnalystType(str, Enum):
    ODDS = "odds"
    SOCIAL = "social"
    NEWS = "news"
    EVENT = "event"
```

- [ ] **Step 2: Update cli/utils.py**

- `ANALYST_ORDER`: `[("Odds Analyst", AnalystType.ODDS), ("Social Media Analyst", AnalystType.SOCIAL), ("News Analyst", AnalystType.NEWS), ("Event Analyst", AnalystType.EVENT)]`
- Replace `get_ticker()` with `get_event_input()` — two modes: Manual (event URL/ID) and Scan (filters → select from results)
- `get_analysis_date()` can remain as-is (used for context)
- Keep `select_analysts`, `select_research_depth`, `select_llm_provider`, model selections as-is

- [ ] **Step 3: Update cli/main.py**

- `MessageBuffer.FIXED_AGENTS`: Research Team → `["YES Advocate", "NO Advocate", "Timing Advocate", "Research Manager"]`
- `MessageBuffer.ANALYST_MAPPING`: `{"odds": "Odds Analyst", "social": "Social Analyst", "news": "News Analyst", "event": "Event Analyst"}`
- `MessageBuffer.REPORT_SECTIONS`: `odds_report`, `event_report`, `trader_plan`, `final_decision`
- `ANALYST_ORDER`: `["odds", "social", "news", "event"]`
- `ANALYST_AGENT_NAMES`: update accordingly
- `ANALYST_REPORT_MAP`: `{"odds": "odds_report", "social": "sentiment_report", "news": "news_report", "event": "event_report"}`
- Update `run_analysis()`:
  - `selections["ticker"]` → `selections["event_id"]` + `selections["event_question"]`
  - `graph.propagate(event_id, event_question, date)` call
  - Update `investment_debate_state` chunk processing: `bull_history` → `yes_history`, `bear_history` → `no_history`, add `timing_history`
  - Update `trader_investment_plan` → `trader_plan`
  - Update `final_trade_decision` → `final_decision`
  - Update `risk_debate_state` references
- Update `display_complete_report()`: section titles and field names
- Update `save_report_to_disk()`: field names and folder structure

- [ ] **Step 4: Verify CLI loads without error**

Run: `source .venv/bin/activate && python -c "from cli.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add cli/
git commit -m "feat: update CLI for Polymarket event input and display"
```

---

## Task 12: Cleanup Old Files

**Files:**
- Delete: `tradingagents/agents/researchers/bull_researcher.py`
- Delete: `tradingagents/agents/researchers/bear_researcher.py`
- Delete: `tradingagents/agents/analysts/market_analyst.py`
- Delete: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Delete: `tradingagents/agents/utils/core_stock_tools.py`
- Delete: `tradingagents/agents/utils/technical_indicators_tools.py`
- Delete: `tradingagents/agents/utils/fundamental_data_tools.py`
- Delete: `tradingagents/agents/utils/news_data_tools.py`

- [ ] **Step 1: Verify no remaining imports of old files**

Run: `source .venv/bin/activate && grep -r "bull_researcher\|bear_researcher\|market_analyst\|fundamentals_analyst\|core_stock_tools\|technical_indicators_tools\|fundamental_data_tools\|news_data_tools" tradingagents/ cli/ --include="*.py" -l`
Expected: No results (or only the files being deleted)

- [ ] **Step 2: Delete old files**

```bash
rm tradingagents/agents/researchers/bull_researcher.py
rm tradingagents/agents/researchers/bear_researcher.py
rm tradingagents/agents/analysts/market_analyst.py
rm tradingagents/agents/analysts/fundamentals_analyst.py
rm tradingagents/agents/utils/core_stock_tools.py
rm tradingagents/agents/utils/technical_indicators_tools.py
rm tradingagents/agents/utils/fundamental_data_tools.py
rm tradingagents/agents/utils/news_data_tools.py
```

- [ ] **Step 3: Run all tests**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove old stock-specific agent and tool files"
```

---

## Task 13: End-to-End Integration Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_integration.py`:

```python
"""End-to-end integration test for Polymarket agent."""
import pytest
from unittest.mock import MagicMock, patch


def test_graph_compiles_with_all_analysts():
    """Verify the graph compiles without errors."""
    with patch("tradingagents.graph.trading_graph.create_llm_client") as mock_client:
        mock_llm = MagicMock()
        mock_client.return_value = MagicMock(get_llm=lambda: mock_llm)

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        graph = TradingAgentsGraph(
            selected_analysts=["odds", "social", "news", "event"],
            debug=False,
        )
        assert graph.graph is not None


def test_initial_state_has_correct_fields():
    """Verify initial state matches AgentState schema."""
    from tradingagents.graph.propagation import Propagator
    prop = Propagator()
    state = prop.create_initial_state("test-event-id", "Will X happen?", "2026-03-21")

    assert state["event_id"] == "test-event-id"
    assert state["event_question"] == "Will X happen?"
    assert "odds_report" in state
    assert "event_report" in state
    assert "timing_history" in state["investment_debate_state"]
    assert "latest_speaker" in state["investment_debate_state"]
```

- [ ] **Step 2: Run integration test**

Run: `source .venv/bin/activate && python -m pytest tests/test_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration tests"
```

---

## Task 14: Live Smoke Test

- [ ] **Step 1: Create a simple smoke test script**

Create `smoke_test.py`:

```python
"""Smoke test: run Polymarket agent on a real event."""
from dotenv import load_dotenv
load_dotenv()

from tradingagents.agents.utils.polymarket_tools import search_markets, get_market_data

# Test 1: Search for active markets
print("=== Market Search ===")
results = search_markets(min_volume=50000, limit=5)
print(results[:2000])

# Test 2: Get data for a specific market (if any found)
print("\n=== Market Data ===")
# Use a known active event or pick from search results
data = get_market_data(event_id="will-donald-trump-be-president-on-december-31-2026")
print(data[:2000])
```

- [ ] **Step 2: Run smoke test**

Run: `source .venv/bin/activate && python smoke_test.py`
Expected: Real Polymarket data printed (market search results + event details)

- [ ] **Step 3: If smoke test passes, run full agent on a real event**

Run the CLI: `source .venv/bin/activate && python -m cli.main`
Select Manual mode, enter an active event, run analysis.

- [ ] **Step 4: Delete smoke_test.py and commit**

```bash
rm smoke_test.py
git add -A
git commit -m "chore: cleanup after successful smoke test"
```
