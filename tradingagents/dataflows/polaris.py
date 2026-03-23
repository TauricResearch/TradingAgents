"""
Polaris Knowledge API data vendor for TradingAgents.

Polaris provides sentiment-scored intelligence briefs, composite trading signals,
technical indicators, financial data, and news impact analysis. Unlike raw data
feeds, every Polaris response includes confidence scores, bias analysis, and
NLP-derived metadata that enriches agent decision-making.

Setup:
    pip install polaris-news
    export POLARIS_API_KEY=pr_live_xxx  # Free: 1,000 credits/month at thepolarisreport.com

API docs: https://thepolarisreport.com/api-reference
"""

import os
import threading
from typing import Annotated
from datetime import datetime

try:
    from cachetools import TTLCache
except ImportError:
    # Fallback if cachetools not installed
    from functools import lru_cache
    TTLCache = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CACHE_TTL = 300  # 5 minutes
_CACHE_MAX = 500

# Thread-safe TTL cache (preferred) with fallback to simple dict
if TTLCache is not None:
    _cache = TTLCache(maxsize=_CACHE_MAX, ttl=_CACHE_TTL)
    _cache_lock = threading.Lock()
else:
    _cache = {}
    _cache_lock = threading.Lock()

_client_instance = None
_client_lock = threading.Lock()


def _get_client():
    """Lazy-initialize Polaris client (thread-safe singleton)."""
    global _client_instance
    if _client_instance is not None:
        return _client_instance
    with _client_lock:
        if _client_instance is not None:
            return _client_instance
        try:
            from polaris_news import PolarisClient
        except ImportError:
            raise ImportError(
                "polaris-news is required for the Polaris data vendor. "
                "Install it with: pip install polaris-news"
            )
        api_key = os.environ.get("POLARIS_API_KEY", "demo")
        _client_instance = PolarisClient(api_key=api_key)
        return _client_instance


def _cached(key: str):
    """Check cache for a key. Returns cached value or None (thread-safe)."""
    with _cache_lock:
        return _cache.get(key)


def _set_cache(key: str, data: str):
    """Store data in cache (thread-safe)."""
    with _cache_lock:
        _cache[key] = data


# ---------------------------------------------------------------------------
# Core Stock APIs
# ---------------------------------------------------------------------------

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch OHLCV stock data from Polaris (via multi-provider: Yahoo/TwelveData/FMP)."""
    cache_key = f"stock:{symbol}:{start_date}:{end_date}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()

    # Determine range from date span
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days

    if days <= 30:
        range_param = "1mo"
    elif days <= 90:
        range_param = "3mo"
    elif days <= 180:
        range_param = "6mo"
    elif days <= 365:
        range_param = "1y"
    elif days <= 730:
        range_param = "2y"
    else:
        range_param = "5y"

    try:
        data = client.candles(symbol, interval="1d", range=range_param)
    except Exception as e:
        return f"Error fetching stock data for {symbol}: {e}"

    candles = data.get("candles", [])
    if not candles:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Filter to requested date range
    candles = [c for c in candles if start_date <= c["date"] <= end_date]

    # Format as CSV (matching yfinance output format)
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Source: Polaris Knowledge API (multi-provider: Yahoo/TwelveData/FMP)\n"
    header += f"# Total records: {len(candles)}\n\n"

    csv = "Date,Open,High,Low,Close,Volume\n"
    for c in candles:
        csv += f"{c['date']},{c['open']},{c['high']},{c['low']},{c['close']},{c['volume']}\n"

    result = header + csv
    _set_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Technical Indicators
# ---------------------------------------------------------------------------

def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get"],
    curr_date: Annotated[str, "Current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Fetch technical indicators from Polaris (20 indicators + signal summary)."""
    cache_key = f"indicators:{symbol}:{indicator}:{curr_date}:{look_back_days}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()

    # Map common indicator names to Polaris types
    indicator_map = {
        "close_50_sma": "sma", "close_20_sma": "sma", "close_200_sma": "sma",
        "rsi_14": "rsi", "rsi": "rsi",
        "macd": "macd", "macds": "macd", "macdh": "macd",
        "boll": "bollinger", "boll_ub": "bollinger", "boll_lb": "bollinger",
        "atr": "atr", "atr_14": "atr",
        "stoch": "stochastic", "stochrsi": "stochastic",
        "adx": "adx", "williams_r": "williams_r",
        "cci": "cci", "mfi": "mfi", "roc": "roc",
        "obv": "obv", "vwap": "vwap",
    }

    polaris_type = indicator_map.get(indicator.lower(), indicator.lower())

    # Determine range
    if look_back_days <= 30:
        range_param = "1mo"
    elif look_back_days <= 90:
        range_param = "3mo"
    elif look_back_days <= 180:
        range_param = "6mo"
    else:
        range_param = "1y"

    # Try specific indicator first, fall back to full technicals
    try:
        if polaris_type in ["sma", "ema", "rsi", "macd", "bollinger", "atr",
                            "stochastic", "adx", "obv", "vwap", "williams_r",
                            "cci", "mfi", "roc", "ppo", "trix", "donchian",
                            "parabolic_sar", "ichimoku", "fibonacci"]:
            data = client.indicators(symbol, type=polaris_type, range=range_param)
        else:
            data = client.technicals(symbol, range=range_param)
    except Exception as e:
        return f"Error fetching indicators for {symbol}: {e}"

    values = data.get("values", [])

    header = f"# Technical Indicator: {indicator} for {symbol.upper()}\n"
    header += f"# Source: Polaris Knowledge API\n"
    header += f"# Period: {range_param} | Data points: {len(values)}\n\n"

    if isinstance(values, list) and values:
        # Format based on indicator type
        first = values[0]
        if "value" in first:
            csv = "Date,Value\n"
            for v in values:
                csv += f"{v['date']},{v['value']}\n"
        elif "macd" in first:
            csv = "Date,MACD,Signal,Histogram\n"
            for v in values:
                csv += f"{v['date']},{v.get('macd','')},{v.get('signal','')},{v.get('histogram','')}\n"
        elif "upper" in first:
            csv = "Date,Upper,Middle,Lower\n"
            for v in values:
                csv += f"{v['date']},{v.get('upper','')},{v.get('middle','')},{v.get('lower','')}\n"
        elif "k" in first:
            csv = "Date,K,D\n"
            for v in values:
                csv += f"{v['date']},{v.get('k','')},{v.get('d','')}\n"
        else:
            csv = str(values)
    elif isinstance(values, dict):
        # Fibonacci or similar
        csv = str(values)
    else:
        csv = "No indicator data available"

    result = header + csv
    _set_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Fundamental Data
