"""Ticker universe discovery for the ticker accuracy agent.

Provides ticker candidates from multiple sources:
- S&P 500 constituents (from a bundled CSV or yfinance)
- Yahoo Finance sector ETFs top holdings
- Custom universe file (user-supplied JSON)
- Cross-references from existing ticker analysis
"""
from __future__ import annotations

import json
import logging
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


_SP500_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK.B", "LLY",
    "AVGO", "JPM", "V", "TSLA", "XOM", "UNH", "MA", "PG", "JNJ", "COST", "HD",
    "MRK", "CVX", "ABBV", "BAC", "CRM", "WMT", "NFLX", "AMD", "KO", "PEP",
    "ADBE", "TMO", "DIS", "WFC", "CSCO", "MCD", "ABT", "GE", "DHR", "VZ",
    "ACN", "CMCSA", "NKE", "LIN", "TXN", "PM", "IBM", "UPS", "QCOM", "AMGN",
    "BX", "LOW", "BA", "CAT", "RTX", "SPGI", "INTU", "GS", "MS", "BLK",
    "PLD", "DE", "SYK", "SCHW", "C", "UNP", "AMT", "HON", "ISRG", "ELV",
    "ANET", "TMUS", "VRTX", "TJX", "LRCX", "PANW", "ETN", "MDT", "SO", "DUK",
    "NEE", "MO", "MMC", "PGR", "ICE", "ADI", "CL", "BSX", "TT", "ZTS",
    "CMG", "ORLY", "AON", "MCO", "APD", "GD", "EQIX", "SHW", "BDX",
]


_SP500_SAMPLE_SIZE = 50  # Use top 50 by market cap to keep universe manageable


def _get_sp500_tickers() -> list[str]:
    """Return a subset of S&P 500 tickers."""
    return _SP500_TICKERS[:_SP500_SAMPLE_SIZE]


def _get_sector_etf_tickers() -> list[str]:
    """Return tickers from major sector ETFs (XLK, XLF, etc.).

    In v1, returns a curated set of well-known sector representatives.
    Future: fetch top holdings from yfinance dynamically.
    """
    # Major sector ETFs top holdings — representatives per sector
    return [
        # Technology (XLK)
        "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "CSCO", "ADBE", "AMD", "INTC",
        # Financials (XLF)
        "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP",
        # Healthcare (XLV)
        "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "ABT", "SYK", "VRTX",
        # Energy (XLE)
        "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "VLO",
        # Consumer Discretionary (XLY)
        "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "TJX", "SBUX", "GM",
        # Industrial (XLI)
        "GE", "CAT", "BA", "UNP", "HON", "RTX", "ETN", "DE", "UPS",
    ]


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
