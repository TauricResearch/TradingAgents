"""Ticker universe discovery for the ticker accuracy agent.

Provides ticker candidates from multiple sources:
- S&P 500 constituents (fetched dynamically from Wikipedia via pandas)
- Yahoo Finance sector ETFs top holdings (fetched via yfinance)
- Custom universe file (user-supplied JSON)
- Cross-references from existing ticker analysis
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class UniverseConfig:
    sp500_enabled: bool = True
    yahoo_sectors_enabled: bool = True
    custom_file_path: str | None = None
    watchlist_tickers: list[str] = field(default_factory=list)


# -- On-disk cache --
_CACHE_TTL_S = 3600  # 1 hour
_cache_lock = threading.Lock()

# Sector ETFs to pull top holdings from
_SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLI"]

# Hardcoded fallback S&P 500 top 50 (used only when dynamic fetch fails)
_FALLBACK_SP500 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "LLY",
    "AVGO", "JPM", "V", "TSLA", "XOM", "UNH", "MA", "PG", "JNJ", "COST", "HD",
    "MRK", "CVX", "ABBV", "BAC", "CRM", "WMT", "NFLX", "AMD", "KO", "PEP",
    "ADBE", "TMO", "DIS", "WFC", "CSCO", "MCD", "ABT", "GE", "DHR", "VZ",
    "ACN", "CMCSA", "NKE", "LIN", "TXN", "PM", "IBM", "UPS", "QCOM", "AMGN",
]

# Hardcoded fallback sector ETF holdings
_FALLBACK_SECTOR_HOLDINGS = [
    "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "CSCO", "ADBE", "AMD", "INTC",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP",
    "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "ABT", "SYK", "VRTX",
    "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "VLO",
    "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "TJX", "SBUX", "GM",
    "GE", "CAT", "BA", "UNP", "HON", "RTX", "ETN", "DE", "UPS",
]

_cache: dict[str, object] = {}
_cache_loaded = False


def _cache_path() -> Path:
    from web.server import storage as _storage
    try:
        return _storage.ticker_agent_path("universe_cache.json")
    except Exception:
        return Path("universe_cache.json")


def _load_cache() -> dict:
    global _cache_loaded
    with _cache_lock:
        if _cache_loaded:
            return _cache
        try:
            p = _cache_path()
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                if raw.get("ts", 0) + _CACHE_TTL_S > time.time():
                    _cache.update(raw)
        except Exception as e:
            log.warning("Failed to load universe cache: %s", e)
        _cache_loaded = True
        return _cache


def _save_cache() -> None:
    with _cache_lock:
        try:
            _cache["ts"] = time.time()
            _cache_path().write_text(json.dumps(_cache, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Failed to save universe cache: %s", e)


def _fetch_sp500_tickers() -> Optional[list[str]]:
    """Fetch S&P 500 constituents from Wikipedia via pandas."""
    try:
        import pandas as pd
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        tickers = df["Symbol"].tolist()
        return [t.strip().upper() for t in tickers if t.strip()]
    except Exception as e:
        log.warning("Failed to fetch S&P 500 tickers from Wikipedia: %s", e)
        return None


def _fetch_sector_holdings(etf_symbol: str) -> Optional[list[str]]:
    """Fetch top holdings for a sector ETF via yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(etf_symbol)
        holdings = ticker.funds_data.top_holdings
        if holdings is not None and not holdings.empty:
            if "Symbol" in holdings.columns:
                return [s.upper().strip() for s in holdings["Symbol"].tolist() if s]
            if "Ticker" in holdings.columns:
                return [s.upper().strip() for s in holdings["Ticker"].tolist() if s]
        return None
    except Exception as e:
        log.warning("Failed to fetch holdings for %s: %s", etf_symbol, e)
        return None


def _get_sp500_tickers() -> list[str]:
    """Return S&P 500 tickers, fetched dynamically with fallback."""
    cache = _load_cache()
    cached = cache.get("sp500")
    if isinstance(cached, list):
        return cached[:50]

    fetched = _fetch_sp500_tickers()
    if fetched:
        cache["sp500"] = fetched
        _save_cache()
        return fetched[:50]

    log.info("Using hardcoded fallback for S&P 500 tickers")
    return _FALLBACK_SP500


def _get_sector_etf_tickers() -> list[str]:
    """Return tickers from major sector ETFs, fetched dynamically with fallback."""
    cache = _load_cache()

    seen: set[str] = set()
    merged: list[str] = []
    any_fetched = False

    for etf in _SECTOR_ETFS:
        cached_key = f"sector_holdings_{etf}"
        cached_val = cache.get(cached_key)
        holdings: Optional[list[str]] = None

        if isinstance(cached_val, list):
            holdings = cached_val
            any_fetched = True
        else:
            fetched = _fetch_sector_holdings(etf)
            if fetched:
                cache[cached_key] = fetched
                holdings = fetched
                any_fetched = True

        if holdings is not None:
            for t in holdings:
                upper = t.upper().strip()
                if upper and upper not in seen:
                    seen.add(upper)
                    merged.append(upper)

    if not any_fetched:
        log.info("All sector ETF fetches failed, using hardcoded fallback")
        for t in _FALLBACK_SECTOR_HOLDINGS:
            upper = t.upper().strip()
            if upper and upper not in seen:
                seen.add(upper)
                merged.append(upper)

    _save_cache()
    return merged


def load_custom_universe(file_path: str | Path | None) -> list[str]:
    """Load tickers from a custom JSON file (list of ticker strings)."""
    if not file_path:
        return []
    p = Path(file_path)
    if not p.exists():
        log.warning("Custom universe file not found: %s", p)
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [t.upper().strip() for t in data if isinstance(t, str) and t.strip()]
        log.warning("Custom universe file must contain a JSON array of strings, got %s", type(data))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read custom universe file %s: %s", p, e)
    return []


def merge_and_dedup(sources: dict[str, list[str]]) -> list[str]:
    """Merge multiple ticker sources, dedup by uppercase ticker."""
    seen: set[str] = set()
    merged: list[str] = []
    for source_name, tickers in sources.items():
        for t in tickers:
            upper = t.upper().strip()
            if upper and upper not in seen:
                seen.add(upper)
                merged.append(upper)
    return merged


def discover_universe(config: UniverseConfig) -> list[str]:
    """Build the complete ticker universe from all enabled sources."""
    sources: dict[str, list[str]] = {}

    if config.sp500_enabled:
        sources["sp500"] = _get_sp500_tickers()
    if config.yahoo_sectors_enabled:
        sources["sectors"] = _get_sector_etf_tickers()
    if config.watchlist_tickers:
        sources["watchlist"] = config.watchlist_tickers
    if config.custom_file_path:
        custom = load_custom_universe(config.custom_file_path)
        if custom:
            sources["custom"] = custom

    merged = merge_and_dedup(sources)
    log.info("Discovered %d unique tickers from %d sources", len(merged), len(sources))
    return merged