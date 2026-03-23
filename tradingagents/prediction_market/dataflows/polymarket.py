"""Polymarket API client for prediction market data.

Uses the public Gamma API and CLOB API — no authentication required for read-only access.
"""

import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional

import requests


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

# Simple file-based cache
_CACHE_DIR = None


def _get_cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = os.path.join(
            os.path.dirname(__file__), "data_cache", "polymarket"
        )
        os.makedirs(_CACHE_DIR, exist_ok=True)
    return _CACHE_DIR


def _cache_key(prefix: str, **kwargs) -> str:
    raw = f"{prefix}:{json.dumps(kwargs, sort_keys=True)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str, max_age_seconds: int = 300):
    path = os.path.join(_get_cache_dir(), f"{key}.json")
    if os.path.exists(path):
        mtime = os.path.getmtime(path)
        if time.time() - mtime < max_age_seconds:
            with open(path, "r") as f:
                return json.load(f)
    return None


def _set_cached(key: str, data):
    path = os.path.join(_get_cache_dir(), f"{key}.json")
    with open(path, "w") as f:
        json.dump(data, f)


def _gamma_get(endpoint: str, params: Optional[dict] = None, cache_seconds: int = 300):
    """Make a GET request to the Gamma API with caching."""
    key = _cache_key("gamma", endpoint=endpoint, params=params)
    cached = _get_cached(key, cache_seconds)
    if cached is not None:
        return cached

    url = f"{GAMMA_BASE}{endpoint}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    _set_cached(key, data)
    return data


def _clob_get(endpoint: str, params: Optional[dict] = None, cache_seconds: int = 60):
    """Make a GET request to the CLOB API with caching."""
    key = _cache_key("clob", endpoint=endpoint, params=params)
    cached = _get_cached(key, cache_seconds)
    if cached is not None:
        return cached

    url = f"{CLOB_BASE}{endpoint}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    _set_cached(key, data)
    return data


def get_polymarket_market_info(market_id: str) -> str:
    """Get comprehensive info for a Polymarket market.

    Returns: question, outcomes, prices, volume, liquidity, dates, resolution info.
    """
    data = _gamma_get(f"/markets/{market_id}")

    if not data:
        return f"No market found with ID: {market_id}"

    outcomes = json.loads(data.get("outcomes", "[]")) if isinstance(data.get("outcomes"), str) else data.get("outcomes", [])
    prices = json.loads(data.get("outcomePrices", "[]")) if isinstance(data.get("outcomePrices"), str) else data.get("outcomePrices", [])

    lines = [
        f"Market: {data.get('question', 'N/A')}",
        f"Market ID: {data.get('id', market_id)}",
        f"Status: {'Active' if data.get('active') else 'Closed' if data.get('closed') else 'Unknown'}",
        f"Accepting Orders: {data.get('acceptingOrders', 'N/A')}",
        "",
        "Outcomes and Prices:",
    ]

    for i, outcome in enumerate(outcomes):
        price = prices[i] if i < len(prices) else "N/A"
        lines.append(f"  {outcome}: ${price} ({float(price)*100:.1f}% implied probability)" if price != "N/A" else f"  {outcome}: N/A")

    lines.extend([
        "",
        f"Total Volume: ${data.get('volumeNum', data.get('volume', 'N/A'))}",
        f"24h Volume: ${data.get('volume24hr', 'N/A')}",
        f"Liquidity: ${data.get('liquidityNum', data.get('liquidity', 'N/A'))}",
        f"Best Bid: {data.get('bestBid', 'N/A')}",
        f"Best Ask: {data.get('bestAsk', 'N/A')}",
        f"Last Trade Price: {data.get('lastTradePrice', 'N/A')}",
        "",
        f"End Date: {data.get('endDate', 'N/A')}",
        f"Category: {data.get('category', 'N/A')}",
        f"Negative Risk: {data.get('negRisk', False)}",
        f"Maker Fee: {data.get('makerBaseFee', 'N/A')} bps",
        f"Taker Fee: {data.get('takerBaseFee', 'N/A')} bps",
    ])

    # Add CLOB token IDs for reference
    clob_ids = json.loads(data.get("clobTokenIds", "[]")) if isinstance(data.get("clobTokenIds"), str) else data.get("clobTokenIds", [])
    if clob_ids:
        lines.append("")
        lines.append("CLOB Token IDs:")
        for i, tid in enumerate(clob_ids):
            outcome_name = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
            lines.append(f"  {outcome_name}: {tid}")

    return "\n".join(lines)


