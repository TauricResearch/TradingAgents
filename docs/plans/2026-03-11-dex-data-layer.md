# DEX Data Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create DEX data layer for TradingAgents - enabling crypto token analysis instead of traditional stocks. Phase 1 targets CoinGecko provider with core OHLCV and token info tools.

**Architecture:** Priority-based iterative providers. Phase 1: CoinGecko (market data). Phase 2: DeFiLlama (TVL). Phase 3: Birdeye (whale tracking). Maintains existing LangGraph agent structure.

**Tech Stack:** Python, LangGraph, CoinGecko API, yfinance (existing), stockstats (technical indicators)

---

## Prerequisites

- Ensure `.env` has CoinGecko API key (free tier: 10-30 calls/min)
- Or set: `export COINGECKO_API_KEY=your_key` (optional for free endpoints)

---

# Phase 1: CoinGecko Provider

## Task 1: Create DEX Provider Directory Structure

**Files:**
- Create: `tradingagents/dataflows/dex/__init__.py`

**Step 1: Create the directory and init file**

```python
# tradingagents/dataflows/dex/__init__.py
"""DEX Data Providers for TradingAgents."""

from .coingecko_provider import CoinGeckoProvider, get_coin_ohlcv, get_coin_info

__all__ = ["CoinGeckoProvider", "get_coin_ohlcv", "get_coin_info"]
```

**Step 2: Commit**
```bash
git add tradingagents/dataflows/dex/__init__.py
git commit -m "feat(dex): create DEX dataflows directory structure"
```

---

## Task 2: Create CoinGecko Provider

**Files:**
- Create: `tradingagents/dataflows/dex/coingecko_provider.py`
- Modify: `tradingagents/dataflows/dex/__init__.py`

**Step 1: Write the failing test**

