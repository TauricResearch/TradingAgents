# get_global_news — Design Document

> **Status**: Proposed  
> **Date**: 2026-04-26  
> **Author**: William  
> **Relates to**: [yfinance-integration.md](./yfinance-integration.md)

---

## 1. Problem Statement

`get_global_news` currently only has an Alpha Vantage implementation (`alpha_vantage_news.py`). The default vendor config sets the `news_data` category to `"yfinance,alpha_vantage"`, but `VENDOR_METHODS["get_global_news"]` only registers `alpha_vantage`. This means:

- yfinance (free, no API key required) is not being utilized.
- If Alpha Vantage hits its rate limit (5 req/min on the free tier), there is no fallback.
- This violates the design principle that every method should have at least 2 vendors in its fallback chain.

---

## 2. Proposed Solution

Add `get_global_news` to `yfinance_client.py` by aggregating news from major market indices, then register it in the vendor router. Flow:

1. **yfinance (primary)**: Fetch news from major market indices (`^GSPC`, `^DJI`, `^IXIC`) → deduplicate → filter by date range → format as markdown.
2. **Alpha Vantage (fallback)**: If yfinance throws any exception → the router automatically falls back to the Alpha Vantage `NEWS_SENTIMENT` API.
3. **Tool layer**: `news_data_tools.get_global_news` keeps its existing interface unchanged, still calling `route_to_vendor`.

---

## 3. Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     AGENT LAYER                              │
│  news_analyst → get_global_news(curr_date, 7, 5)           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              TOOL LAYER — news_data_tools.py                 │
│                                                              │
│  @tool                                                       │
│  def get_global_news(curr_date, look_back_days, limit):     │
│      return route_to_vendor("get_global_news", ...)         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              VENDOR ROUTER — interface.py                     │
│                                                              │
│  route_to_vendor("get_global_news", curr_date, 7, 5)       │
│  fallback_chain = ["yfinance", "alpha_vantage"]             │
│                                                              │
│  for vendor in chain:                                        │
│      try:                                                    │
│          result = impl_func(*args)                           │
│          if result and result.strip(): return result         │
│      except AlphaVantageRateLimitError: continue             │
│      except Exception: continue                              │
└───────┬─────────────────────────────────┬───────────────────┘
        │ ① try first                    │ ② on exception
        ▼                                 ▼
┌──────────────────────┐    ┌─────────────────────────────────┐
│  YFINANCE (PRIMARY)  │    │   ALPHA VANTAGE (FALLBACK)      │
│  yfinance_client.py  │    │   alpha_vantage_news.py         │
│                      │    │                                  │
│  get_global_news()   │    │   get_global_news()             │
│  ┌────────────────┐  │    │   ┌──────────────────────────┐  │
│  │ 1. Fetch from  │  │    │   │ 1. topics=market,macro,  │  │
│  │    ^GSPC,^DJI, │  │    │   │    monetary               │  │
│  │    ^IXIC       │  │    │   │ 2. NEWS_SENTIMENT API    │  │
│  │ 2. Deduplicate │  │    │   │ 3. Return JSON/markdown  │  │
│  │ 3. Filter date │  │    │   └──────────────────────────┘  │
│  │ 4. Sort + Trim │  │    │                                  │
│  │ 5. Format MD   │  │    │                                  │
│  └────────────────┘  │    │                                  │
└──────────┬───────────┘    └────────────────┬────────────────┘
           │                                  │
           └──────────┬───────────────────────┘
                      ▼
        ┌──────────────────────────┐
        │  Formatted markdown str  │
        │  → Agent LLM context     │
        └──────────────────────────┘
```

---

## 4. Function Signatures

### 4.1. `yfinance_client.get_global_news` (NEW)

**File**: `tradingagents/dataflows/yfinance_client.py`

```python
# Module-level constants
_GLOBAL_NEWS_INDICES: list[str] = ["^GSPC", "^DJI", "^IXIC"]
"""Major market indices used as proxy for global news."""