def get_polymarket_price_history(
    market_id: str, start_date: str, end_date: str
) -> str:
    """Get historical price/probability time series for a market.

    Uses the CLOB API /prices-history endpoint.
    The market_id should be a CLOB token ID for the YES outcome.
    """
    # First get market info to find the CLOB token ID
    market_data = _gamma_get(f"/markets/{market_id}")
    if not market_data:
        return f"No market found with ID: {market_id}"

    clob_ids = json.loads(market_data.get("clobTokenIds", "[]")) if isinstance(market_data.get("clobTokenIds"), str) else market_data.get("clobTokenIds", [])
    if not clob_ids:
        return "No CLOB token IDs found for this market."

    # Use the first token ID (YES outcome)
    token_id = clob_ids[0]

    # Convert dates to unix timestamps
    try:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD."

    params = {
        "market": token_id,
        "startTs": start_ts,
        "endTs": end_ts,
        "interval": "1d",
    }

    try:
        data = _clob_get("/prices-history", params=params, cache_seconds=300)
    except requests.exceptions.RequestException as e:
        return f"Price history unavailable for this market (API error: {e}). The market may be too new or the date range too large."

    history = data.get("history", [])
    if not history:
        return "No price history available for the specified period."

    lines = [
        f"Price History for: {market_data.get('question', market_id)}",
        f"Period: {start_date} to {end_date}",
        f"Data points: {len(history)}",
        "",
        "Date | YES Price | Implied Probability",
        "--- | --- | ---",
    ]

    for point in history:
        ts = point.get("t", 0)
        price = point.get("p", 0)
        dt = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        lines.append(f"{dt} | ${price:.4f} | {price*100:.1f}%")

    # Summary stats
    prices = [p.get("p", 0) for p in history]
    if prices:
        lines.extend([
            "",
            "Summary:",
            f"  Current: {prices[-1]:.4f} ({prices[-1]*100:.1f}%)",
            f"  Min: {min(prices):.4f} ({min(prices)*100:.1f}%)",
            f"  Max: {max(prices):.4f} ({max(prices)*100:.1f}%)",
            f"  Change: {(prices[-1] - prices[0]):+.4f} ({(prices[-1] - prices[0])*100:+.1f}pp)",
        ])

    return "\n".join(lines)


def get_polymarket_order_book(market_id: str) -> str:
    """Get the current order book for a market."""
    market_data = _gamma_get(f"/markets/{market_id}")
    if not market_data:
        return f"No market found with ID: {market_id}"

    clob_ids = json.loads(market_data.get("clobTokenIds", "[]")) if isinstance(market_data.get("clobTokenIds"), str) else market_data.get("clobTokenIds", [])
    if not clob_ids:
        return "No CLOB token IDs found for this market."

    token_id = clob_ids[0]

    try:
        data = _clob_get("/book", params={"token_id": token_id}, cache_seconds=30)
    except requests.exceptions.RequestException as e:
        return f"Order book unavailable for this market (API error: {e})."

    bids = data.get("bids", [])
    asks = data.get("asks", [])

    lines = [
        f"Order Book for: {market_data.get('question', market_id)}",
        f"Token: YES outcome",
        f"Tick Size: {data.get('tick_size', 'N/A')}",
        f"Min Order Size: {data.get('min_order_size', 'N/A')}",
        f"Last Trade Price: {data.get('last_trade_price', 'N/A')}",
        "",
    ]

    # Bids (buyers)
    lines.append("BIDS (Buyers):")
    lines.append("Price | Size")
    lines.append("--- | ---")
    for bid in bids[:10]:
        lines.append(f"${bid.get('price', 'N/A')} | {bid.get('size', 'N/A')}")

    lines.append("")

    # Asks (sellers)
    lines.append("ASKS (Sellers):")
    lines.append("Price | Size")
    lines.append("--- | ---")
    for ask in asks[:10]:
        lines.append(f"${ask.get('price', 'N/A')} | {ask.get('size', 'N/A')}")

    # Spread analysis
    if bids and asks:
        best_bid = float(bids[0].get("price", 0))
        best_ask = float(asks[0].get("price", 0))
        spread = best_ask - best_bid
        mid = (best_ask + best_bid) / 2
        lines.extend([
            "",
            "Spread Analysis:",
            f"  Best Bid: ${best_bid:.4f}",
            f"  Best Ask: ${best_ask:.4f}",
            f"  Spread: ${spread:.4f} ({spread/mid*100:.2f}%)" if mid > 0 else f"  Spread: ${spread:.4f}",
            f"  Midpoint: ${mid:.4f} ({mid*100:.1f}% implied)",
        ])

    return "\n".join(lines)


