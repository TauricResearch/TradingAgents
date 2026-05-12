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
def _yfinance_info(ticker: str) -> dict:
    """Cached yfinance ``Ticker(ticker).info`` lookup.

    Single cache for the whole metadata dict so the per-field accessors
    (``_yfinance_quote_type``, ``_yfinance_etf_category``) share one
    network roundtrip per ticker — important because the agent layer hits
    quote_type from every routed tool call and category from every ETF
    instrument-context build, so without consolidation a single analysis
    could trigger multiple ``.info`` fetches for the same symbol.

    Network or parse failures collapse to an empty dict so per-field
    callers treat missing keys as "unknown" rather than crashing.
    """
    try:
        import yfinance as yf  # local import: yfinance is heavy
        return yf.Ticker(ticker).info or {}
    except Exception:  # noqa: BLE001 — any failure is "unknown"
        return {}


def _yfinance_quote_type(ticker: str) -> Optional[str]:
    """Cached yfinance ``info.quoteType`` accessor (delegates to ``_yfinance_info``)."""
    return _yfinance_info(ticker).get("quoteType")


def _yfinance_etf_category(ticker: str) -> str:
    """Cached yfinance ``info.category`` accessor (delegates to ``_yfinance_info``).

    ``category`` strings like ``"Trading--Leveraged Equity"`` and
    ``"Trading--Inverse Equity"`` are the most reliable signal that an ETF
    uses daily reset and therefore decays under buy-and-hold framing.
    """
    return str(_yfinance_info(ticker).get("category") or "")


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


def leverage_descriptor(value: object) -> str:
    """Classify a ticker as leveraged / inverse / both / not, returning a tag.

    Returns one of:
    - ``""`` — not an ETF, or an ordinary unleveraged ETF.
    - ``"Leveraged"`` — daily-reset multiplier (TQQQ 3x, UPRO 3x, SOXL 3x).
    - ``"Inverse"`` — daily-reset short (PSQ -1x, SH -1x).
    - ``"Leveraged Inverse"`` — both at once (SQQQ -3x, SDS -2x, SPXS -3x).

    The caller injects a hard structural warning when this returns
    non-empty: daily reset makes long-term framing inappropriate
    regardless of which underlying these products track.

    Falsy / non-string / non-ETF inputs short-circuit to ``""`` so call
    sites can append unconditionally without branching.
    """
    if not isinstance(value, str):
        return ""
    ticker = value.strip()
    if not ticker or not is_etf_ticker(ticker):
        return ""
    category = _yfinance_etf_category(ticker)
    if not category:
        return ""
    # The yfinance convention is "Trading--<flavor> <asset class>", e.g.
    # "Trading--Leveraged Equity", "Trading--Inverse Commodities". Match
    # case-insensitively on the flavor keywords; require the "Trading--"
    # prefix so we don't false-positive on e.g. "Long-Term Bond".
    lower = category.lower()
    if "trading--" not in lower and "trading-" not in lower:
        return ""
    is_leveraged = "leveraged" in lower
    is_inverse = "inverse" in lower
    if is_leveraged and is_inverse:
        return "Leveraged Inverse"
    if is_leveraged:
        return "Leveraged"
    if is_inverse:
        return "Inverse"
    return ""


def clear_etf_cache() -> None:
    """Reset the yfinance metadata LRU cache. Tests call this between cases
    for isolation. ``_yfinance_quote_type`` / ``_yfinance_etf_category``
    are plain delegators now and share this single cache."""
    _yfinance_info.cache_clear()


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


def concentration_summary(weights_pct: list[float]) -> str:
    """Render a concentration block from per-holding weights (in percent).

    Given the top-N holding weights as percentages (e.g. ``[6.2, 5.8, 4.1]``
    for a 6.20% / 5.80% / 4.10% top-3), produce three signals the analyst
    can use to distinguish a thematic ETF from a broad index:

    - **Largest single holding** — quick glance at single-name risk.
    - **Top-N aggregate weight** — reveals "top 10 holds 95%" thematic
      ETFs vs "top 10 holds 25%" broad indices.
    - **Herfindahl index across the top-N** — sum of squared decimal
      weights. Higher = more concentrated. For an N-holding equal-weight
      slice this equals ``1/N``; a single-name slice would equal 1.0.

    The Herfindahl is computed across the *shown* top-N rather than the
    full universe (which we don't have), so it's a relative concentration
    indicator within the visible slice — not the textbook market HHI.
    Returns an empty string for empty / unparseable input.
    """
    cleaned: list[float] = []
    for w in weights_pct:
        try:
            value = float(w)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        cleaned.append(value)
    if not cleaned:
        return ""

    largest = max(cleaned)
    aggregate = sum(cleaned)
    herfindahl = sum((w / 100) ** 2 for w in cleaned)
    return (
        f"\n## Concentration metrics (top-{len(cleaned)} positions shown)\n"
        f"- Largest single holding: {largest:.2f}%\n"
        f"- Top-{len(cleaned)} aggregate weight: {aggregate:.2f}%\n"
        f"- Herfindahl index (top-{len(cleaned)}): {herfindahl:.4f}\n"
    )


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