def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 50,
) -> str:
    """Retrieve global market news by aggregating from major indices.

    yfinance does not have a dedicated global news endpoint.
    Strategy: fetch news from S&P 500, Dow Jones, and NASDAQ composite,
    then deduplicate and filter by date range.

    Args:
        curr_date: Current date in YYYY-MM-DD format.
        look_back_days: Number of calendar days to look back.
        limit: Maximum number of articles to return.

    Returns:
        Markdown-formatted string of global news articles.

    Raises:
        RuntimeError: If all indices fail to return news.
    """
```

**Internal helpers** (private, same file):

```python
def _fetch_index_news(index_symbol: str) -> list[dict]:
    """Fetch news articles for a single market index.

    Args:
        index_symbol: yfinance index symbol (e.g. "^GSPC").

    Returns:
        List of raw news item dicts from yfinance.
    """


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by title hash.

    Uses normalized title (lowercase, stripped) as dedup key.

    Args:
        articles: Raw list of news dicts, may contain duplicates.

    Returns:
        Deduplicated list preserving first-seen order.
    """


def _filter_by_date_range(
    articles: list[dict],
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Filter articles to those within [start_date, end_date].

    Args:
        articles: List of news item dicts with pubDate or providerPublishTime.
        start_date: YYYY-MM-DD inclusive lower bound.
        end_date: YYYY-MM-DD inclusive upper bound.

    Returns:
        Filtered list sorted by publish date descending.
    """


def _format_global_news_markdown(articles: list[dict]) -> str:
    """Format news articles into a readable markdown string.

    Args:
        articles: Cleaned, sorted list of news dicts.

    Returns:
        Markdown string with numbered articles.
    """
```

### 4.2. `interface.py` — Registration Changes

**File**: `tradingagents/dataflows/interface.py`

```python
# Add import at top
from .yfinance_client import (
    ...
    get_global_news as get_yfinance_global_news,  # NEW
)

# Update VENDOR_METHODS
VENDOR_METHODS = {
    ...
    "get_global_news": {
        "yfinance": get_yfinance_global_news,         # NEW — primary
        "alpha_vantage": get_alpha_vantage_global_news,  # existing — fallback
    },
    ...
}
```

No changes needed to `route_to_vendor` — it already has built-in fallback chain logic.

### 4.3. `news_data_tools.py` — No Changes

```python
# Unchanged — tool layer delegates entirely to vendor router
@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """Retrieve global news data via configured vendor."""
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)
```

The tool layer remains unchanged because it fully delegates to the vendor router.

### 4.4. `alpha_vantage_news.py` — No Changes

The existing implementation works correctly. No modifications needed.

---

## 5. Implementation Detail — `get_global_news` (yfinance)

```python
def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 50,
) -> str:
    from datetime import datetime, timedelta

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)

    # Step 1: Aggregate news from major indices
    all_articles: list[dict] = []
    errors: list[str] = []

    for index in _GLOBAL_NEWS_INDICES:
        try:
            articles = _fetch_index_news(index)
            all_articles.extend(articles)
        except Exception as e:
            logger.warning("Failed to fetch news for index %s: %s", index, e)
            errors.append(f"{index}: {e}")

    # If ALL indices failed, raise so router can try next vendor
    if not all_articles and errors:
        raise RuntimeError(
            f"All index news fetches failed: {'; '.join(errors)}"
        )

    if not all_articles:
        return "No global news available from market indices."

    # Step 2: Deduplicate
    unique_articles = _deduplicate_articles(all_articles)

    # Step 3: Filter by date range
    start_str = start_dt.strftime("%Y-%m-%d")
    filtered = _filter_by_date_range(unique_articles, start_str, curr_date)

    # Step 4: Trim to limit
    trimmed = filtered[:limit]

    if not trimmed:
        return f"No global news found in range {start_str} to {curr_date}."

    # Step 5: Format
    return _format_global_news_markdown(trimmed)


