"""Live currency exchange rates, in the spirit of a simple Xe-style board.

Same reasoning as charts.py: a free, quota-free glance, fetched straight
from Yahoo Finance FX tickers (``BASEQUOTE=X``, Yahoo's own convention —
the price is how much QUOTE one unit of BASE buys), not the LLM pipeline.
"""

from __future__ import annotations

import yfinance as yf

from tradingagents.dataflows.stockstats_utils import yf_retry

# A curated board, not "every currency" — matches what a research/trading
# product's users actually reach for, plus the base currency this repo's
# stock data functions are implicitly denominated in (USD).
SUPPORTED_CURRENCIES = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "CAD",
    "CHF",
    "CNY",
    "INR",
    "AED",
    "SAR",
    "EGP",
)


class RatesUnavailable(Exception):
    """No rate could be fetched for one or more currencies."""


def get_exchange_rates(base: str) -> dict[str, float]:
    base = base.upper()
    if base not in SUPPORTED_CURRENCIES:
        raise ValueError(f"base must be one of {SUPPORTED_CURRENCIES}, got {base!r}")

    rates: dict[str, float] = {base: 1.0}
    for currency in SUPPORTED_CURRENCIES:
        if currency == base:
            continue
        ticker = yf.Ticker(f"{base}{currency}=X")
        try:
            data = yf_retry(lambda t=ticker: t.history(period="5d"))
        except Exception as exc:  # noqa: BLE001 - any yfinance/network failure
            raise RatesUnavailable(f"Could not fetch {base}/{currency}: {exc}") from exc
        if data.empty:
            continue
        rates[currency] = round(float(data["Close"].iloc[-1]), 4)

    if len(rates) <= 1:
        raise RatesUnavailable(f"No rates available for base {base}")
    return rates
