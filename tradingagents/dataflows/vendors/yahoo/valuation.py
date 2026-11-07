"""Raw inputs for the valuation analyst from Yahoo Finance.

Yahoo dates a statement by the period it covers and ``Ticker.info`` is a
present-day snapshot, so neither carries a historical vintage. A run dated in the
past is therefore served nothing from here (it raises ``NoMarketDataError`` with
the reason); SEC EDGAR serves US filers as filed. Money is unscaled, in the
currency the company reports in, and a figure Yahoo does not give is None.
"""

from __future__ import annotations

import math

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.currencies import main_unit
from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, yf_retry

# Yahoo industries whose cash flows a free-cash-flow DCF cannot value.
_FINANCIAL_INDUSTRY_WORDS = ("bank", "insurance", "thrift", "mortgage finance", "credit services",
                             "financial conglomerates")


def _withheld(ticker: str, canonical: str, as_of_date: str | None, what: str) -> None:
    if is_historical(as_of_date):
        raise NoMarketDataError(
            ticker, canonical,
            f"{what} from Yahoo are withheld for {as_of_date}: Yahoo reports no filing date and "
            "only present-day values, so it cannot show what was public then",
        )


def _number(value) -> float | None:
    """A finite float, or None for a missing, NaN or non-numeric cell."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _row(frame, *names) -> pd.Series | None:
    """The first named row of a statement frame, as a Series by period (newest first)."""
    if frame is None or getattr(frame, "empty", True):
        return None
    for name in names:
        if name in frame.index:
            return frame.loc[name]
    return None


def _latest_value(series) -> float | None:
    """The newest period's figure that is not NaN."""
    if series is None:
        return None
    for cell in series.sort_index(ascending=False):
        number = _number(cell)
        if number is not None:
            return number
    return None


def is_financial_industry(industry: str | None, sector: str | None = None) -> bool:
    text = f"{industry or ''}".lower()
    return (sector or "").lower().startswith("financial") and any(w in text for w in _FINANCIAL_INDUSTRY_WORDS)


def get_valuation_inputs(ticker: str, as_of_date: str | None = None) -> dict:
    """The raw figures a DCF needs, from Yahoo, for a run dated today."""
    canonical = normalize_symbol(ticker)
    _withheld(ticker, canonical, as_of_date, "statements and profile")

    info = yf_retry(lambda: yf.Ticker(canonical).info)
    if not info:
        raise_for_empty(ticker, canonical, "company profile")
    cashflow = yf_retry(lambda: yf.Ticker(canonical).cashflow)
    income = yf_retry(lambda: yf.Ticker(canonical).financials)
    balance = yf_retry(lambda: yf.Ticker(canonical).balance_sheet)

    cfo, capex = _row(cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities"), \
        _row(cashflow, "Capital Expenditure")
    if cfo is None or cfo.dropna().empty:
        raise_for_empty(ticker, canonical, "annual operating cash flow")
    cfo = cfo.dropna().sort_index()
    periods = [
        {
            "end": pd.Timestamp(end).strftime("%Y-%m-%d"),
            "cfo": float(value),
            # Yahoo reports capital expenditure as a negative outflow.
            "capex": None if capex is None or _number(capex.get(end)) is None else abs(float(capex[end])),
        }
        for end, value in cfo.items()
    ][-5:]

    industry, sector = info.get("industry"), info.get("sector")
    financial = is_financial_industry(industry, sector)
    shares = _number(info.get("sharesOutstanding")) or _latest_value(_row(balance, "Ordinary Shares Number"))
    return {
        "source": "yfinance",
        "as_of": as_of_date,
        "currency": info.get("financialCurrency"),
        "quote_currency": info.get("currency"),
        "periods": periods,
        "interest_expense": _latest_value(_row(income, "Interest Expense")),
        "income_tax": _latest_value(_row(income, "Tax Provision")),
        "pretax_income": _latest_value(_row(income, "Pretax Income")),
        "net_income": _latest_value(_row(income, "Net Income")),
        "revenue": _latest_value(_row(income, "Total Revenue")),
        "total_debt": _latest_value(_row(balance, "Total Debt")),
        "cash": _latest_value(_row(balance, "Cash And Cash Equivalents",
                                   "Cash Cash Equivalents And Short Term Investments")),
        "equity": _latest_value(_row(balance, "Stockholders Equity", "Common Stock Equity")),
        "shares": shares,
        "is_financial": financial,
        "financial_reason": f"Yahoo classifies it as {sector} / {industry}" if financial else "",
        "industry": industry,
        "notes": ["Yahoo Finance annual statements and present-day profile; money unscaled, in the "
                  "currency the company reports in."],
    }


def _peer_row(symbol: str) -> dict:
    """One peer's multiples as Yahoo computes them; raises if its profile cannot be read."""
    info = yf_retry(lambda: yf.Ticker(symbol).info) or {}
    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "pe": _number(info.get("trailingPE")),
        "ev_ebitda": _number(info.get("enterpriseToEbitda")),
        "ps": _number(info.get("priceToSalesTrailing12Months")),
        "pb": _number(info.get("priceToBook")),
        "roe": _number(info.get("returnOnEquity")),
        "market_cap": _number(info.get("marketCap")),
        "currency": main_unit(info.get("currency")),
    }


def get_peer_snapshot(ticker: str, as_of_date: str | None = None,
                      peers: list[str] | None = None, max_peers: int = 8) -> dict:
    """The target's own multiple inputs and its peers' multiples, for a run dated today.

    ``peers`` is the configured list; without one, the largest companies in the
    target's Yahoo industry.
    """
    canonical = normalize_symbol(ticker)
    _withheld(ticker, canonical, as_of_date, "peer multiples")
    info = yf_retry(lambda: yf.Ticker(canonical).info)
    if not info:
        raise_for_empty(ticker, canonical, "company profile")

    industry_key, notes = info.get("industryKey"), []
    if peers:
        symbols, peer_source = [normalize_symbol(p) for p in peers], "configured peer list"
    elif industry_key:
        top = yf_retry(lambda: yf.Industry(industry_key).top_companies)
        symbols = [] if top is None else [str(s) for s in top.index]
        peer_source = f"largest companies in Yahoo industry '{industry_key}'"
    else:
        symbols, peer_source = [], "none: Yahoo gives no industry for this company"
    symbols = [s for s in dict.fromkeys(symbols) if s != canonical][:max_peers]

    rows, failed = [], []
    for symbol in symbols:
        try:
            rows.append(_peer_row(symbol))
        except Exception as exc:  # noqa: BLE001 - one unreadable peer must not end the report
            failed.append(f"{symbol} ({type(exc).__name__})")
    if failed:
        notes.append("Peers whose profile could not be read: " + ", ".join(failed))

    return {
        "source": "yfinance",
        "as_of": as_of_date,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "is_financial": is_financial_industry(info.get("industry"), info.get("sector")),
        "peer_source": peer_source,
        "peers": rows,
        "target": {
            "name": info.get("shortName") or info.get("longName"),
            "quote_currency": info.get("currency"),
            "reporting_currency": info.get("financialCurrency"),
            "eps": _number(info.get("trailingEps")),
            "ebitda": _number(info.get("ebitda")),
            "revenue": _number(info.get("totalRevenue")),
            "book_value_per_share": _number(info.get("bookValue")),
            "total_debt": _number(info.get("totalDebt")),
            "total_cash": _number(info.get("totalCash")),
            "shares": _number(info.get("sharesOutstanding")),
            "roe": _number(info.get("returnOnEquity")),
            "market_cap": _number(info.get("marketCap")),
        },
        "notes": notes,
    }
