"""India-only ticker normalization and validation.

The fork is India-first by default. Bare symbols are normalized only for a
conservative allowlist of common Indian tickers; all other equities should be
entered with an explicit `.NS` or `.BO` suffix. This prevents obvious US
tickers such as AAPL or SPY from becoming accidental Yahoo India symbols.
"""

from __future__ import annotations

import re

from tradingagents.dataflows.utils import safe_ticker_component


class IndiaSymbolError(ValueError):
    """Raised when a symbol is outside IndiaMarketAgents' default scope."""


_INDIA_SUFFIX_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,23}\.(NS|BO)$")
_BARE_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,23}$")

_INDIA_INDEX_SYMBOLS = frozenset(
    {
        "^NSEI",
        "^BSESN",
        "^NSEBANK",
        "^CNXIT",
        "^CNXAUTO",
        "^CNXENERGY",
        "^CNXFMCG",
        "^CNXMETAL",
        "^CNXPHARMA",
        "^CNXREALTY",
    }
)

_COMMON_BARE_NSE_SYMBOLS = frozenset(
    {
        "RELIANCE",
        "HDFCBANK",
        "SUNPHARMA",
        "CIPLA",
        "DIVISLAB",
        "DEEPAKNTR",
        "SRF",
        "PIIND",
        "ONGC",
        "IOC",
        "BPCL",
        "GAIL",
        "TCS",
        "INFY",
        "ICICIBANK",
        "SBIN",
        "LT",
        "ITC",
        "HINDUNILVR",
        "BHARTIARTL",
        "KOTAKBANK",
        "AXISBANK",
        "MARUTI",
        "BAJFINANCE",
        "ASIANPAINT",
        "ULTRACEMCO",
        "TITAN",
        "WIPRO",
        "TECHM",
        "DRREDDY",
        "LUPIN",
        "AUROPHARMA",
        "ALKEM",
        "TORNTPHARM",
        "AARTIIND",
        "NAVINFLUOR",
        "TATACHEM",
        "ATUL",
        "VINATIORGA",
        "OIL",
        "PETRONET",
        "IGL",
        "MGL",
        "GUJGASLTD",
    }
)

_KNOWN_NON_INDIA_BARE = frozenset(
    {
        "AAPL",
        "MSFT",
        "NVDA",
        "GOOGL",
        "GOOG",
        "AMZN",
        "META",
        "TSLA",
        "SPY",
        "QQQ",
        "DIA",
        "IWM",
        "VOO",
        "VTI",
        "BRK.B",
        "BTC",
        "ETH",
    }
)


def _clean(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise IndiaSymbolError(
            "Ticker is required. Use NSE/BSE tickers such as RELIANCE.NS or RELIANCE.BO."
        )
    cleaned = symbol.strip().upper()
    try:
        safe_ticker_component(cleaned)
    except ValueError as exc:
        raise IndiaSymbolError(
            "Ticker contains unsafe characters. Use a plain NSE/BSE ticker such as RELIANCE.NS."
        ) from exc
    return cleaned


def is_indian_equity_symbol(symbol: str) -> bool:
    """Return True for explicit Indian Yahoo symbols and supported Indian indices."""
    try:
        cleaned = _clean(symbol)
    except IndiaSymbolError:
        return False
    return (
        cleaned in _INDIA_INDEX_SYMBOLS
        or _INDIA_SUFFIX_RE.fullmatch(cleaned) is not None
        or cleaned in _COMMON_BARE_NSE_SYMBOLS
    )


def normalize_india_symbol(symbol: str, default_exchange: str = "NSE") -> str:
    """Normalize an India symbol to Yahoo-compatible NSE/BSE form."""
    cleaned = _clean(symbol)
    if cleaned in _INDIA_INDEX_SYMBOLS:
        return cleaned
    if _INDIA_SUFFIX_RE.fullmatch(cleaned):
        return cleaned
    if cleaned in _KNOWN_NON_INDIA_BARE or "-" in cleaned or "=" in cleaned:
        raise IndiaSymbolError(
            "IndiaMarketAgents is India-only by default. Use NSE/BSE tickers such as "
            "RELIANCE.NS or RELIANCE.BO."
        )
    if cleaned in _COMMON_BARE_NSE_SYMBOLS and _BARE_RE.fullmatch(cleaned):
        exchange = default_exchange.strip().upper()
        if exchange == "BSE":
            return f"{cleaned}.BO"
        return f"{cleaned}.NS"
    raise IndiaSymbolError(
        "IndiaMarketAgents is India-only by default. Use explicit NSE/BSE tickers "
        "such as RELIANCE.NS or RELIANCE.BO. Bare symbols are accepted only for "
        "common Indian tickers."
    )


def validate_india_symbol_or_raise(symbol: str, config: dict) -> str:
    """Validate and normalize a symbol according to the active India config."""
    if config.get("allow_non_india_tickers"):
        return _clean(symbol)
    default_exchange = config.get("default_exchange", "NSE")
    default_suffix = str(config.get("default_india_suffix", "")).upper()
    if default_suffix == ".BO":
        default_exchange = "BSE"
    elif default_suffix == ".NS":
        default_exchange = "NSE"
    return normalize_india_symbol(symbol, default_exchange=default_exchange)


def safe_india_ticker_component(symbol: str) -> str:
    """Normalize and return a filesystem-safe India ticker path component."""
    return safe_ticker_component(normalize_india_symbol(symbol))
