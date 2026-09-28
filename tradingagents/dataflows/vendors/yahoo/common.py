"""What every Yahoo request shares: its retry, and how a failure or an empty answer is reported."""

import logging
import time

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable

logger = logging.getLogger(__name__)

YAHOO_HOST = "https://query2.finance.yahoo.com"


def raise_for_empty(symbol: str, canonical: str, what: str) -> None:
    """Report an empty Yahoo answer as an absence, or as an outage if it is one.

    An empty answer from a Yahoo that cannot be reached is not an answer about
    the symbol, so the host is probed before "this symbol has no {what}" is said.
    """
    if not vendor_reachable(YAHOO_HOST):
        raise VendorUnavailableError(f"Yahoo Finance is unreachable; no {what} was retrieved")
    raise NoMarketDataError(symbol, canonical, f"no {what}")


# yfinance answers some failed requests with an empty result, which would read as
# "no data" for a symbol nobody checked; raised, the failure is reported as one.
yf.config.debug.hide_exceptions = False


def _not_found(exc: Exception) -> bool:
    """Whether Yahoo answered that it has no such symbol (HTTP 404)."""
    return getattr(getattr(exc, "response", None), "status_code", None) == 404


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally, so this wrapper retries them. A rate limit that
    outlasts the retries, or any other exception, is raised as
    VendorUnavailableError: it failed in transit and says nothing about the
    symbol. Yahoo answering that it has no such symbol (HTTP 404) returns None,
    an empty answer. ``func`` should build its own Ticker and make the request
    itself: a Ticker keeps a failed ``info`` fetch as done, so asking the same
    one again reads an empty profile.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError as exc:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise VendorUnavailableError(
                    f"Yahoo Finance rate limited after {max_retries} retries: {exc}"
                ) from exc
        except Exception as exc:
            if _not_found(exc):
                return None
            raise VendorUnavailableError(f"Yahoo Finance request failed: {type(exc).__name__}") from exc
