from typing import Annotated, List, Dict, Any, Optional
from datetime import datetime, timedelta
import threading

from .local import get_YFin_data, get_finnhub_news, get_finnhub_company_insider_sentiment, get_finnhub_company_insider_transactions, get_simfin_balance_sheet, get_simfin_cashflow, get_simfin_income_statements, get_reddit_global_news, get_reddit_company_news
from .y_finance import get_YFin_data_online, get_stock_stats_indicators_window, get_balance_sheet as get_yfinance_balance_sheet, get_cashflow as get_yfinance_cashflow, get_income_statement as get_yfinance_income_statement, get_insider_transactions as get_yfinance_insider_transactions
from .google import get_google_news, get_bulk_news_google
from .openai import get_stock_news_openai, get_global_news_openai, get_fundamentals_openai, get_bulk_news_openai
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news
)
from .alpha_vantage_news import get_bulk_news_alpha_vantage
from .alpha_vantage_common import AlphaVantageRateLimitError

from .config import get_config

from tradingagents.agents.discovery import NewsArticle

TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News (public/insiders, original/processed)",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_sentiment",
            "get_insider_transactions",
            "get_bulk_news",
        ]
    }
}

VENDOR_LIST = [
    "local",
    "yfinance",
    "openai",
    "google"
]

VENDOR_METHODS = {
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "local": get_YFin_data,
    },
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "local": get_stock_stats_indicators_window
    },
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "openai": get_fundamentals_openai,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "local": get_simfin_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "local": get_simfin_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "local": get_simfin_income_statements,
    },
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "openai": get_stock_news_openai,
        "google": get_google_news,
        "local": [get_finnhub_news, get_reddit_company_news, get_google_news],
    },
    "get_global_news": {
        "openai": get_global_news_openai,
        "local": get_reddit_global_news
    },
    "get_insider_sentiment": {
        "local": get_finnhub_company_insider_sentiment
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "local": get_finnhub_company_insider_transactions,
    },
    "get_bulk_news": {
        "alpha_vantage": get_bulk_news_alpha_vantage,
        "openai": get_bulk_news_openai,
        "google": get_bulk_news_google,
    },
}

CACHE_TTL_SECONDS = 300

_bulk_news_cache: Dict[str, Dict[str, Any]] = {}
_bulk_news_cache_lock = threading.Lock()


def parse_lookback_period(lookback: str) -> int:
    lookback = lookback.lower().strip()

    if lookback == "1h":
        return 1
    elif lookback == "6h":
        return 6
    elif lookback == "24h":
        return 24
    elif lookback == "7d":
        return 168
    else:
        raise ValueError(f"Invalid lookback period: {lookback}. Valid values: 1h, 6h, 24h, 7d")


def _get_cached_bulk_news(lookback_period: str) -> Optional[List[NewsArticle]]:
    cache_key = lookback_period
    with _bulk_news_cache_lock:
        if cache_key in _bulk_news_cache:
            cached = _bulk_news_cache[cache_key]
            cached_time = cached.get("timestamp")
            if cached_time and (datetime.now() - cached_time).total_seconds() < CACHE_TTL_SECONDS:
                return cached.get("articles")
    return None


def _set_cached_bulk_news(lookback_period: str, articles: List[NewsArticle]) -> None:
    cache_key = lookback_period
    with _bulk_news_cache_lock:
        _bulk_news_cache[cache_key] = {
            "timestamp": datetime.now(),
            "articles": articles,
        }


def _convert_to_news_articles(raw_articles: List[Dict[str, Any]]) -> List[NewsArticle]:
    articles = []
    for item in raw_articles:
        try:
            published_at_str = item.get("published_at", "")
            if isinstance(published_at_str, str):
                try:
                    published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                except ValueError:
                    published_at = datetime.now()
            elif isinstance(published_at_str, datetime):
                published_at = published_at_str
            else:
                published_at = datetime.now()

            article = NewsArticle(
                title=item.get("title", ""),
                source=item.get("source", ""),
                url=item.get("url", ""),
                published_at=published_at,
                content_snippet=item.get("content_snippet", ""),
                ticker_mentions=[],
            )
            articles.append(article)
        except Exception:
            continue
    return articles