Run: `pytest tradingagents/dataflows/dex/test_coingecko.py -v` (will fail - file doesn't exist yet)

```python
# tradingagents/dataflows/dex/test_coingecko.py
import pytest
from tradingagents.dataflows.dex.coingecko_provider import get_coin_ohlcv, get_coin_info

@pytest.mark.asyncio
async def test_get_coin_ohlcv_returns_data():
    """Test that get_coin_ohlcv returns OHLCV data for SOL."""
    result = await get_coin_ohlcv("solana", "usd", 7)
    assert " timestamp " in result.lower() or "open" in result.lower()
    assert len(result) > 100

@pytest.mark.asyncio
async def test_get_coin_info_returns_metadata():
    """Test that get_coin_info returns token metadata."""
    result = await get_coin_info("solana")
    assert "solana" in result.lower()
    assert "market_cap" in result.lower() or "$" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tradingagents/dataflows/dex/test_coingecko.py -v`
Expected: FAIL -ModuleNotFoundError

**Step 3: Write the CoinGecko provider implementation**

```python
# tradingagents/dataflows/dex/coingecko_provider.py
"""CoinGecko API provider for DEX data."""

import os
from typing import Optional
import httpx
import pandas as pd
from datetime import datetime, timedelta

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

class CoinGeckoProvider:
    """Provider for CoinGecko API calls."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINGECKO_API_KEY")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated GET request to CoinGecko."""
        headers = {}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key

        params = params or {}
        response = await self.client.get(
            f"{COINGECKO_BASE_URL}{endpoint}",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_ohlc(self, coin_id: str, vs_currency: str = "usd", days: int = 7) -> list:
        """Get OHLC data for a coin."""
        return await self._get(
            f"/coins/{coin_id}/ohlc",
            params={"vs_currency": vs_currency, "days": days}
        )

    async def get_coin_data(self, coin_id: str) -> dict:
        """Get detailed coin data including market info."""
        return await self._get(
            f"/coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false"
            }
        )


# Global provider instance
_provider: Optional[CoinGeckoProvider] = None

def _get_provider() -> CoinGeckoProvider:
    global _provider
    if _provider is None:
        _provider = CoinGeckoProvider()
    return _provider


async def get_coin_ohlcv(coin_id: str, vs_currency: str = "usd", days: int = 7) -> str:
    """Get OHLCV data for a cryptocurrency token.

    Args:
        coin_id: CoinGecko coin ID (e.g., 'solana', 'bitcoin', 'ethereum')
        vs_currency: Target currency (default: 'usd')
        days: Number of days of data (1-365)

    Returns:
        Formatted OHLCV data string for LLM consumption
    """
    provider = _get_provider()
    try:
        ohlc_data = await provider.get_ohlc(coin_id, vs_currency, days)

        if not ohlc_data:
            return f"No OHLCV data available for {coin_id}"

        # Convert to readable format
        lines = [f"OHLCV Data for {coin_id.upper()} (last {days} days)"]
        lines.append("=" * 60)

        for i, (timestamp, open_val, high, low, close) in enumerate(ohlc_data):
            date = datetime.fromtimestamp(timestamp // 1000)
            date_str = date.strftime("%Y-%m-%d")
            lines.append(
                f"{date_str} | O: {open_val:>10.2f} | H: {high:>10.2f} | "
                f"L: {low:>10.2f} | C: {close:>10.2f}"
            )

        # Calculate summary
        closes = [row[4] for row in ohlc_data]
        if closes:
            price_change = ((closes[-1] - closes[0]) / closes[0]) * 100
            lines.append("")
            lines.append(f"Price Change: {price_change:+.2f}%")
            lines.append(f"High: ${max(closes):.2f} | Low: ${min(closes):.2f}")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error fetching OHLCV data: {e.response.status_code}"
    except Exception as e:
        return f"Error fetching OHLCV data: {str(e)}"


async def get_coin_info(coin_id: str) -> str:
    """Get token metadata and market data.

    Args:
        coin_id: CoinGecko coin ID (e.g., 'solana', 'bitcoin')

    Returns:
        Formatted token info string for LLM consumption
    """
    provider = _get_provider()
    try:
        data = await provider.get_coin_data(coin_id)

        if not data:
            return f"No data available for {coin_id}"

        market = data.get("market_data", {})
        lines = [f"Token Information: {data.get('name', coin_id).upper()} ({data.get('symbol', '').upper()})"]
        lines.append("=" * 60)

        # Market data
        current_price = market.get("current_price", {}).get("usd", 0)
        lines.append(f"Current Price: ${current_price:,.2f}")

        market_cap = market.get("market_cap", {}).get("usd", 0)
        lines.append(f"Market Cap: ${market_cap:,.0f}")

        volume = market.get("total_volume", {}).get("usd", 0)
        lines.append(f"24h Volume: ${volume:,.0f}")

        # Price changes
        for period, key in [("24h", "price_change_percentage_24h"),
                           ("7d", "price_change_percentage_7d"),
                           ("30d", "price_change_percentage_30d")]:
            change = market.get(key, 0)
            if change is not None:
                lines.append(f"{period} Change: {change:+.2f}%")

        # Supply
        supply = market.get("circulating_supply", 0)
        if supply:
            lines.append(f"Circulating Supply: {supply:,.0f} {data.get('symbol', '').upper()}")

        total_supply = market.get("total_supply", 0)
        if total_supply:
            lines.append(f"Total Supply: {total_supply:,.0f}")

        max_supply = market.get("max_supply", 0)
        if max_supply:
            lines.append(f"Max Supply: {max_supply:,.0f}")

        # ATH/ATL
        ath = market.get("ath", {}).get("usd", 0)
        ath_change = market.get("ath_change_percentage", {}).get("usd", 0)
        if ath:
            lines.append(f"All-Time High: ${ath:,.2f} ({ath_change:.2f}% from ATH)")

        atl = market.get("atl", {}).get("usd", 0)
        atl_change = market.get("atl_change_percentage", {}).get("usd", 0)
        if atl:
            lines.append(f"All-Time Low: ${atl:,.2f} ({atl_change:+.2f}% from ATL)")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error fetching token info: {e.response.status_code}"
    except Exception as e:
        return f"Error fetching token info: {str(e)}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tradingagents/dataflows/dex/test_coingecko.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add tradingagents/dataflows/dex/coingecko_provider.py tradingagents/dataflows/dex/__init__.py
git commit -m "feat(dex): add CoinGecko provider with OHLCV and token info"
```

---

## Task 3: Add DEX Routing to Interface

**Files:**
- Modify: `tradingagents/dataflows/interface.py:1-50`

**Step 1: Read existing interface.py to understand current routing**

Run: `head -80 tradingagents/dataflows/interface.py`

**Step 2: Add DEX vendor constants**

```python
# Add after existing VENDOR_LIST definition
DEX_VENDOR_LIST = ["coingecko", "defillama", "birdeye"]

# Tool categories for DEX
DEX_TOOLS_CATEGORIES = {
    "core_token_apis": {
        "tools": ["get_token_ohlcv"],
        "default": "coingecko"
    },
    "token_info": {
        "tools": ["get_token_info"],
        "default": "coingecko"
    },
    "technical_indicators": {
        "tools": ["get_token_indicators"],
        "default": "coingecko"
    },
    "defi_fundamentals": {
        "tools": ["get_pool_data", "get_token_info"],
        "default": "defillama"
    },
    "whale_tracking": {
        "tools": ["get_whale_transactions"],
        "default": "birdeye"
    },
}
```

**Step 3: Commit**
```bash
git add tradingagents/dataflows/interface.py
git commit -m "feat(dex): add DEX vendor routing to interface"
```

---

## Task 4: Create DEX Tool Wrappers for Agents

**Files:**
- Create: `tradingagents/agents/utils/dex_tools.py`
- Modify: `tradingagents/agents/utils/__init__.py`

**Step 1: Write the failing test**

```python
# tradingagents/agents/utils/test_dex_tools.py
import pytest
from tradingagents.agents.utils.dex_tools import get_token_ohlcv, get_token_info

def test_get_token_ohlcv_is_valid_tool():
    """Verify get_token_ohlcv is a valid LangChain tool."""
    assert hasattr(get_token_ohlcv, 'name')
    assert get_token_ohlcv.name == "get_token_ohlcv"

def test_get_token_info_is_valid_tool():
    """Verify get_token_info is a valid LangChain tool."""
    assert hasattr(get_token_info, 'name')
    assert get_token_info.name == "get_token_info"
```

**Step 2: Run test to verify it fails**

Run: `pytest tradingagents/agents/utils/test_dex_tools.py -v`
Expected: FAIL - ModuleNotFoundError

**Step 3: Write the tool wrappers**

```python
# tradingagents/agents/utils/dex_tools.py
"""DEX tool wrappers for TradingAgents."""

from typing import Annotated
from langchain_core.tools import tool
from tradingagents.dataflows.dex.coingecko_provider import get_coin_ohlcv as _get_coin_ohlcv
from tradingagents.dataflows.dex.coingecko_provider import get_coin_info as _get_coin_info


@tool
def get_token_ohlcv(
    coin_id: Annotated[str, "CoinGecko ID (e.g., solana, bitcoin, ethereum)"],
    vs_currency: Annotated[str, "Target currency (default: usd)"] = "usd",
    days: Annotated[int, "Number of days (1-365, default: 7)"] = 7
) -> str:
    """Get OHLCV (Open-High-Low-Close-Volume) price data for a cryptocurrency token.

    Use this to analyze price movements, trends, and volatility.
    CoinGecko ID examples:
    - solana, bitcoin, ethereum, cardano, polygon, avalanche-2, chainlink

    Returns formatted OHLC data with price summary.
    """
    import asyncio
    return asyncio.run(_get_coin_ohlcv(coin_id, vs_currency, days))


@tool
def get_token_info(
    coin_id: Annotated[str, "CoinGecko ID (e.g., solana, bitcoin, ethereum)"]
) -> str:
    """Get comprehensive token metadata and market data.

    Includes: current price, market cap, volume, supply, ATH/ATL.
    Use this for fundamental analysis of cryptocurrency tokens.

    CoinGecko ID examples:
    - solana, bitcoin, ethereum, cardano, polygon, avalanche-2, chainlink
    """
    import asyncio
    return asyncio.run(_get_coin_info(coin_id))


@tool
def get_pool_data(
    pool_address: Annotated[str, "DEX pool contract address"],
    chain: Annotated[str, "Blockchain (solana, ethereum, bsc)"] = "solana"
) -> str:
    """Get DEX pool metrics: TVL, volume 24h, fees.

    Note: This requires DeFiLlama provider (Phase 2).
    Currently returns placeholder.
    """
    return "Pool data requires DeFiLlama provider (Phase 2). Use get_token_ohlcv for now."


@tool
def get_whale_transactions(
    token_address: Annotated[str, "Token contract address"],
    chain: Annotated[str, "Blockchain network"] = "solana",
    min_usd: Annotated[float, "Minimum USD value (default: 10000)"] = 10000
) -> str:
    """Track large holder (whale) movements.

    Note: This requires Birdeye provider (Phase 3).
    Currently returns placeholder.
    """
    return "Whale tracking requires Birdeye provider (Phase 3). Use get_token_ohlcv for now."
```

**Step 4: Run test to verify it passes**

Run: `pytest tradingagents/agents/utils/test_dex_tools.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add tradingagents/agents/utils/dex_tools.py
git commit -m "feat(dex): add DEX tool wrappers for agents"
```

---

## Task 5: Update Default Config for DEX

**Files:**
- Modify: `tradingagents/default_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
from tradingagents.default_config import DEFAULT_CONFIG

def test_default_config_has_dex_vendors():
    """Verify config supports DEX vendors."""
    assert "data_vendors" in DEFAULT_CONFIG
    assert "core_token_apis" in DEFAULT_CONFIG["data_vendors"]
    assert DEFAULT_CONFIG["data_vendors"]["core_token_apis"] == "coingecko"

def test_default_config_has_chain():
    """Verify config supports default chain."""
    assert "default_chain" in DEFAULT_CONFIG
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL - KeyError

**Step 3: Add DEX config options**

Update `tradingagents/default_config.py`:

```python
DEFAULT_CONFIG = {
    # ... existing settings ...

    # DEX-specific configuration (NEW)
    "data_vendors": {
        # Traditional finance (Stock data - existing)
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",

        # DEX/Crypto (NEW - overrides stock data)
        "core_token_apis": "coingecko",
        "token_info": "coingecko",
        "technical_indicators_dex": "coingecko",  # Uses stockstats for calculation
        "defi_fundamentals": "defillama",  # Phase 2
        "whale_tracking": "birdeye",  # Phase 3
    },

    # Default blockchain for DEX operations
    "default_chain": "solana",  # Options: solana, ethereum, bsc, arbitrum, etc.

    # Mode: "stock" or "dex"
    "trading_mode": "stock",  # Start with stock, user switches to "dex"
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add tradingagents/default_config.py
git commit -m "feat(dex): add DEX configuration to default config"
```

---

## Task 6: Update Market Analyst for DEX Mode

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py:1-80`

**Step 1: Read existing market analyst**

Run: `head -100 tradingagents/agents/analysts/market_analyst.py`

**Step 2: Add DEX mode prompt alternative**

```python
# Add after existing SYSTEM_PROMPT
DEX_MARKET_ANALYST_PROMPT = """You are an On-Chain Market Analyst specializing in cryptocurrency and DeFi tokens.

Your role is to analyze:
1. OHLCV data from DEX pools (price, volume, liquidity)
2. Technical indicators (RSI, MACD, Bollinger Bands) calculated from on-chain data
3. Token market structure (TVL, volume ratios)

When analyzing, consider:
- Price momentum and trend direction
- Volume anomalies (unusual buying/selling)
- Liquidity depth implications
- Comparison to similar tokens in the ecosystem

Provide insights in a structured format that helps traders make informed decisions.
"""
```

**Step 3: Modify the agent to support both modes**

In the MarketAnalyst class, update the initialization to accept trading_mode and select appropriate prompt.

**Step 4: Commit**
```bash
git add tradingagents/agents/analysts/market_analyst.py
git commit -m "feat(dex): add DEX mode prompt to market analyst"
```

---

# Phase 2: DeFiLlama Provider (Next Iteration)

After Phase 1 is verified working:

## Task 7: Add DeFiLlama Provider

**Files:**
- Create: `tradingagents/dataflows/dex/defillama_provider.py`
- Modify: `tradingagents/dataflows/dex/__init__.py`

```python
# Minimal implementation required:
# - get_tvl(protocol_name: str) -> str
# - get_pool_data(pool_address: str, chain: str) -> str
# - get_chain_volumes(chain: str) -> str
```

---

# Phase 3: Birdeye Provider (Next Iteration)

## Task 8: Add Birdeye Provider

**Files:**
- Create: `tradingagents/dataflows/dex/birdeye_provider.py`
- Modify: `tradingagents/dataflows/dex/__init__.py`

```python
# Minimal implementation required:
# - get_whale_transactions(token_address: str, chain: str, min_usd: float) -> str
# - get_token_security(token_address: str, chain: str) -> str
```

---

# Verification Commands

## Phase 1 Verification

```bash
# Test CoinGecko provider directly
python -c "
import asyncio
from tradingagents.dataflows.dex.coingecko_provider import get_coin_ohlcv, get_coin_info

async def test():
    ohlc = await get_coin_ohlcv('solana', 'usd', 7)
    print('OHLCV:', ohlc[:500])

    info = await get_coin_info('solana')
    print('INFO:', info[:500])

asyncio.run(test())
"

# Run full pipeline test
python -c "
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config['trading_mode'] = 'dex'
config['default_chain'] = 'solana'

ta = TradingAgentsGraph(debug=True, config=config)
state, decision = ta.propagate('solana', '2026-03-01')
print('Decision:', decision)
"
```

---

# Plan Complete

**Saved to:** `docs/plans/2026-03-11-dex-data-layer.md`

**Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
