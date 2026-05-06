"""Reddit + CoinMarketCap community sentiment sources.

Both sources require credentials. When credentials are missing, the
helpers return a structured "missing-creds" message so the Sentiment
Analyst (Phase 2) can still produce a useful (degraded) report instead
of failing the pipeline.

Required environment variables:
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    CMC_API_KEY (free tier from https://coinmarketcap.com/api/)
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import requests

from ._cache import cached_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reddit (PRAW-style, but we use the public read-only token endpoint to
# avoid pulling in PRAW's full dependency footprint)
# ---------------------------------------------------------------------------

_DEFAULT_SUBREDDITS = ["Bitcoin", "CryptoCurrency", "CryptoMarkets", "btc"]


def _reddit_token() -> Optional[str]:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "tradingagents/0.3 by kalshi-pivot")
    if not client_id or not client_secret:
        return None

    def _fetch():
        r = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": user_agent},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    try:
        token_payload = cached_json("reddit_token", ttl_seconds=3000, fetcher=_fetch)
        return token_payload.get("access_token")
    except requests.RequestException as e:
        logger.warning("Reddit token fetch failed: %s", e)
        return None


def fetch_reddit_posts(
    asset: str = "bitcoin",
    subreddits: List[str] | None = None,
    limit_per_sub: int = 15,
) -> Optional[List[Dict]]:
    """Fetch top recent posts mentioning ``asset`` across crypto subreddits.

    Returns ``None`` when Reddit credentials are missing or the API call
    fails. Returns an empty list when credentials are valid but no posts
    matched.
    """
    token = _reddit_token()
    if not token:
        return None

    subreddits = subreddits or _DEFAULT_SUBREDDITS
    user_agent = os.environ.get("REDDIT_USER_AGENT", "tradingagents/0.3 by kalshi-pivot")
    headers = {"Authorization": f"Bearer {token}", "User-Agent": user_agent}
    needle = asset.strip().lower()

    posts: List[Dict] = []
    for sub in subreddits:
        url = f"https://oauth.reddit.com/r/{sub}/hot"
        try:
            r = requests.get(url, headers=headers, params={"limit": limit_per_sub}, timeout=10)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.warning("Reddit fetch r/%s failed: %s", sub, e)
            continue
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            title = d.get("title", "")
            text = d.get("selftext", "")
            if needle and needle not in (title + " " + text).lower():
                continue
            posts.append({
                "subreddit": sub,
                "title": title,
                "score": d.get("score", 0),
                "num_comments": d.get("num_comments", 0),
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "summary": text[:500],
            })
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts


def render_reddit_markdown(posts: Optional[List[Dict]], asset: str) -> str:
    if posts is None:
        return (
            f"Reddit sentiment for {asset} unavailable: REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET must be set. Get app creds at "
            "https://www.reddit.com/prefs/apps. The pipeline continues "
            "with the other sentiment inputs."
        )
    if not posts:
        return f"No recent Reddit posts mentioning '{asset}' on the monitored subreddits."

    lines = [f"Top recent posts referencing **{asset}** (score-sorted):", ""]
    for p in posts[:15]:
        lines.append(
            f"- **r/{p['subreddit']}** · score {p['score']} · {p['num_comments']} comments — "
            f"[{p['title']}]({p['url']})"
        )
        if p["summary"]:
            lines.append(f"  {p['summary'][:240]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CoinMarketCap community sentiment
# ---------------------------------------------------------------------------

_CMC_BASE = "https://pro-api.coinmarketcap.com/v1"


def fetch_cmc_sentiment(asset: str = "BTC") -> Optional[Dict]:
    """Fetch CoinMarketCap community sentiment for an asset.

    Returns ``None`` when CMC_API_KEY is unset or the API call fails.
    Returns a dict with at least: ``price``, ``percent_change_24h``,
    ``volume_24h``, ``market_cap``, and the ``cmc_rank``.

    Note: CMC's first-party "Crypto Community Sentiment" dashboard
    surfaces bullish/bearish percentages but its endpoint requires the
    paid Hobbyist+ plan. On the free tier we surface quote + market
    metrics, which the analyst can interpret as a momentum proxy.
    """
    api_key = os.environ.get("CMC_API_KEY")
    if not api_key:
        return None

    symbol = asset.strip().upper()

    def _fetch():
        r = requests.get(
            f"{_CMC_BASE}/cryptocurrency/quotes/latest",
            params={"symbol": symbol, "convert": "USD"},
            headers={"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    try:
        payload = cached_json(f"cmc_{symbol}", ttl_seconds=300, fetcher=_fetch)
    except requests.RequestException as e:
        logger.warning("CMC fetch %s failed: %s", symbol, e)
        return None

    asset_data = (payload.get("data") or {}).get(symbol)
    if not asset_data:
        return None
    quote = (asset_data.get("quote") or {}).get("USD", {})
    return {
        "price": quote.get("price"),
        "percent_change_1h": quote.get("percent_change_1h"),
        "percent_change_24h": quote.get("percent_change_24h"),
        "percent_change_7d": quote.get("percent_change_7d"),
        "volume_24h": quote.get("volume_24h"),
        "volume_change_24h": quote.get("volume_change_24h"),
        "market_cap": quote.get("market_cap"),
        "cmc_rank": asset_data.get("cmc_rank"),
        "name": asset_data.get("name"),
        "symbol": symbol,
    }


def render_cmc_markdown(data: Optional[Dict], asset: str) -> str:
    if data is None:
        return (
            f"CMC community sentiment for {asset} unavailable: CMC_API_KEY "
            "is unset. Get a free tier key at https://coinmarketcap.com/api/. "
            "The pipeline continues with the other sentiment inputs."
        )

    def _pct(v):
        return f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"

    lines = [
        f"### CoinMarketCap snapshot — {data.get('name', asset)} ({data.get('symbol', asset)})",
        "",
        f"- Rank: #{data.get('cmc_rank', '—')}",
        f"- Price (USD): ${data.get('price', 0):,.2f}",
        f"- 1h change: {_pct(data.get('percent_change_1h'))}",
        f"- 24h change: {_pct(data.get('percent_change_24h'))}",
        f"- 7d change: {_pct(data.get('percent_change_7d'))}",
        f"- 24h volume: ${data.get('volume_24h', 0):,.0f} "
        f"(Δ {_pct(data.get('volume_change_24h'))})",
        f"- Market cap: ${data.get('market_cap', 0):,.0f}",
    ]
    return "\n".join(lines)