# ---------------------------------------------------------------------------

def _get_financials_cached(symbol: str) -> dict:
    """Shared cached financials fetch — used by fundamentals, balance_sheet, cashflow, income_statement."""
    cache_key = f"financials_raw:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached
    client = _get_client()
    data = client.financials(symbol)
    _set_cache(cache_key, data)
    return data


def get_fundamentals(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch company fundamentals from Polaris (via Yahoo Finance quoteSummary)."""
    cache_key = f"fundamentals:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching fundamentals for {symbol}: {e}"

    result = f"# Company Fundamentals: {data.get('company_name', symbol)}\n"
    result += f"# Source: Polaris Knowledge API\n\n"
    result += f"Sector: {data.get('sector', 'N/A')}\n"
    result += f"Industry: {data.get('industry', 'N/A')}\n"
    result += f"Market Cap: {data.get('market_cap_formatted', 'N/A')}\n"
    result += f"P/E Ratio: {data.get('pe_ratio', 'N/A')}\n"
    result += f"Forward P/E: {data.get('forward_pe', 'N/A')}\n"
    result += f"EPS: {data.get('eps', 'N/A')}\n"
    result += f"Revenue: {data.get('revenue_formatted', 'N/A')}\n"
    result += f"EBITDA: {data.get('ebitda_formatted', 'N/A')}\n"
    result += f"Profit Margin: {data.get('profit_margin', 'N/A')}\n"
    result += f"Debt/Equity: {data.get('debt_to_equity', 'N/A')}\n"
    result += f"ROE: {data.get('return_on_equity', 'N/A')}\n"
    result += f"Beta: {data.get('beta', 'N/A')}\n"
    result += f"52-Week High: {data.get('fifty_two_week_high', 'N/A')}\n"
    result += f"52-Week Low: {data.get('fifty_two_week_low', 'N/A')}\n"

    _set_cache(cache_key, result)
    return result


def get_balance_sheet(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch balance sheet from Polaris."""
    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching balance sheet for {symbol}: {e}"

    sheets = data.get("balance_sheets", [])
    result = f"# Balance Sheet: {symbol.upper()}\n# Source: Polaris Knowledge API\n\n"
    result += "Date,Total Assets,Total Liabilities,Total Equity\n"
    for s in sheets:
        result += f"{s['date']},{s['total_assets']},{s['total_liabilities']},{s['total_equity']}\n"

    return result


def get_cashflow(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch cash flow data from Polaris."""
    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching cashflow for {symbol}: {e}"

    result = f"# Cash Flow: {symbol.upper()}\n# Source: Polaris Knowledge API\n\n"
    result += f"Free Cash Flow: {data.get('free_cash_flow', 'N/A')}\n"
    return result


def get_income_statement(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch income statement from Polaris."""
    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching income statement for {symbol}: {e}"

    stmts = data.get("income_statements", [])
    result = f"# Income Statement: {symbol.upper()}\n# Source: Polaris Knowledge API\n\n"
    result += "Date,Revenue,Net Income,Gross Profit\n"
    for s in stmts:
        result += f"{s['date']},{s['revenue']},{s['net_income']},{s['gross_profit']}\n"

    return result


# ---------------------------------------------------------------------------
# News & Intelligence (Polaris advantage — sentiment-scored, not raw headlines)
# ---------------------------------------------------------------------------

def get_news(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch sentiment-scored intelligence briefs from Polaris.

    Unlike raw news feeds, each brief includes:
    - Confidence score (0-1)
    - Bias score and direction
    - Counter-arguments
    - Entity-level sentiment (-1.0 to +1.0)
    """
    cache_key = f"news:{symbol}:{start_date}:{end_date}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.search(symbol, per_page=20)
        # Handle both dict and typed response objects
        if hasattr(data, '__dict__') and not isinstance(data, dict):
            data = data.__dict__ if hasattr(data, '__dict__') else {}
        if isinstance(data, dict):
            briefs = data.get("briefs", [])
        else:
            briefs = getattr(data, 'briefs', [])
    except Exception as e:
        return f"Error fetching news for {symbol}: {e}"
    if not briefs:
        return f"No intelligence briefs found for {symbol}"

    result = f"# Intelligence Briefs for {symbol.upper()}\n"
    result += f"# Source: Polaris Knowledge API (sentiment-scored, bias-analyzed)\n"
    result += f"# Total: {len(briefs)} briefs\n\n"

    def _get(obj, key, default='N/A'):
        """Get attribute from dict or object."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for b in briefs:
        prov = _get(b, "provenance", {})
        result += f"--- Brief: {_get(b, 'id', '')} ---\n"
        result += f"Date: {_get(b, 'published_at', '')}\n"
        result += f"Headline: {_get(b, 'headline', '')}\n"
        result += f"Summary: {_get(b, 'summary', '')}\n"
        result += f"Category: {_get(b, 'category', '')}\n"
        result += f"Confidence: {_get(prov, 'confidence_score', 'N/A')}\n"
        result += f"Bias Score: {_get(prov, 'bias_score', 'N/A')}\n"
        result += f"Review Status: {_get(prov, 'review_status', 'N/A')}\n"
        result += f"Sentiment: {_get(b, 'sentiment', 'N/A')}\n"
        result += f"Impact Score: {_get(b, 'impact_score', 'N/A')}\n"

        entities = _get(b, "entities_enriched", []) or []
        if entities:
            ent_str = ", ".join(
                f"{_get(e, 'name', '?')}({_get(e, 'sentiment_score', '?')})"
                for e in (entities[:5] if isinstance(entities, list) else [])
            )
            result += f"Entities: {ent_str}\n"

        ca = _get(b, "counter_argument", None)
        if ca:
            result += f"Counter-Argument: {str(ca)[:200]}...\n"

        result += "\n"

    _set_cache(cache_key, result)
    return result


def get_global_news(
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch global intelligence feed from Polaris with sentiment and bias scoring."""
    cache_key = f"global_news:{start_date}:{end_date}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.feed(per_page=20)
        if hasattr(data, '__dict__') and not isinstance(data, dict):
            data = data.__dict__ if hasattr(data, '__dict__') else {}
        if isinstance(data, dict):
            briefs = data.get("briefs", [])
        else:
            briefs = getattr(data, 'briefs', [])
    except Exception as e:
        return f"Error fetching global news: {e}"
    result = f"# Global Intelligence Feed\n"
    result += f"# Source: Polaris Knowledge API\n"
    result += f"# Briefs: {len(briefs)}\n\n"

    def _get2(obj, key, default='N/A'):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for b in briefs:
        prov = _get2(b, "provenance", {})
        pub = str(_get2(b, 'published_at', ''))[:10]
        result += f"[{pub}] [{_get2(b, 'category', '')}] "
        result += f"{_get2(b, 'headline', '')} "
        result += f"(confidence={_get2(prov, 'confidence_score', '?')}, "
        result += f"bias={_get2(prov, 'bias_score', '?')}, "
        result += f"sentiment={_get2(b, 'sentiment', '?')})\n"

    _set_cache(cache_key, result)
    return result


def get_insider_transactions(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch SEC EDGAR earnings filings via Polaris."""
    client = _get_client()
    try:
        data = client.transcripts(symbol, days=365)
    except Exception as e:
        return f"Error fetching filings for {symbol}: {e}"

    filings = data.get("filings", [])
    result = f"# SEC Filings for {symbol.upper()}\n"
    result += f"# Source: Polaris Knowledge API (SEC EDGAR)\n\n"
    result += "Date,Form,Description,URL\n"
    for f in filings[:20]:
        result += f"{f.get('date', '')},{f.get('form', '')},{f.get('description', '')},{f.get('filing_url', '')}\n"

    return result


# ---------------------------------------------------------------------------
# Polaris-Exclusive: Sentiment & Trading Signals
# (Not available from Yahoo Finance or Alpha Vantage)
# ---------------------------------------------------------------------------

def get_sentiment_score(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get composite trading signal from Polaris.

    Returns a multi-factor score combining:
    - Sentiment (40% weight)
    - Momentum (25% weight)
    - Coverage velocity (20% weight)
    - Event proximity (15% weight)

    Not available from any other data vendor.
    """
    cache_key = f"sentiment:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.ticker_score(symbol)
    except Exception as e:
        return f"Error fetching sentiment score for {symbol}: {e}"

    result = f"# Composite Trading Signal: {symbol.upper()}\n"
    result += f"# Source: Polaris Knowledge API (exclusive)\n\n"
    result += f"Signal: {data.get('signal', 'N/A')}\n"
    result += f"Composite Score: {data.get('composite_score', 'N/A')}\n\n"

    components = data.get("components", {})
    sent = components.get("sentiment", {})
    result += f"Sentiment (40%): current_24h={sent.get('current_24h')}, week_avg={sent.get('week_avg')}\n"

    mom = components.get("momentum", {})
    result += f"Momentum (25%): {mom.get('direction', 'N/A')} (value={mom.get('value')})\n"

    vol = components.get("volume", {})
    result += f"Volume (20%): {vol.get('briefs_24h')} briefs/24h, velocity={vol.get('velocity_change_pct')}%\n"

    evt = components.get("events", {})
    result += f"Events (15%): {evt.get('count_7d')} events, latest={evt.get('latest_type')}\n"

    _set_cache(cache_key, result)
    return result


def get_sector_analysis(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get competitor intelligence for a ticker — same-sector peers with live data."""
    cache_key = f"competitors:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.competitors(symbol)
    except Exception as e:
        return f"Error fetching sector analysis for {symbol}: {e}"

    result = f"# Competitor Analysis: {symbol.upper()} ({data.get('sector', 'N/A')})\n"
    result += f"# Source: Polaris Knowledge API (exclusive)\n\n"
    result += "Ticker,Name,Price,RSI,Sentiment_7d,Briefs_7d\n"

    for c in data.get("competitors", []):
        result += f"{c.get('ticker')},{c.get('entity_name')},{c.get('price')},{c.get('rsi_14')},{c.get('sentiment_7d')},{c.get('briefs_7d')}\n"

    _set_cache(cache_key, result)
    return result


def get_news_impact(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Measure how news moved the stock price — brief-to-price causation analysis."""
    cache_key = f"impact:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.news_impact(symbol)
    except Exception as e:
        return f"Error fetching news impact for {symbol}: {e}"

    result = f"# News Impact Analysis: {symbol.upper()}\n"
    result += f"# Source: Polaris Knowledge API (exclusive)\n\n"
    result += f"Briefs Analyzed: {data.get('briefs_analyzed', 0)}\n"
    result += f"Avg 1-Day Impact: {data.get('avg_impact_1d_pct', 'N/A')}%\n"
    result += f"Avg 3-Day Impact: {data.get('avg_impact_3d_pct', 'N/A')}%\n\n"

    best = data.get("best_impact", {})
    if best:
        result += f"Best Impact: {best.get('headline', '')[:60]} (+{best.get('impact_1d_pct')}%)\n"

    worst = data.get("worst_impact", {})
    if worst:
        result += f"Worst Impact: {worst.get('headline', '')[:60]} ({worst.get('impact_1d_pct')}%)\n"

    _set_cache(cache_key, result)
    return result
