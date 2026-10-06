"""Yahoo Finance data for the browser UI's Company page.

A live, present-day view: today's quote and Yahoo's latest statements, with no
point-in-time cut (see ``tradingagents.dataflows.company_profile``). It is not a
routed tool, and nothing on an agent or backtest path may call it.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.company_profile import CompanyData, as_number, build_profile
from tradingagents.dataflows.errors import VendorRateLimitError
from tradingagents.dataflows.field_aliases import ALIASES as FIELD_ALIASES
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.ohlcv import raise_for_empty, yf_retry

# Yahoo's names for each field of ``CompanyData``, by where they come from: its
# section of the one alias table every source shares. Names differ between
# yfinance versions and between companies, so add a spelling there rather than
# at a call site.
ALIASES = FIELD_ALIASES["yahoo"]
_TEXT_FIELDS = {"name", "exchange", "sector", "industry", "website", "summary", "currency",
                "financial_currency", "quote_type"}

# Each page view costs Yahoo six requests, so a profile is reused for a while.
CACHE_TTL_SECONDS = 15 * 60
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 64


def pick(get, alternatives):
    """The first of ``alternatives`` that ``get`` has a value for; a tuple of names
    sums those present. None when none is present."""
    for alternative in alternatives:
        if isinstance(alternative, tuple):
            parts = [v for v in map(get, alternative) if v is not None]
            if parts:
                return sum(parts)
        elif (value := get(alternative)) is not None:
            return value
    return None


def quote_fields(info: dict) -> dict:
    """``Ticker.info`` as the quote fields, blanks left out."""
    def get(key):
        value = info.get(key)
        return None if value is None or value == "" else value

    out = {}
    for name, keys in ALIASES["quote"].items():
        value = pick(get, keys)
        if name in _TEXT_FIELDS:
            value = None if value is None else str(value).strip() or None
        else:
            value = as_number(value)
        if value is not None:
            out[name] = value
    return out


def statement_fields(frame: pd.DataFrame | None, aliases: dict) -> dict[str, dict[str, float]]:
    """A yfinance statement frame (rows by label, a column per period end) as
    ``{period end: {field: value}}``. Blanks are left out, and so is a period with none."""
    if frame is None or getattr(frame, "empty", True):
        return {}
    out = {}
    for column in frame.columns:
        try:
            end = pd.Timestamp(column).date().isoformat()
        except (TypeError, ValueError):
            continue

        def get(label, column=column):
            if label not in frame.index:
                return None
            value = frame.loc[label, column]
            if isinstance(value, pd.Series):  # a label listed twice
                value = value.dropna().iloc[0] if value.notna().any() else None
            return as_number(value)

        values = {name: v for name, labels in aliases.items() if (v := pick(get, labels)) is not None}
        if values:
            out[end] = values
    return out


def price_rows(frame: pd.DataFrame | None) -> list[tuple[str, float, float | None]]:
    """Daily (date, close, volume) from a yfinance history frame, oldest first.

    Dates are the exchange's own calendar days; a day listed twice keeps its last row.
    """
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
        return []
    index = frame.index
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)  # drop the zone, keep the local wall-clock date
    volumes = frame["Volume"] if "Volume" in frame else pd.Series(None, index=frame.index)
    rows: dict[str, tuple[str, float, float | None]] = {}
    for stamp, close, volume in zip(index, frame["Close"], volumes, strict=True):
        if (price := as_number(close)) is not None:
            day = pd.Timestamp(stamp).date().isoformat()
            rows[day] = (day, price, as_number(volume))
    return sorted(rows.values())


def _read(get):
    """One yfinance read, retried while throttled. Any other failure reads as no data,
    so a statement Yahoo lacks leaves the rest of the page standing."""
    try:
        return yf_retry(get)
    except YFRateLimitError as exc:
        raise VendorRateLimitError("Yahoo Finance is rate-limiting requests") from exc
    except Exception:  # noqa: BLE001 — yfinance raises assorted errors for data it lacks
        return None


def _history(ticker) -> list[tuple[str, float, float | None]]:
    # Split-adjusted closes, not dividend-adjusted: the prices people saw, as charted.
    return price_rows(_read(lambda: ticker.history(period="max", auto_adjust=False)))


def _nse_listing(canonical: str) -> str | None:
    """The NSE symbol for a BSE one (``ITC.BO`` -> ``ITC.NS``); numeric BSE codes have none."""
    base, dot, exchange = canonical.rpartition(".")
    return f"{base}.NS" if dot and exchange == "BO" and not base.isdigit() else None


def fetch_company_data(symbol: str) -> CompanyData:
    """Yahoo's data for ``symbol``, uncached and unbuilt, for a caller that lays
    other sources over it (the India data layer) before building the page."""
    return _fetch(symbol, normalize_symbol(symbol))


def _fetch(symbol: str, canonical: str) -> CompanyData:
    ticker = yf.Ticker(canonical)
    quote = quote_fields(_read(lambda: ticker.info) or {})
    prices, prices_from = _history(ticker), None
    # Yahoo serves BSE listings their latest bar only; the NSE listing of the same
    # shares has the history, and the page says whose prices it charts.
    nse = _nse_listing(canonical) if len(prices) < 2 else None
    if nse and len(nse_prices := _history(yf.Ticker(nse))) >= 2:
        prices, prices_from = nse_prices, nse
    # yfinance answers an unknown symbol with a near-empty info dict and no prices.
    if not prices and not (quote.get("name") or quote.get("price")):
        raise_for_empty(symbol, canonical, "quote or price history")
    return CompanyData(
        symbol=canonical,
        quote=quote,
        quarterly=statement_fields(_read(lambda: ticker.quarterly_income_stmt), ALIASES["income"]),
        annual=statement_fields(_read(lambda: ticker.income_stmt), ALIASES["income"]),
        balance=statement_fields(_read(lambda: ticker.balance_sheet), ALIASES["balance"]),
        cashflow=statement_fields(_read(lambda: ticker.cashflow), ALIASES["cashflow"]),
        prices=prices,
        prices_from=prices_from,
        source="Yahoo Finance",
        fetched=datetime.now(),
    )


def build_company_profile(symbol: str) -> dict:
    """The Company page's data for ``symbol``, at most ``CACHE_TTL_SECONDS`` old.

    Raises ``NoMarketDataError`` for a symbol Yahoo does not know, and
    ``VendorRateLimitError`` when Yahoo throttles or cannot be reached.
    """
    canonical = normalize_symbol(symbol)
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(canonical)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    profile = build_profile(_fetch(symbol, canonical))
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[canonical] = (now, profile)
    return profile