def _fetch_index_news(index_symbol: str) -> list[dict]:
    t = yf.Ticker(index_symbol)
    time.sleep(_REQUEST_DELAY)
    news = t.news
    if not news:
        return []
    return news


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for article in articles:
        content = article.get("content", {})
        title = content.get("title") or article.get("title", "")
        key = title.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


def _filter_by_date_range(
    articles: list[dict],
    start_date: str,
    end_date: str,
) -> list[dict]:
    from datetime import datetime

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    filtered: list[dict] = []
    for article in articles:
        content = article.get("content", {})
        pub_date_str = content.get("pubDate", "")

        if not pub_date_str:
            # fallback: providerPublishTime (unix timestamp)
            ts = article.get("providerPublishTime")
            if ts:
                article_dt = datetime.utcfromtimestamp(ts)
            else:
                continue
        else:
            try:
                article_dt = datetime.fromisoformat(
                    pub_date_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except ValueError:
                continue

        if start_dt <= article_dt <= end_dt.replace(
            hour=23, minute=59, second=59
        ):
            filtered.append(article)

    # Sort by date descending
    def _sort_key(a: dict) -> str:
        c = a.get("content", {})
        return c.get("pubDate", "") or str(a.get("providerPublishTime", 0))

    filtered.sort(key=_sort_key, reverse=True)
    return filtered


def _format_global_news_markdown(articles: list[dict]) -> str:
    lines: list[str] = ["# Global Market News\n"]

    for i, article in enumerate(articles, 1):
        content = article.get("content", {})
        title = content.get("title") or article.get("title", "No Title")
        provider = content.get("provider", {})
        publisher = (
            provider.get("displayName")
            if isinstance(provider, dict)
            else article.get("publisher", "Unknown")
        )
        pub_date = content.get("pubDate", "")
        canonical = content.get("canonicalUrl", {})
        url = (
            canonical.get("url")
            if isinstance(canonical, dict)
            else article.get("link", "")
        )
        summary = content.get("summary", "")

        lines.append(f"## {i}. {title}")
        if publisher:
            lines.append(f"**Publisher**: {publisher}")
        if pub_date:
            lines.append(f"**Date**: {pub_date}")
        if url:
            lines.append(f"**URL**: {url}")
        if summary:
            lines.append(f"**Summary**: {summary}")
        lines.append("")

    return "\n".join(lines)
```

---

## 6. Files Changed Summary

| File | Action | Description |
|---|---|---|
| `dataflows/yfinance_client.py` | **MODIFY** | Add `get_global_news` + 4 private helpers |
| `dataflows/interface.py` | **MODIFY** | Import `get_yfinance_global_news`, add to `VENDOR_METHODS` |
| `tests/test_yfinance_global_news.py` | **NEW** | Unit tests for the new function |
| `news_data_tools.py` | No change | Already delegates to `route_to_vendor` |
| `alpha_vantage_news.py` | No change | Existing fallback implementation |

---

## 7. Error Handling Matrix

| Scenario | Behavior |
|---|---|
| yfinance returns news successfully | Return formatted markdown, skip Alpha Vantage |
| yfinance returns empty (no news) | Router logs warning, tries Alpha Vantage |
| yfinance throws any `Exception` | Router catches, logs, tries Alpha Vantage |
| yfinance partial failure (1/3 indices fail) | Continue with remaining indices, only raise if ALL fail |
| Alpha Vantage rate limited | `AlphaVantageRateLimitError` → router exhausts chain → `RuntimeError` |
| Both vendors fail | `RuntimeError("All vendors exhausted for 'get_global_news'")` |

---

## 8. Debate Round

### Challenger

1. **yfinance has no real global news API.** Using news from indices (`^GSPC`, `^DJI`, `^IXIC`) is only a proxy. The returned news may be heavily biased toward the US market, missing global coverage (EU, Asia, emerging markets). Alpha Vantage's `NEWS_SENTIMENT` with topics like `economy_macro` provides broader coverage.

2. **3 API calls per single invocation.** Each index = 1 `Ticker.news` call = 1 HTTP request. With `_REQUEST_DELAY = 0.5s`, the minimum total latency is ~1.5s just for yfinance. Compared to Alpha Vantage's single API call, this is a poor latency trade-off.

3. **Dedup logic is fragile.** Using title string matching for deduplication — if two sources write about the same story but with slightly different titles (e.g., adding a dash or using different abbreviations), they won't be deduplicated. Fuzzy matching adds significant complexity.

4. **yfinance rate limiting is increasingly aggressive.** Yahoo Finance has started throttling more heavily. 3 consecutive calls for indices could trigger a 429, making the fallback path even slower.

### Defender

1. **Free vs. paid trade-off.** yfinance is completely free with no API key required. Alpha Vantage's free tier is limited to 5 req/min. In production workloads (multiple ticker analyses running in parallel), Alpha Vantage's rate limit becomes a real bottleneck. yfinance serves as a safety net when Alpha Vantage quota is exhausted.

2. **Latency is acceptable.** 1.5s latency for news fetching in the context of an agent system (where LLM inference takes 5-30s) is negligible. News is not real-time critical — the agent only needs an overview for analysis.

3. **Dedup is good enough for this use case.** Exact title matching removes ~80-90% of duplicates from the same wire sources (Reuters, AP). Perfect deduplication is unnecessary because the agent LLM will naturally synthesize and skip duplicate content during analysis.

4. **Rate limiting mitigation.** `_REQUEST_DELAY` is already in place. If yfinance gets throttled, the exception propagates → router falls back to Alpha Vantage. This is exactly the desired behavior — graceful degradation.

### Verdict

The design **stands as proposed** with the following refinements:

- **Keep yfinance as primary**: The benefit of being free with no API key outweighs the latency concern.
- **Add caching layer (future)**: Cache news responses per session (TTL = 5 min) to reduce duplicate calls. This is a future improvement and does not block the current implementation.
- **Make the indices list configurable**: `_GLOBAL_NEWS_INDICES` is defined as a constant but can be overridden via config if additional indices are needed (e.g., `^FTSE`, `^N225` for broader international coverage).
- **Keep exact match dedup**: Good enough for MVP. Fuzzy matching would be over-engineering at this stage.

---

## 9. Testing Strategy

```python
# tests/test_yfinance_global_news.py

class TestGetGlobalNews:
    """Tests for yfinance get_global_news implementation."""

    def test_returns_markdown_on_success(self, mock_yf_ticker):
        """Happy path: all indices return news."""

    def test_deduplicates_across_indices(self, mock_yf_ticker):
        """Same article from ^GSPC and ^DJI should appear once."""

    def test_filters_by_date_range(self, mock_yf_ticker):
        """Articles outside look_back_days should be excluded."""

    def test_respects_limit(self, mock_yf_ticker):
        """Should not return more than `limit` articles."""

    def test_raises_when_all_indices_fail(self, mock_yf_ticker):
        """RuntimeError when all 3 indices throw exceptions."""

    def test_partial_failure_still_returns(self, mock_yf_ticker):
        """1/3 index fails, other 2 succeed → still returns news."""

    def test_empty_news_returns_message(self, mock_yf_ticker):
        """All indices return empty list → informative message."""


class TestRouterFallback:
    """Integration tests for vendor router fallback behavior."""

    def test_yfinance_success_skips_alpha_vantage(self):
        """When yfinance succeeds, alpha_vantage is not called."""

    def test_yfinance_exception_falls_to_alpha_vantage(self):
        """When yfinance raises, alpha_vantage is tried next."""

    def test_yfinance_empty_falls_to_alpha_vantage(self):
        """When yfinance returns empty string, try fallback."""
```

---

## 10. Implementation Checklist

- [ ] Add `get_global_news` + helpers to `yfinance_client.py`
- [ ] Add import + registration in `interface.py`
- [ ] Write unit tests in `tests/test_yfinance_global_news.py`
- [ ] Run `pytest --tb=short` to verify
- [ ] Manual test: `route_to_vendor("get_global_news", "2026-04-26", 7, 5)`
- [ ] Verify fallback: mock yfinance failure → confirm Alpha Vantage kicks in