def _fetch_bulk_news_from_vendor(lookback_period: str) -> List[Dict[str, Any]]:
    lookback_hours = parse_lookback_period(lookback_period)

    vendor_order = ["alpha_vantage", "openai", "google"]

    for vendor in vendor_order:
        if vendor not in VENDOR_METHODS["get_bulk_news"]:
            continue

        vendor_func = VENDOR_METHODS["get_bulk_news"][vendor]

        try:
            print(f"DEBUG: Attempting bulk news from vendor '{vendor}'...")
            result = vendor_func(lookback_hours)
            if result:
                print(f"SUCCESS: Got {len(result)} articles from vendor '{vendor}'")
                return result
            print(f"DEBUG: Vendor '{vendor}' returned empty results, trying next...")
        except AlphaVantageRateLimitError as e:
            print(f"RATE_LIMIT: Alpha Vantage rate limit exceeded: {e}")
            continue
        except Exception as e:
            print(f"FAILED: Vendor '{vendor}' failed: {e}")
            continue

    return []


def get_bulk_news(lookback_period: str = "24h") -> List[NewsArticle]:
    cached = _get_cached_bulk_news(lookback_period)
    if cached is not None:
        print(f"DEBUG: Returning cached bulk news for period '{lookback_period}'")
        return cached

    raw_articles = _fetch_bulk_news_from_vendor(lookback_period)

    articles = _convert_to_news_articles(raw_articles)

    _set_cached_bulk_news(lookback_period, articles)

    return articles


def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    config = get_config()

    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)

    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())

    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    primary_str = " -> ".join(primary_vendors)
    fallback_str = " -> ".join(fallback_vendors)
    print(f"DEBUG: {method} - Primary: [{primary_str}] | Full fallback order: [{fallback_str}]")

    results = []
    vendor_attempt_count = 0
    any_primary_vendor_attempted = False
    successful_vendor = None

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            if vendor in primary_vendors:
                print(f"INFO: Vendor '{vendor}' not supported for method '{method}', falling back to next vendor")
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        is_primary_vendor = vendor in primary_vendors
        vendor_attempt_count += 1

        if is_primary_vendor:
            any_primary_vendor_attempted = True

        vendor_type = "PRIMARY" if is_primary_vendor else "FALLBACK"
        print(f"DEBUG: Attempting {vendor_type} vendor '{vendor}' for {method} (attempt #{vendor_attempt_count})")

        if isinstance(vendor_impl, list):
            vendor_methods = [(impl, vendor) for impl in vendor_impl]
            print(f"DEBUG: Vendor '{vendor}' has multiple implementations: {len(vendor_methods)} functions")
        else:
            vendor_methods = [(vendor_impl, vendor)]

        vendor_results = []
        for impl_func, vendor_name in vendor_methods:
            try:
                print(f"DEBUG: Calling {impl_func.__name__} from vendor '{vendor_name}'...")
                result = impl_func(*args, **kwargs)
                vendor_results.append(result)
                print(f"SUCCESS: {impl_func.__name__} from vendor '{vendor_name}' completed successfully")

            except AlphaVantageRateLimitError as e:
                if vendor == "alpha_vantage":
                    print(f"RATE_LIMIT: Alpha Vantage rate limit exceeded, falling back to next available vendor")
                    print(f"DEBUG: Rate limit details: {e}")
                continue
            except Exception as e:
                print(f"FAILED: {impl_func.__name__} from vendor '{vendor_name}' failed: {e}")
                continue

        if vendor_results:
            results.extend(vendor_results)
            successful_vendor = vendor
            result_summary = f"Got {len(vendor_results)} result(s)"
            print(f"SUCCESS: Vendor '{vendor}' succeeded - {result_summary}")

            if len(primary_vendors) == 1:
                print(f"DEBUG: Stopping after successful vendor '{vendor}' (single-vendor config)")
                break
        else:
            print(f"FAILED: Vendor '{vendor}' produced no results")

    if not results:
        print(f"FAILURE: All {vendor_attempt_count} vendor attempts failed for method '{method}'")
        raise RuntimeError(f"All vendor implementations failed for method '{method}'")
    else:
        print(f"FINAL: Method '{method}' completed with {len(results)} result(s) from {vendor_attempt_count} vendor attempt(s)")

    if len(results) == 1:
        return results[0]
    else:
        return '\n'.join(str(result) for result in results)