def get_polymarket_resolution_criteria(market_id: str) -> str:
    """Get the resolution criteria for a market."""
    data = _gamma_get(f"/markets/{market_id}")
    if not data:
        return f"No market found with ID: {market_id}"

    lines = [
        f"Resolution Criteria for: {data.get('question', market_id)}",
        "",
        f"End Date: {data.get('endDate', 'N/A')}",
        f"Description: {data.get('description', 'No description available')}",
        "",
        f"Negative Risk: {data.get('negRisk', False)}",
        f"UMA Bond: {data.get('umaBond', 'N/A')}",
        f"UMA Reward: {data.get('umaReward', 'N/A')}",
    ]

    return "\n".join(lines)


def get_polymarket_event_context(event_id: str) -> str:
    """Get all markets grouped under a prediction market event."""
    try:
        data = _gamma_get(f"/events/{event_id}")
    except requests.exceptions.RequestException:
        return f"No event found with ID: {event_id}. Note: this may be a market ID, not an event ID. Use get_market_info with the market ID instead."
    if not data:
        return f"No event found with ID: {event_id}. Note: this may be a market ID, not an event ID. Use get_market_info with the market ID instead."

    lines = [
        f"Event: {data.get('title', 'N/A')}",
        f"Description: {data.get('description', 'N/A')}",
        f"Negative Risk: {data.get('negRisk', False)}",
        "",
        "Markets in this event:",
        "",
    ]

    markets = data.get("markets", [])
    for i, market in enumerate(markets, 1):
        outcomes = json.loads(market.get("outcomes", "[]")) if isinstance(market.get("outcomes"), str) else market.get("outcomes", [])
        prices = json.loads(market.get("outcomePrices", "[]")) if isinstance(market.get("outcomePrices"), str) else market.get("outcomePrices", [])

        lines.append(f"{i}. {market.get('question', 'N/A')}")
        lines.append(f"   ID: {market.get('id', 'N/A')}")

        for j, outcome in enumerate(outcomes):
            price = prices[j] if j < len(prices) else "N/A"
            lines.append(f"   {outcome}: ${price}")

        lines.append(f"   Volume: ${market.get('volumeNum', market.get('volume', 'N/A'))}")
        lines.append(f"   Active: {market.get('active', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


def get_polymarket_related_markets(query: str, limit: int = 5) -> str:
    """Search for related prediction market events."""
    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": limit,
    }

    data = _gamma_get("/events", params=params, cache_seconds=600)

    if not data:
        return "No events found."

    events = data if isinstance(data, list) else [data]

    lines = [
        f"Top {limit} Active Events by 24h Volume:",
        "",
    ]

    for i, event in enumerate(events[:limit], 1):
        lines.append(f"{i}. {event.get('title', 'N/A')}")
        markets = event.get("markets", [])
        total_volume = sum(
            float(m.get("volume24hr", 0) or 0) for m in markets
        )
        lines.append(f"   Markets: {len(markets)} | 24h Volume: ${total_volume:,.0f}")
        lines.append(f"   ID: {event.get('id', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


def get_polymarket_search(query: str, limit: int = 10) -> str:
    """Search Polymarket for markets matching a query."""
    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": limit,
    }
    if query:
        params["tag"] = query
    data = _gamma_get("/markets", params=params, cache_seconds=300)

    if not data:
        return f"No results found for: {query}"

    markets = data if isinstance(data, list) else data.get("markets", [])

    lines = [
        f"Search results for: '{query}'",
        "",
    ]

    for i, item in enumerate(markets[:limit], 1):
        lines.append(f"{i}. {item.get('question', item.get('title', 'N/A'))}")
        lines.append(f"   ID: {item.get('id', 'N/A')}")

        prices = item.get("outcomePrices")
        if prices:
            if isinstance(prices, str):
                prices = json.loads(prices)
            if prices:
                lines.append(f"   YES: ${prices[0]} | NO: ${prices[1] if len(prices) > 1 else 'N/A'}")

        lines.append(f"   Volume: ${item.get('volumeNum', item.get('volume', 'N/A'))}")
        lines.append(f"   Active: {item.get('active', 'N/A')}")
        lines.append("")

    return "\n".join(lines)
