"""Yahoo Finance symbol search: quotes matching a symbol or company name."""

from __future__ import annotations

import yfinance as yf


def search_quotes(query: str, max_results: int, timeout: float = 5) -> list[dict]:
    """Yahoo's quote matches for ``query``, best first.

    Each quote is Yahoo's own dict (``symbol``, ``quoteType``, ``longname``,
    ``exchDisp`` and so on). A failed request raises rather than returning an
    empty list, so a caller can tell "no match" from "Yahoo unreachable".
    """
    return yf.Search(query, max_results=max_results, news_count=0, lists_count=0,
                     timeout=timeout, raise_errors=True).quotes
