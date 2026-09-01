"""TW Market Data vendor for Taiwan-listed equities (TWSE / TPEx).

This vendor adds coverage the US-focused defaults do not carry: Taiwan daily
prices, the Taiwan-specific monthly revenue disclosure, and the official
financial statements — sourced from the TW Market Data API via the ``twmd``
client (pure-Python: httpx + pandas, no compiled dependencies).

It is a *data* vendor. It returns records as the source published them and adds
no analysis, scoring, ranking, or opinion. What the data means is the calling
agent's job, not this module's.

Look-ahead safety
-----------------
Statement and revenue readers filter to rows dated on or before ``curr_date``,
so a backtest at ``curr_date`` never sees a row it could not have seen then. This
is the same discipline as
``alpha_vantage_fundamentals._filter_reports_by_date``: a period-based cut.

The reader prefers a genuine publication-date column
(``announcement_date`` / ``source_publish_date``) when one is present *and
usable*, and otherwise falls back to the period column (``month`` / ``report_date``),
naming the basis it used in the header so the cut is never silently
misrepresented. "Usable" matters: some current datasets carry a publication-date
column whose values are all identical — a bulk-load timestamp, not a per-row
disclosure date — which cannot discriminate rows and would wrongly hide
everything before it. Such a column is detected and skipped in favour of the
period cut.

A stronger, true point-in-time filter — one that reflects exactly what was known
on ``curr_date``, including restatements — is deliberately **not** claimed here.
It depends on per-row disclosure dates being verified reliable across the
datasets, which is tracked separately. Until then this vendor makes the same
period-based assurance the existing vendors make, no more.

Free tier
---------
Five sample tickers — 2330, 2317, 2454, 0050, 2603 — return live prices and
monthly revenue with no API key, so the vendor is demonstrable out of the box.
Everything else needs ``TWMD_API_KEY``; without it those calls raise
``VendorNotConfiguredError`` and the router moves on, surfacing a message that
points to free registration.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from .errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)

logger = logging.getLogger(__name__)

# Integration marker sent on every request so the publisher can attribute
# TradingAgents traffic (shared measurement across the ecosystem plugins).
_SOURCE = "ecosys/tradingagents"

# Yahoo-style suffixes a user may append to a Taiwan code. twmd wants the bare
# code (``2330``), so these are stripped before the request.
_TW_SUFFIXES = (".TW", ".TWO")

# Publication-date columns, most-specific first. A row is visible at curr_date
# only if the earliest present one of these is <= curr_date.
_PUBLICATION_COLUMNS = ("announcement_date", "source_publish_date", "publish_date")

# Period columns, used only for labelling and as the last-resort look-ahead key.
_PERIOD_COLUMNS = ("report_date", "period", "month", "date")


def _client():
    """Build a twmd client, or raise the router's not-configured error.

    ``twmd`` is an optional dependency; a missing install is a configuration
    problem the router should route around, not a crash.
    """
    try:
        from twmd import Client
    except ImportError as exc:  # pragma: no cover - exercised via router only
        raise VendorNotConfiguredError(
            "The twmd client is required for the Taiwan (twmd) vendor. "
            "Install it with: pip install twmarketdata"
        ) from exc
    return Client(source=_SOURCE)


def _canonical(symbol: str) -> str:
    """Return the bare Taiwan code twmd expects (strip a Yahoo ``.TW`` suffix)."""
    s = (symbol or "").strip().upper()
    for suffix in _TW_SUFFIXES:
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def _call(func, canonical: str, *args, **kwargs):
    """Invoke a twmd client method, mapping its errors onto the router taxonomy.

    ``canonical`` is used only for the rate-limit message; ``args``/``kwargs`` pass
    straight through to ``func`` (so a ``symbol=`` kwarg does not collide with this
    wrapper's own parameters).
    """
    from twmd import TwmdAuthError, TwmdPaymentRequired, TwmdRateLimitError

    try:
        return func(*args, **kwargs)
    except (TwmdAuthError, TwmdPaymentRequired) as exc:
        # No key, invalid key, or an unentitled key. All mean "this vendor
        # cannot serve the call as configured" — route around it, and let the
        # message guide the user to a (free) key.
        raise VendorNotConfiguredError(
            f"TW Market Data needs an API key for this request "
            f"({getattr(exc, 'error_code', None) or 'authentication required'}). "
            f"Free registration takes about three minutes at twmarketdata.com; "
            f"set TWMD_API_KEY once you have one. Five sample tickers "
            f"(2330, 2317, 2454, 0050, 2603) work without a key for prices and "
            f"monthly revenue."
        ) from exc
    except TwmdRateLimitError as exc:
        raise VendorRateLimitError(f"TW Market Data rate-limited {canonical!r}") from exc


def _is_usable_date_column(series: pd.Series) -> bool:
    """Whether a date column can discriminate rows for a look-ahead cut.

    A column whose non-null values are all identical is a bulk-load timestamp,
    not a per-row disclosure date; cutting on it would hide every row before that
    one date regardless of period, so it is treated as unusable.
    """
    non_null = series.dropna()
    return non_null.nunique() > 1


def _visible_at(df: pd.DataFrame, curr_date: Optional[str]) -> tuple[pd.DataFrame, str]:
    """Drop rows dated after ``curr_date``. Returns (frame, basis-note).

    Prefers a usable publication-date column; otherwise falls back to the period
    column. The basis note names which column and which kind of cut was made, so
    the header never overstates what was applied.
    """
    if not curr_date or df.empty:
        return df, "no date filter"
    for col in _PUBLICATION_COLUMNS:
        if col in df.columns and _is_usable_date_column(df[col]):
            kept = df[df[col].astype(str) <= curr_date]
            return kept, f"published on/before {curr_date} (by {col})"
    for col in _PERIOD_COLUMNS:
        if col in df.columns:
            kept = df[df[col].astype(str) <= curr_date]
            return kept, (
                f"period on/before {curr_date} (by {col}; period-based cut, the "
                f"same assurance the other vendors make — not a per-row "
                f"point-in-time filter)"
            )
    return df, "no usable date column found; returned unfiltered"


def _header(title: str, canonical: str, symbol: str, rows: int, extra: str = "") -> str:
    label = canonical if canonical == symbol.strip().upper() else f"{canonical} (from {symbol})"
    head = f"# {title} for {label}\n# Source: TW Market Data (official Taiwan exchanges)\n"
    head += f"# Total records: {rows}\n"
    if extra:
        head += f"# {extra}\n"
    return head + "\n"


def _frame_to_output(df: pd.DataFrame, title: str, canonical: str, symbol: str, note: str) -> str:
    lineage = df.attrs.get("lineage") if hasattr(df, "attrs") else None
    data_as_of = df.attrs.get("data_as_of") if hasattr(df, "attrs") else None
    extra_bits = []
    if data_as_of:
        extra_bits.append(f"data_as_of: {data_as_of}")
    if isinstance(lineage, dict) and lineage.get("provider"):
        extra_bits.append(f"provider: {lineage['provider']}")
    if note:
        extra_bits.append(f"look-ahead: {note}")
    extra = "; ".join(extra_bits)
    return _header(title, canonical, symbol, len(df), extra) + df.to_csv(index=False)


# ---------------------------------------------------------------------------
# core_stock_apis
# ---------------------------------------------------------------------------

def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Daily OHLCV for a Taiwan-listed symbol, ``start_date``..``end_date`` inclusive.

    Free for the five sample tickers; any other ticker needs ``TWMD_API_KEY``.
    """
    canonical = _canonical(symbol)
    client = _client()
    df = _call(
        client.get_dataset, canonical,
        "twse-daily-price", symbol=canonical, date_from=start_date, date_to=end_date,
    )
    if df.empty:
        raise NoMarketDataError(symbol, canonical, f"no rows between {start_date} and {end_date}")
    if "date" in df.columns:
        df = df[(df["date"].astype(str) >= start_date) & (df["date"].astype(str) <= end_date)]
    if df.empty:
        raise NoMarketDataError(symbol, canonical, f"no rows between {start_date} and {end_date}")
    return _frame_to_output(df, f"Taiwan daily prices {start_date} to {end_date}", canonical, symbol, "")


# ---------------------------------------------------------------------------
# fundamental_data
# ---------------------------------------------------------------------------

def _statement(dataset: str, title: str, ticker: str, curr_date: Optional[str]) -> str:
    canonical = _canonical(ticker)
    client = _client()
    # Forward as_of when we have a curr_date. twmd's as_of support on these
    # endpoints is unverified, so we do not rely on it — the client-side
    # publication-date filter below is the real look-ahead guard.
    df = _call(
        client.get_dataset, canonical,
        dataset, symbol=canonical, as_of=curr_date,
    )
    if df.empty:
        raise NoMarketDataError(ticker, canonical, f"no {title.lower()} data")
    df, note = _visible_at(df, curr_date)
    if df.empty:
        raise NoMarketDataError(ticker, canonical, f"no {title.lower()} published on/before {curr_date}")
    return _frame_to_output(df, title, canonical, ticker, note)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: Optional[str] = None) -> str:
    """Income statement, filtered to rows published on/before ``curr_date``."""
    return _statement("income-statement", "Taiwan income statement", ticker, curr_date)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: Optional[str] = None) -> str:
    """Balance sheet, filtered to rows published on/before ``curr_date``."""
    return _statement("balance-sheet", "Taiwan balance sheet", ticker, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: Optional[str] = None) -> str:
    """Cash flow statement, filtered to rows published on/before ``curr_date``."""
    return _statement("cash-flow-statement", "Taiwan cash flow statement", ticker, curr_date)


def get_fundamentals(ticker: str, curr_date: Optional[str] = None) -> str:
    """Monthly revenue history — the Taiwan-specific monthly disclosure.

    Free for the five sample tickers. Rows are filtered to those announced on or
    before ``curr_date`` so a historical run does not see revenue that had not
    yet been reported. The MoM and YoY figures are the publisher's own computed
    fields, reported as given.
    """
    canonical = _canonical(ticker)
    client = _client()
    # Ask for several years so a backtest at an older curr_date has history to
    # cut down to, rather than only the most recent months.
    df = _call(client.get_dataset, canonical, "monthly-revenue", symbol=canonical, limit=120)
    if df.empty:
        raise NoMarketDataError(ticker, canonical, "no monthly revenue data")
    df, note = _visible_at(df, curr_date)
    if df.empty:
        raise NoMarketDataError(ticker, canonical, f"no monthly revenue announced on/before {curr_date}")
    return _frame_to_output(df, "Taiwan monthly revenue", canonical, ticker, note)
