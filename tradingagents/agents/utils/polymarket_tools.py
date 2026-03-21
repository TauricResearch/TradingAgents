"""
Polymarket API tool functions for the TradingAgents prediction market framework.

API base URLs:
- Gamma: https://gamma-api.polymarket.com
- CLOB:  https://clob.polymarket.com
- Data:  https://data-api.polymarket.com
"""

import os
import json
import time
from typing import Optional
import requests
from langchain_core.tools import tool

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

_MAX_RETRIES = 3
_TIMEOUT = 30


def _api_get(url: str, params: Optional[dict] = None) -> dict:
    """
    Retry wrapper for GET requests with exponential backoff.
    Raises requests.HTTPError on non-2xx after max retries.
    """
    last_exc: Exception = RuntimeError("_api_get failed with no attempts")
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise last_exc


# ---------------------------------------------------------------------------
# Tool 1: get_market_data
# ---------------------------------------------------------------------------

@tool
def get_market_data(event_id: str) -> str:
    """
    Fetch market data for a Polymarket event.

    Queries the Gamma API for the given event_id and returns a Markdown report
    including event metadata, outcome prices, volume, and spread.

    Args:
        event_id: The Polymarket event ID (slug or numeric ID).

    Returns:
        A formatted Markdown string with event metadata and market prices.
    """
    try:
        data = _api_get(f"{GAMMA_BASE}/events/{event_id}")
    except Exception as exc:
        return f"## Error fetching market data\n\nFailed to retrieve data for event `{event_id}`:\n{exc}"

    title = data.get("title", "N/A")
    slug = data.get("slug", "N/A")
    volume = data.get("volume", "N/A")
    liquidity = data.get("liquidity", "N/A")
    start_date = data.get("startDate", "N/A")
    end_date = data.get("endDate", "N/A")
    status = data.get("active", "N/A")

    lines = [
        f"## Market Data: {title}",
        "",
        f"- **Event ID**: {event_id}",
        f"- **Slug**: {slug}",
        f"- **Status**: {'Active' if status else 'Closed'}",
        f"- **Start Date**: {start_date}",
        f"- **End Date**: {end_date}",
        f"- **Volume**: {volume}",
        f"- **Liquidity**: {liquidity}",
        "",
        "### Markets",
    ]

    markets = data.get("markets", [])
    for mkt in markets:
        q = mkt.get("question", "N/A")
        raw_prices = mkt.get("outcomePrices", "[]")
        raw_outcomes = mkt.get("outcomes", "[]")
        try:
            prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
        except (json.JSONDecodeError, TypeError):
            prices = []
        try:
            outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
        except (json.JSONDecodeError, TypeError):
            outcomes = []

        spread = mkt.get("spread", "N/A")
        mkt_volume = mkt.get("volume", "N/A")

        lines.append(f"\n**{q}**")
        for i, outcome in enumerate(outcomes):
            price = prices[i] if i < len(prices) else "N/A"
            lines.append(f"  - {outcome}: {price}")
        lines.append(f"  - Spread: {spread} | Volume: {mkt_volume}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: get_price_history
# ---------------------------------------------------------------------------

@tool
def get_price_history(token_id: str, interval: str = "1w") -> str:
    """
    Fetch price history for a Polymarket token.

    Queries the CLOB /prices-history endpoint and returns a time-series table
    plus summary statistics (min, max, mean, latest price).

    Args:
        token_id: The CLOB token ID for the market outcome.
        interval:  Time interval string (e.g., "1d", "1w", "1m"). Defaults to "1w".

    Returns:
        A formatted Markdown string with price history and stats.
    """
    try:
        data = _api_get(f"{CLOB_BASE}/prices-history", params={"market": token_id, "interval": interval, "fidelity": 60})
    except Exception as exc:
        return f"## Error fetching price history\n\nFailed for token `{token_id}`:\n{exc}"

    history = data.get("history", [])
    if not history:
        return f"## Price History: {token_id}\n\nNo price history data available."

    prices = [float(h.get("p", 0)) for h in history if h.get("p") is not None]
    timestamps = [h.get("t", "") for h in history]

    min_p = min(prices) if prices else 0
    max_p = max(prices) if prices else 0
    mean_p = sum(prices) / len(prices) if prices else 0
    latest_p = prices[-1] if prices else 0

    lines = [
        f"## Price History: Token {token_id}",
        f"**Interval**: {interval}",
        "",
        "### Summary Statistics",
        f"- **Latest Price**: {latest_p:.4f}",
        f"- **Min Price**: {min_p:.4f}",
        f"- **Max Price**: {max_p:.4f}",
        f"- **Mean Price**: {mean_p:.4f}",
        f"- **Data Points**: {len(prices)}",
        "",
        "### Price Series (last 20 entries)",
        "| Timestamp | Price |",
        "|-----------|-------|",
    ]

    recent = list(zip(timestamps, prices))[-20:]
    for ts, p in recent:
        lines.append(f"| {ts} | {p:.4f} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3: get_event_details
# ---------------------------------------------------------------------------

@tool
def get_event_details(event_id: str) -> str:
    """
    Fetch detailed information about a Polymarket event.

    Queries the Gamma API and returns description, resolution criteria,
    resolution deadline, and associated markets.

    Args:
        event_id: The Polymarket event ID.

    Returns:
        A formatted Markdown string with event details.
    """
    try:
        data = _api_get(f"{GAMMA_BASE}/events/{event_id}")
    except Exception as exc:
        return f"## Error fetching event details\n\nFailed for event `{event_id}`:\n{exc}"

    title = data.get("title", "N/A")
    description = data.get("description", "No description available.")
    resolution_source = data.get("resolutionSource", "N/A")
    end_date = data.get("endDate", "N/A")
    tags = data.get("tags", [])
    tag_names = [t.get("label", "") for t in tags] if isinstance(tags, list) else []

    lines = [
        f"## Event Details: {title}",
        "",
        f"**Event ID**: {event_id}",
        f"**Resolution Deadline**: {end_date}",
        f"**Resolution Source**: {resolution_source}",
        f"**Tags**: {', '.join(tag_names) if tag_names else 'None'}",
        "",
        "### Description",
        description,
        "",
        "### Associated Markets",
    ]

    markets = data.get("markets", [])
    for mkt in markets:
        q = mkt.get("question", "N/A")
        cond_id = mkt.get("conditionId", "N/A")
        status = "Active" if mkt.get("active") else "Closed"
        end = mkt.get("endDate", "N/A")
        resolution_criteria = mkt.get("description", "")
        lines.append(f"\n#### {q}")
        lines.append(f"- **Condition ID**: {cond_id}")
        lines.append(f"- **Status**: {status}")
        lines.append(f"- **End Date**: {end}")
        if resolution_criteria:
            lines.append(f"- **Resolution Criteria**: {resolution_criteria[:300]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4: get_orderbook
# ---------------------------------------------------------------------------

@tool
def get_orderbook(token_id: str) -> str:
    """
    Fetch the current order book for a Polymarket token.

    Queries the CLOB /book endpoint and returns bid/ask depth tables.

    Args:
        token_id: The CLOB token ID for the market outcome.

    Returns:
        A formatted Markdown string with bid and ask depth tables.
    """
    try:
        data = _api_get(f"{CLOB_BASE}/book", params={"token_id": token_id})
    except Exception as exc:
        return f"## Error fetching order book\n\nFailed for token `{token_id}`:\n{exc}"

    bids = data.get("bids", [])
    asks = data.get("asks", [])
    market = data.get("market", token_id)
    asset_id = data.get("asset_id", token_id)

    lines = [
        f"## Order Book: {asset_id}",
        f"**Market**: {market}",
        "",
        "### Bids (Buy Orders)",
        "| Price | Size |",
        "|-------|------|",
    ]
    for bid in bids[:10]:
        p = bid.get("price", "N/A")
        s = bid.get("size", "N/A")
        lines.append(f"| {p} | {s} |")

    lines += [
        "",
        "### Asks (Sell Orders)",
        "| Price | Size |",
        "|-------|------|",
    ]
    for ask in asks[:10]:
        p = ask.get("price", "N/A")
        s = ask.get("size", "N/A")
        lines.append(f"| {p} | {s} |")

    if bids and asks:
        best_bid = float(bids[0].get("price", 0))
        best_ask = float(asks[0].get("price", 0))
        spread = best_ask - best_bid
        lines += ["", f"**Best Bid**: {best_bid:.4f} | **Best Ask**: {best_ask:.4f} | **Spread**: {spread:.4f}"]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5: get_event_news
# ---------------------------------------------------------------------------

@tool
def get_event_news(query: str, api_key: Optional[str] = None) -> str:
    """
    Search for news articles related to a Polymarket event using Tavily.

    Args:
        query:   Search query string related to the prediction market event.
        api_key: Tavily API key. Falls back to TAVILY_API_KEY environment variable.

    Returns:
        A formatted Markdown string with relevant news articles.
    """
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        return "## Event News\n\nNo Tavily API key provided. Set TAVILY_API_KEY environment variable."

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=key)
        response = client.search(query=query, max_results=5)
    except ImportError:
        return "## Event News\n\nTavily package is not installed. Run: pip install tavily-python"
    except Exception as exc:
        return f"## Event News\n\nSearch failed for query `{query}`:\n{exc}"

    results = response.get("results", [])
    lines = [
        f"## Event News: {query}",
        f"**Query**: {query}",
        f"**Results**: {len(results)} articles",
        "",
    ]
    for i, art in enumerate(results, 1):
        title = art.get("title", "N/A")
        url = art.get("url", "")
        content = art.get("content", "")[:400]
        published = art.get("published_date", "N/A")
        lines += [
            f"### {i}. {title}",
            f"**Published**: {published}",
            f"**URL**: {url}",
            f"{content}",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6: get_global_news
# ---------------------------------------------------------------------------

@tool
def get_global_news(query: str = "prediction markets macro economic news", api_key: Optional[str] = None) -> str:
    """
    Search for global macroeconomic and market news using Tavily.

    Args:
        query:   Search query for macro/global news. Defaults to a broad market query.
        api_key: Tavily API key. Falls back to TAVILY_API_KEY environment variable.

    Returns:
        A formatted Markdown string with global news articles.
    """
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        return "## Global News\n\nNo Tavily API key provided. Set TAVILY_API_KEY environment variable."

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=key)
        response = client.search(query=query, max_results=5, search_depth="advanced")
    except ImportError:
        return "## Global News\n\nTavily package is not installed. Run: pip install tavily-python"
    except Exception as exc:
        return f"## Global News\n\nSearch failed:\n{exc}"

    results = response.get("results", [])
    lines = [
        f"## Global News",
        f"**Query**: {query}",
        f"**Results**: {len(results)} articles",
        "",
    ]
    for i, art in enumerate(results, 1):
        title = art.get("title", "N/A")
        url = art.get("url", "")
        content = art.get("content", "")[:400]
        published = art.get("published_date", "N/A")
        lines += [
            f"### {i}. {title}",
            f"**Published**: {published}",
            f"**URL**: {url}",
            f"{content}",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 7: get_whale_activity
# ---------------------------------------------------------------------------

@tool
def get_whale_activity(market_id: str) -> str:
    """
    Fetch top holder (whale) activity for a Polymarket market.

    Queries the Data API /holders endpoint and returns a table of top holders.

    Args:
        market_id: The Polymarket market/condition ID.

    Returns:
        A formatted Markdown string with top holder information.
    """
    try:
        data = _api_get(f"{DATA_BASE}/holders", params={"market": market_id, "limit": 20})
    except Exception as exc:
        return f"## Error fetching whale activity\n\nFailed for market `{market_id}`:\n{exc}"

    holders = data if isinstance(data, list) else data.get("holders", data.get("data", []))

    lines = [
        f"## Whale Activity: {market_id}",
        "",
        "| Rank | Address | Position | Value |",
        "|------|---------|---------|-------|",
    ]
    for i, holder in enumerate(holders[:20], 1):
        address = holder.get("proxyWallet", holder.get("address", "N/A"))
        position = holder.get("position", holder.get("amount", "N/A"))
        value = holder.get("value", holder.get("usdcValue", "N/A"))
        lines.append(f"| {i} | {address[:12]}... | {position} | {value} |")

    if not holders:
        lines.append("| - | No holder data available | - | - |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 8: get_market_stats
# ---------------------------------------------------------------------------

@tool
def get_market_stats(market_id: str) -> str:
    """
    Fetch open interest and market statistics for a Polymarket market.

    Queries the Data API /openInterest endpoint and returns OI and related stats.

    Args:
        market_id: The Polymarket market/condition ID.

    Returns:
        A formatted Markdown string with market statistics.
    """
    try:
        data = _api_get(f"{DATA_BASE}/openInterest", params={"market": market_id})
    except Exception as exc:
        return f"## Error fetching market stats\n\nFailed for market `{market_id}`:\n{exc}"

    oi = data.get("openInterest", data.get("open_interest", "N/A"))
    total_volume = data.get("totalVolume", data.get("volume", "N/A"))
    num_traders = data.get("numTraders", data.get("traders", "N/A"))
    liquidity = data.get("liquidity", "N/A")
    last_trade_price = data.get("lastTradePrice", "N/A")

    lines = [
        f"## Market Statistics: {market_id}",
        "",
        f"- **Open Interest**: {oi}",
        f"- **Total Volume**: {total_volume}",
        f"- **Number of Traders**: {num_traders}",
        f"- **Liquidity**: {liquidity}",
        f"- **Last Trade Price**: {last_trade_price}",
    ]

    # Include any additional fields
    extra_fields = {k: v for k, v in data.items()
                    if k not in ("openInterest", "open_interest", "totalVolume", "volume",
                                 "numTraders", "traders", "liquidity", "lastTradePrice")}
    if extra_fields:
        lines.append("\n### Additional Stats")
        for k, v in list(extra_fields.items())[:10]:
            lines.append(f"- **{k}**: {v}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 9: get_leaderboard_signals
# ---------------------------------------------------------------------------

@tool
def get_leaderboard_signals(category: str = "OVERALL", time_period: str = "WEEK") -> str:
    """
    Fetch leaderboard data from Polymarket to identify top traders and signals.

    Queries the Data API /v1/leaderboard endpoint.

    Args:
        category:    Leaderboard category (e.g., "OVERALL", "POLITICS", "SPORTS"). Defaults to "OVERALL".
        time_period: Time period for the leaderboard (e.g., "WEEK", "MONTH", "ALL"). Defaults to "WEEK".

    Returns:
        A formatted Markdown string with leaderboard rankings.
    """
    try:
        data = _api_get(f"{DATA_BASE}/v1/leaderboard", params={"category": category, "timePeriod": time_period})
    except Exception as exc:
        return f"## Error fetching leaderboard\n\nFailed (category={category}, period={time_period}):\n{exc}"

    traders = data if isinstance(data, list) else data.get("data", data.get("leaderboard", []))

    lines = [
        f"## Leaderboard Signals",
        f"**Category**: {category} | **Period**: {time_period}",
        "",
        "| Rank | Name / Address | Profit & Loss | Volume |",
        "|------|---------------|--------------|--------|",
    ]
    for i, trader in enumerate(traders[:20], 1):
        name = trader.get("name", trader.get("pseudonym", trader.get("proxyWallet", "N/A")))
        if len(str(name)) > 20:
            name = str(name)[:18] + "..."
        pnl = trader.get("pnl", trader.get("profit", "N/A"))
        volume = trader.get("volume", "N/A")
        lines.append(f"| {i} | {name} | {pnl} | {volume} |")

    if not traders:
        lines.append("| - | No leaderboard data available | - | - |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 10: get_social_sentiment
# ---------------------------------------------------------------------------

@tool
def get_social_sentiment(query: str) -> str:
    """
    Fetch social media sentiment from Twitter and Reddit related to a query.

    Gracefully skips Twitter/Reddit if API keys are not set in environment.
    Required environment variables:
      - Twitter: TWITTER_BEARER_TOKEN
      - Reddit:  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

    Args:
        query: The search query or topic for sentiment analysis.

    Returns:
        A formatted Markdown string with social sentiment data.
    """
    lines = [f"## Social Sentiment: {query}", ""]
    any_data = False

    # --- Twitter ---
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    if bearer_token:
        try:
            import tweepy
            client = tweepy.Client(bearer_token=bearer_token)
            response = client.search_recent_tweets(
                query=f"{query} -is:retweet lang:en",
                max_results=10,
                tweet_fields=["created_at", "public_metrics"],
            )
            tweets = response.data or []
            lines += [
                "### Twitter",
                f"**Recent tweets** ({len(tweets)} found):",
                "",
            ]
            for tweet in tweets:
                text = tweet.text[:200].replace("\n", " ")
                metrics = getattr(tweet, "public_metrics", {}) or {}
                likes = metrics.get("like_count", 0)
                rts = metrics.get("retweet_count", 0)
                lines.append(f"- {text} _(likes: {likes}, retweets: {rts})_")
            any_data = True
        except ImportError:
            lines.append("_Twitter: tweepy not installed (pip install tweepy)_")
        except Exception as exc:
            lines.append(f"_Twitter: Error — {exc}_")
    else:
        lines.append("_Twitter: TWITTER_BEARER_TOKEN not set — skipping._")

    lines.append("")

    # --- Reddit ---
    reddit_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_secret = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_agent = os.getenv("REDDIT_USER_AGENT", "polymarket-agent/1.0")
    if reddit_id and reddit_secret:
        try:
            import praw
            reddit = praw.Reddit(
                client_id=reddit_id,
                client_secret=reddit_secret,
                user_agent=reddit_agent,
            )
            subreddits = "Polymarket+PredictionMarkets+politics+finance"
            results = list(reddit.subreddit(subreddits).search(query, limit=10, sort="new"))
            lines += [
                "### Reddit",
                f"**Recent posts** ({len(results)} found):",
                "",
            ]
            for post in results:
                title = post.title[:150].replace("\n", " ")
                score = post.score
                sub = post.subreddit.display_name
                lines.append(f"- [{sub}] {title} _(score: {score})_")
            any_data = True
        except ImportError:
            lines.append("_Reddit: praw not installed (pip install praw)_")
        except Exception as exc:
            lines.append(f"_Reddit: Error — {exc}_")
    else:
        lines.append("_Reddit: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set — skipping._")

    if not any_data:
        lines.append("\n_No social sentiment data available. Configure API keys._")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 11: search_markets
# ---------------------------------------------------------------------------

@tool
def search_markets(
    min_volume: int = 10000,
    category: str = "",
    status: str = "active",
    limit: int = 20,
) -> str:
    """
    Search for Polymarket events/markets with optional filters.

    Queries the Gamma API /events endpoint with filters for volume, category,
    and market status.

    Args:
        min_volume: Minimum trading volume filter (default: 10000).
        category:   Category tag filter, e.g., "politics", "sports" (optional).
        status:     Market status filter: "active" or "closed" (default: "active").
        limit:      Maximum number of results to return (default: 20).

    Returns:
        A formatted Markdown string listing matching markets.
    """
    params = {
        "limit": min(limit, 100),
        "active": (status.lower() == "active"),
        "closed": (status.lower() == "closed"),
    }
    if category:
        params["tag"] = category

    try:
        data = _api_get(f"{GAMMA_BASE}/events", params=params)
    except Exception as exc:
        return f"## Error searching markets\n\nFailed:\n{exc}"

    events = data if isinstance(data, list) else data.get("events", data.get("data", []))

    # Filter by min_volume
    filtered = []
    for ev in events:
        try:
            vol = float(ev.get("volume", 0) or 0)
        except (ValueError, TypeError):
            vol = 0
        if vol >= min_volume:
            filtered.append(ev)

    lines = [
        "## Market Search Results",
        f"**Filters**: min_volume={min_volume}, category='{category}', status={status}",
        f"**Found**: {len(filtered)} markets (showing up to {limit})",
        "",
        "| Title | Volume | End Date | Status |",
        "|-------|--------|---------|--------|",
    ]

    for ev in filtered[:limit]:
        title = str(ev.get("title", "N/A"))[:50]
        vol = ev.get("volume", "N/A")
        end = ev.get("endDate", "N/A")
        active = "Active" if ev.get("active") else "Closed"
        lines.append(f"| {title} | {vol} | {end} | {active} |")

    if not filtered:
        lines.append("| No markets matched the given filters | - | - | - |")

    return "\n".join(lines)
