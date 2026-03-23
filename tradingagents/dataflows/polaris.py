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


def _set_cache(key: str, data):
    """Store data in cache (thread-safe)."""
    with _cache_lock:
        _cache[key] = data


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safe_get(obj, key, default='N/A'):
    """Get attribute from dict or object, returning default if missing or None."""
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return default if val is None else val
    val = getattr(obj, key, default)
    return default if val is None else val


def _days_to_range(days: int) -> str:
    """Convert a day count to a Polaris range string."""
    if days <= 30:
        return "1mo"
    elif days <= 90:
        return "3mo"
    elif days <= 180:
        return "6mo"
    elif days <= 365:
        return "1y"
    elif days <= 730:
        return "2y"
    else:
        return "5y"


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

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days
    range_param = _days_to_range(days)

    try:
        data = client.candles(symbol, interval="1d", range=range_param)
    except Exception as e:
        return f"Error fetching stock data for {symbol}: {e}"

    candles = data.get("candles", [])
    if not candles:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Filter to requested date range
    candles = [c for c in candles if start_date <= c["date"] <= end_date]

    lines = [
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date}",
        f"# Source: Polaris Knowledge API (multi-provider: Yahoo/TwelveData/FMP)",
        f"# Total records: {len(candles)}",
        "",
        "Date,Open,High,Low,Close,Volume",
    ]
    lines.extend(
        f"{c['date']},{c['open']},{c['high']},{c['low']},{c['close']},{c['volume']}"
        for c in candles
    )

    result = "\n".join(lines) + "\n"
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
    range_param = _days_to_range(look_back_days)

    known_types = {
        "sma", "ema", "rsi", "macd", "bollinger", "atr",
        "stochastic", "adx", "obv", "vwap", "williams_r",
        "cci", "mfi", "roc", "ppo", "trix", "donchian",
        "parabolic_sar", "ichimoku", "fibonacci",
    }

    try:
        if polaris_type in known_types:
            data = client.indicators(symbol, type=polaris_type, range=range_param)
        else:
            data = client.technicals(symbol, range=range_param)
    except Exception as e:
        return f"Error fetching indicators for {symbol}: {e}"

    values = data.get("values", [])

    lines = [
        f"# Technical Indicator: {indicator} for {symbol.upper()}",
        f"# Source: Polaris Knowledge API",
        f"# Period: {range_param} | Data points: {len(values) if isinstance(values, list) else 'N/A'}",
        "",
    ]

    if isinstance(values, list) and values:
        first = values[0]
        if "value" in first:
            lines.append("Date,Value")
            lines.extend(f"{v['date']},{v.get('value', '')}" for v in values)
        elif "macd" in first:
            lines.append("Date,MACD,Signal,Histogram")
            lines.extend(f"{v['date']},{v.get('macd', '')},{v.get('signal', '')},{v.get('histogram', '')}" for v in values)
        elif "upper" in first:
            lines.append("Date,Upper,Middle,Lower")
            lines.extend(f"{v['date']},{v.get('upper', '')},{v.get('middle', '')},{v.get('lower', '')}" for v in values)
        elif "k" in first:
            lines.append("Date,K,D")
            lines.extend(f"{v['date']},{v.get('k', '')},{v.get('d', '')}" for v in values)
        else:
            # Format dict keys as CSV columns
            keys = list(first.keys())
            lines.append(",".join(keys))
            lines.extend(",".join(str(v.get(k, '')) for k in keys) for v in values)
    elif isinstance(values, dict):
        for k, v in values.items():
            lines.append(f"{k}: {v}")
    else:
        lines.append("No indicator data available")

    result = "\n".join(lines) + "\n"
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

    lines = [
        f"# Company Fundamentals: {data.get('company_name', symbol)}",
        f"# Source: Polaris Knowledge API",
        "",
        f"Sector: {_safe_get(data, 'sector')}",
        f"Industry: {_safe_get(data, 'industry')}",
        f"Market Cap: {_safe_get(data, 'market_cap_formatted')}",
        f"P/E Ratio: {_safe_get(data, 'pe_ratio')}",
        f"Forward P/E: {_safe_get(data, 'forward_pe')}",
        f"EPS: {_safe_get(data, 'eps')}",
        f"Revenue: {_safe_get(data, 'revenue_formatted')}",
        f"EBITDA: {_safe_get(data, 'ebitda_formatted')}",
        f"Profit Margin: {_safe_get(data, 'profit_margin')}",
        f"Debt/Equity: {_safe_get(data, 'debt_to_equity')}",
        f"ROE: {_safe_get(data, 'return_on_equity')}",
        f"Beta: {_safe_get(data, 'beta')}",
        f"52-Week High: {_safe_get(data, 'fifty_two_week_high')}",
        f"52-Week Low: {_safe_get(data, 'fifty_two_week_low')}",
    ]

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


