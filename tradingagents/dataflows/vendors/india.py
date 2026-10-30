"""What the Indian news vendors (Zerodha Pulse, NDTV Profit) share: which tickers they
serve, the search terms for a company, and Indian Standard Time."""

from __future__ import annotations

import logging
import re
from datetime import timedelta, timezone

from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.fundamentals import get_company_profile

logger = logging.getLogger(__name__)

INDIAN_SUFFIXES = (".NS", ".BO")  # NSE and BSE listings, the only ones these vendors are searched for
IST = timezone(timedelta(hours=5, minutes=30))  # both sites stamp articles in Indian Standard Time
MIN_QUERY = 3  # the sites' search ignores anything shorter
_CORPORATE_SUFFIXES = {
    "limited", "ltd", "inc", "incorporated", "corp", "corporation", "co", "company",
    "plc", "ag", "sa", "nv", "llc", "pvt", "private",
}


def require_indian_ticker(vendor: str, ticker: str) -> None:
    """Raise ``VendorUnavailableError`` for a ticker the vendor is not searched for."""
    if not ticker.strip().upper().endswith(INDIAN_SUFFIXES):
        raise VendorUnavailableError(
            f"{vendor} covers only Indian listings ({', '.join(INDIAN_SUFFIXES)}), not {ticker}"
        )


def require_crawl4ai() -> None:
    """Raise ``VendorNotConfiguredError`` when the optional crawl4ai extra is missing."""
    try:
        import crawl4ai  # noqa: F401
    except ImportError as exc:
        raise VendorNotConfiguredError(
            'crawl4ai is not installed; run: pip install "tradingagents[crawl4ai]" && crawl4ai-setup'
        ) from exc


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def search_terms(ticker: str) -> list[str]:
    """Lower-cased queries to try, most specific first: company name, then ticker root."""
    canonical = normalize_symbol(ticker)
    terms: list[str] = []
    try:
        info = get_company_profile(ticker)
    except Exception as exc:  # noqa: BLE001 — name lookup is best-effort
        logger.debug("No company profile for %s: %s", ticker, exc)
        info = {}
    name = info.get("longName") or info.get("shortName") or ""
    words = re.sub(r"[^\w&\s-]", " ", name.lower()).split()
    while words and words[-1] in _CORPORATE_SUFFIXES:
        words.pop()
    if words:
        terms.append(" ".join(words))
    root = canonical.split(".")[0].lower()
    # A BSE scrip code (500325.BO) is never in an article, so it is no query.
    if root not in terms and root.isalnum() and not root.isdigit():
        terms.append(root)
    return [t for t in terms if len(t) >= MIN_QUERY]
