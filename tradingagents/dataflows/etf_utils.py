"""Cross-market ETF detection and placeholder helpers.

ETFs are not companies — they have no income statement, balance sheet, or
cash flow. Company-financial tools applied to ETF tickers return mostly-empty
data that confuses the analyst into hallucinating "company margins" for an
index basket. This module centralizes:

- :func:`is_etf_ticker` — vendor-agnostic detection (yfinance ``quoteType``
  with LRU caching, since the check runs on every tool invocation).
- :func:`etf_placeholder` — decorator that short-circuits a vendor function
  to a polite ETF-not-applicable message when the input is an ETF.

A-share tickers are intentionally not special-cased here; A-share ETF support
arrives with the AKShare vendor in a separate change.
"""

from __future__ import annotations

import functools
from typing import Callable, Optional


ETF_PLACEHOLDER = (
    "This ticker {ticker} is an ETF; company-style {report_type} does not apply. "
    "Use get_etf_profile and get_etf_holdings for ETF-relevant data instead."
)


# Company-financial method → human label used in the ETF placeholder.
# ``interface.py`` walks this map at module load and wraps every registered
# vendor implementation of each method with :func:`etf_placeholder`. New
# vendors register only their plain implementation in ``VENDOR_METHODS``;
# they get ETF protection for free, and no vendor module needs to know
# about ETF semantics.
ETF_PROTECTED_METHODS = {
    "get_fundamentals": "fundamentals",
    "get_balance_sheet": "balance sheet",
    "get_cashflow": "cash flow statement",
    "get_income_statement": "income statement",
    "get_insider_transactions": "insider transactions",
}


@functools.lru_cache(maxsize=512)
def _yfinance_quote_type(ticker: str) -> Optional[str]:
    """Cached yfinance ``info.quoteType`` lookup.

    The detection runs from agent prompts and the routing layer, so without
    the LRU we would hit yfinance ``.info`` (a network call) on every tool
    invocation. Any network or parse failure collapses to ``None`` so callers
    treat it as "unknown".
    """
    try:
        import yfinance as yf  # local import: yfinance is heavy
        info = yf.Ticker(ticker).info or {}
        return info.get("quoteType")
    except Exception:  # noqa: BLE001 — any failure is "unknown"
        return None


def is_etf_ticker(value: object) -> bool:
    """Return True when ``value`` is recognized as an ETF by yfinance.

    Falsy / non-string inputs short-circuit to False so callers can pass
    user input straight in without pre-checking.
    """
    if not isinstance(value, str):
        return False
    ticker = value.strip()
    if not ticker:
        return False
    return _yfinance_quote_type(ticker) == "ETF"


def clear_etf_cache() -> None:
    """Reset the quote-type LRU. Tests call this between cases for isolation."""
    _yfinance_quote_type.cache_clear()


def _extract_ticker_arg(args: tuple, kwargs: dict) -> object:
    """Pull the ticker out of an arbitrary vendor-function call signature.

    Vendor functions take the ticker either as the first positional argument
    or as ``ticker=``/``symbol=``. We accept both so the decorator stays
    indifferent to per-vendor naming.
    """
    if args:
        return args[0]
    for key in ("ticker", "symbol"):
        if key in kwargs:
            return kwargs[key]
    return None


def etf_placeholder(report_type: str) -> Callable:
    """Decorator: short-circuit a vendor function to an ETF placeholder.

    Wraps a company-financial vendor function (``get_fundamentals``,
    ``get_balance_sheet``, ...) so an ETF ticker returns a uniform
    placeholder pointing the analyst at ``get_etf_profile`` /
    ``get_etf_holdings`` instead of an empty financial statement.

    ``report_type`` is the human-readable label woven into the placeholder
    (e.g. ``"balance sheet"`` → "company-style balance sheet does not apply").
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            ticker = _extract_ticker_arg(args, kwargs)
            if is_etf_ticker(ticker):
                return ETF_PLACEHOLDER.format(ticker=ticker, report_type=report_type)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