def get_balance_sheet(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch balance sheet from Polaris."""
    cache_key = f"balance_sheet:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching balance sheet for {symbol}: {e}"

    sheets = data.get("balance_sheets", [])
    lines = [
        f"# Balance Sheet: {symbol.upper()}",
        f"# Source: Polaris Knowledge API",
        "",
        "Date,Total Assets,Total Liabilities,Total Equity",
    ]
    lines.extend(f"{s['date']},{s['total_assets']},{s['total_liabilities']},{s['total_equity']}" for s in sheets)

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


def get_cashflow(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch cash flow data from Polaris."""
    cache_key = f"cashflow:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching cashflow for {symbol}: {e}"

    lines = [
        f"# Cash Flow: {symbol.upper()}",
        f"# Source: Polaris Knowledge API",
        "",
        f"Free Cash Flow: {_safe_get(data, 'free_cash_flow')}",
    ]

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


def get_income_statement(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch income statement from Polaris."""
    cache_key = f"income_stmt:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    try:
        data = _get_financials_cached(symbol)
    except Exception as e:
        return f"Error fetching income statement for {symbol}: {e}"

    stmts = data.get("income_statements", [])
    lines = [
        f"# Income Statement: {symbol.upper()}",
        f"# Source: Polaris Knowledge API",
        "",
        "Date,Revenue,Net Income,Gross Profit",
    ]
    lines.extend(f"{s['date']},{s['revenue']},{s['net_income']},{s['gross_profit']}" for s in stmts)

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
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
        data = client.search(symbol, per_page=20, from_date=start_date, to_date=end_date)
        if hasattr(data, '__dict__') and not isinstance(data, dict):
            data = data.__dict__ if hasattr(data, '__dict__') else {}
        if isinstance(data, dict):
            briefs = data.get("briefs", [])
        else:
            briefs = getattr(data, 'briefs', [])
    except Exception as e:
        return f"Error fetching news for {symbol}: {e}"
    if not briefs:
        return f"No intelligence briefs found for {symbol} between {start_date} and {end_date}"

    lines = [
        f"# Intelligence Briefs for {symbol.upper()} ({start_date} to {end_date})",
        f"# Source: Polaris Knowledge API (sentiment-scored, bias-analyzed)",
        f"# Total: {len(briefs)} briefs",
        "",
    ]

    for b in briefs:
        prov = _safe_get(b, "provenance", {})
        if not isinstance(prov, dict):
            prov = {}
        lines.append(f"--- Brief: {_safe_get(b, 'id', '')} ---")
        lines.append(f"Date: {_safe_get(b, 'published_at', '')}")
        lines.append(f"Headline: {_safe_get(b, 'headline', '')}")
        lines.append(f"Summary: {_safe_get(b, 'summary', '')}")
        lines.append(f"Category: {_safe_get(b, 'category', '')}")
        lines.append(f"Confidence: {_safe_get(prov, 'confidence_score')}")
        lines.append(f"Bias Score: {_safe_get(prov, 'bias_score')}")
        lines.append(f"Review Status: {_safe_get(prov, 'review_status')}")
        lines.append(f"Sentiment: {_safe_get(b, 'sentiment')}")
        lines.append(f"Impact Score: {_safe_get(b, 'impact_score')}")

        entities = _safe_get(b, "entities_enriched", [])
        if isinstance(entities, list) and entities:
            ent_str = ", ".join(
                f"{_safe_get(e, 'name', '?')}({_safe_get(e, 'sentiment_score', '?')})"
                for e in entities[:5]
            )
            lines.append(f"Entities: {ent_str}")

        ca = _safe_get(b, "counter_argument", None)
        if ca and ca != 'N/A':
            lines.append(f"Counter-Argument: {str(ca)[:200]}...")

        lines.append("")

    result = "\n".join(lines)
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
        data = client.feed(per_page=20, from_date=start_date, to_date=end_date)
        if hasattr(data, '__dict__') and not isinstance(data, dict):
            data = data.__dict__ if hasattr(data, '__dict__') else {}
        if isinstance(data, dict):
            briefs = data.get("briefs", [])
        else:
            briefs = getattr(data, 'briefs', [])
    except Exception as e:
        return f"Error fetching global news: {e}"

    # Filter to requested date range (belt-and-suspenders)
    filtered = []
    for b in briefs:
        pub = str(_safe_get(b, 'published_at', ''))[:10]
        if pub and start_date <= pub <= end_date:
            filtered.append(b)
    if not filtered:
        filtered = briefs  # Fall back to unfiltered if date parsing fails

    lines = [
        f"# Global Intelligence Feed ({start_date} to {end_date})",
        f"# Source: Polaris Knowledge API",
        f"# Briefs: {len(filtered)}",
        "",
    ]

    for b in filtered:
        prov = _safe_get(b, "provenance", {})
        if not isinstance(prov, dict):
            prov = {}
        pub = str(_safe_get(b, 'published_at', ''))[:10]
        lines.append(
            f"[{pub}] [{_safe_get(b, 'category', '')}] "
            f"{_safe_get(b, 'headline', '')} "
            f"(confidence={_safe_get(prov, 'confidence_score')}, "
            f"bias={_safe_get(prov, 'bias_score')}, "
            f"sentiment={_safe_get(b, 'sentiment')})"
        )

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


def get_sec_filings(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Fetch SEC EDGAR earnings filings (8-K, 10-Q, 10-K) via Polaris."""
    cache_key = f"sec_filings:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.transcripts(symbol, days=365)
    except Exception as e:
        return f"Error fetching filings for {symbol}: {e}"

    filings = data.get("filings", [])
    lines = [
        f"# SEC Filings for {symbol.upper()}",
        f"# Source: Polaris Knowledge API (SEC EDGAR)",
        "",
        "Date,Form,Description,URL",
    ]
    lines.extend(
        f"{_safe_get(f, 'date', '')},{_safe_get(f, 'form', '')},{_safe_get(f, 'description', '')},{_safe_get(f, 'filing_url', '')}"
        for f in filings[:20]
    )

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


# Keep old name as alias for backward compatibility
get_insider_transactions = get_sec_filings


# ---------------------------------------------------------------------------
# Polaris-Exclusive: Sentiment & Trading Signals
# (Complements price/fundamental data from yfinance and Alpha Vantage)
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

    Polaris-exclusive: complements price data from other vendors with intelligence signals.
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

    components = data.get("components", {})
    sent = components.get("sentiment", {}) or {}
    mom = components.get("momentum", {}) or {}
    vol = components.get("volume", {}) or {}
    evt = components.get("events", {}) or {}

    lines = [
        f"# Composite Trading Signal: {symbol.upper()}",
        f"# Source: Polaris Knowledge API (exclusive)",
        "",
        f"Signal: {_safe_get(data, 'signal')}",
        f"Composite Score: {_safe_get(data, 'composite_score')}",
        "",
        f"Sentiment (40%): current_24h={_safe_get(sent, 'current_24h')}, week_avg={_safe_get(sent, 'week_avg')}",
        f"Momentum (25%): {_safe_get(mom, 'direction')} (value={_safe_get(mom, 'value')})",
        f"Volume (20%): {_safe_get(vol, 'briefs_24h')} briefs/24h, velocity={_safe_get(vol, 'velocity_change_pct')}%",
        f"Events (15%): {_safe_get(evt, 'count_7d')} events, latest={_safe_get(evt, 'latest_type')}",
    ]

    result = "\n".join(lines) + "\n"
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

    lines = [
        f"# Competitor Analysis: {symbol.upper()} ({_safe_get(data, 'sector')})",
        f"# Source: Polaris Knowledge API (exclusive)",
        "",
        "Ticker,Name,Price,RSI,Sentiment_7d,Briefs_7d",
    ]

    for c in data.get("competitors", []):
        lines.append(
            f"{_safe_get(c, 'ticker')},{_safe_get(c, 'entity_name')},"
            f"{_safe_get(c, 'price')},{_safe_get(c, 'rsi_14')},"
            f"{_safe_get(c, 'sentiment_7d')},{_safe_get(c, 'briefs_7d')}"
        )

    result = "\n".join(lines) + "\n"
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

    best = data.get("best_impact", {}) or {}
    worst = data.get("worst_impact", {}) or {}

    lines = [
        f"# News Impact Analysis: {symbol.upper()}",
        f"# Source: Polaris Knowledge API (exclusive)",
        "",
        f"Briefs Analyzed: {_safe_get(data, 'briefs_analyzed', 0)}",
        f"Avg 1-Day Impact: {_safe_get(data, 'avg_impact_1d_pct')}%",
        f"Avg 3-Day Impact: {_safe_get(data, 'avg_impact_3d_pct')}%",
        "",
    ]

    if best:
        lines.append(f"Best Impact: {_safe_get(best, 'headline', '')[:60]} (+{_safe_get(best, 'impact_1d_pct')}%)")
    if worst:
        lines.append(f"Worst Impact: {_safe_get(worst, 'headline', '')[:60]} ({_safe_get(worst, 'impact_1d_pct')}%)")

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Polaris-Exclusive: Technical Analysis & Competitive Intelligence
# (Phase 2 — additional intelligence capabilities)
# ---------------------------------------------------------------------------

def get_technicals(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get full technical analysis with 20 indicators and buy/sell/neutral signal.

    Returns all indicators at once: SMA, EMA, RSI, MACD, Bollinger, ATR,
    Stochastic, ADX, OBV, VWAP, Williams %R, CCI, MFI, ROC, and more.
    Includes a composite signal summary with buy/sell/neutral recommendation.

    Polaris-exclusive: complements price data from other vendors with intelligence signals.
    """
    cache_key = f"technicals:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.technicals(symbol, range="6mo")
    except Exception as e:
        return f"Error fetching technicals for {symbol}: {e}"

    latest = data.get("latest", {}) or {}
    signal = data.get("signal_summary", {}) or {}

    lines = [
        f"# Technical Analysis: {symbol.upper()}",
        f"# Source: Polaris Knowledge API (exclusive — 20 indicators)",
        "",
        f"Signal: {_safe_get(signal, 'overall', 'N/A').upper()}",
        f"Buy signals: {_safe_get(signal, 'buy_count', 0)} | Sell signals: {_safe_get(signal, 'sell_count', 0)} | Neutral: {_safe_get(signal, 'neutral_count', 0)}",
        "",
        f"Price: {_safe_get(latest, 'price')}",
        f"RSI(14): {_safe_get(latest, 'rsi_14')}",
        f"MACD: {_safe_get(latest.get('macd', {}), 'macd')} (signal={_safe_get(latest.get('macd', {}), 'signal')}, hist={_safe_get(latest.get('macd', {}), 'histogram')})",
        f"SMA(20): {_safe_get(latest, 'sma_20')} | SMA(50): {_safe_get(latest, 'sma_50')}",
        f"EMA(12): {_safe_get(latest, 'ema_12')} | EMA(26): {_safe_get(latest, 'ema_26')}",
        f"Bollinger: upper={_safe_get(latest.get('bollinger', {}), 'upper')}, middle={_safe_get(latest.get('bollinger', {}), 'middle')}, lower={_safe_get(latest.get('bollinger', {}), 'lower')}",
        f"ATR(14): {_safe_get(latest, 'atr_14')}",
        f"Stochastic: K={_safe_get(latest.get('stochastic', {}), 'k')}, D={_safe_get(latest.get('stochastic', {}), 'd')}",
        f"ADX(14): {_safe_get(latest, 'adx_14')}",
        f"Williams %R(14): {_safe_get(latest, 'williams_r_14')}",
        f"CCI(20): {_safe_get(latest, 'cci_20')}",
        f"MFI(14): {_safe_get(latest, 'mfi_14')}",
        f"ROC(12): {_safe_get(latest, 'roc_12')}",
        f"OBV: {_safe_get(latest, 'obv')}",
        f"VWAP: {_safe_get(latest, 'vwap')}",
    ]

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result


def get_competitors(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get same-sector peers with live price, RSI, sentiment, and news coverage.

    Returns competitors ranked by relevance with real-time data for
    relative analysis and sector positioning.

    Polaris-exclusive: complements price data from other vendors with intelligence signals.
    """
    cache_key = f"peer_analysis:{symbol}"
    cached = _cached(cache_key)
    if cached:
        return cached

    client = _get_client()
    try:
        data = client.competitors(symbol)
    except Exception as e:
        return f"Error fetching competitors for {symbol}: {e}"

    peers = data.get("competitors", [])
    lines = [
        f"# Peer Analysis: {symbol.upper()} ({_safe_get(data, 'sector')})",
        f"# Source: Polaris Knowledge API (exclusive)",
        f"# Peers: {len(peers)}",
        "",
        "Ticker,Name,Price,Change%,RSI(14),Sentiment_7d,Briefs_7d,Signal",
    ]

    for c in peers:
        lines.append(
            f"{_safe_get(c, 'ticker')},{_safe_get(c, 'entity_name')},"
            f"${_safe_get(c, 'price')},{_safe_get(c, 'change_pct')}%,"
            f"{_safe_get(c, 'rsi_14')},{_safe_get(c, 'sentiment_7d')},"
            f"{_safe_get(c, 'briefs_7d')},{_safe_get(c, 'signal', 'N/A')}"
        )

    result = "\n".join(lines) + "\n"
    _set_cache(cache_key, result)
    return result
