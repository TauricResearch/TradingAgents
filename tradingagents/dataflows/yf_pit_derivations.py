"""Point-in-time reconstruction of yfinance ``Ticker.info`` snapshot fields.

``yfinance.Ticker.info`` always returns *live* values (current market cap,
TTM ratios, 52-week ranges, moving averages, dividend yield) regardless of
the historical date a backtest is simulating. ``y_finance.get_fundamentals``
addresses the look-ahead bug by omitting those fields on historical calls.

This module *reconstructs* the same fields PIT-correctly from data
yfinance does expose with proper time indexing:

* ``Ticker.history(start, end)`` — daily OHLCV bars (price-derived ranges,
  moving averages, market cap close).
* ``Ticker.quarterly_income_stmt`` / ``.quarterly_balance_sheet`` /
  ``.quarterly_cashflow`` — fiscal-period-indexed statements (TTM sums,
  point-in-time stocks, derived ratios).
* ``Ticker.get_shares_full(start, end)`` — historical share count series.
* ``Ticker.dividends`` — date-indexed per-share dividend payments.

Forward-looking fields (Forward EPS, Forward P/E, PEG Ratio) are
intentionally not reconstructed — they are analyst projections, not
historical fact, and have no PIT-correct yfinance source.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


# yfinance row labels for each statement line item often vary by ticker /
# statement vintage. We accept the first match against a list of synonyms.
_INCOME_KEYS = {
    "revenue": ["Total Revenue", "TotalRevenue"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
    "operating_income": [
        "Operating Income",
        "OperatingIncome",
        "Total Operating Income As Reported",
    ],
    "net_income": [
        "Net Income",
        "Net Income Common Stockholders",
        "NetIncome",
        "Net Income From Continuing Operation Net Minority Interest",
        "Net Income Continuous Operations",
    ],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
}

_BALANCE_KEYS = {
    "total_assets": ["Total Assets"],
    "total_equity": [
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ],
    "total_debt": ["Total Debt", "Net Debt"],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
}

_CASHFLOW_KEYS = {
    "free_cash_flow": ["Free Cash Flow", "FreeCashFlow"],
}


def _strip_tz(idx):
    """yfinance sometimes returns tz-aware indexes; PIT comparisons need naive."""
    try:
        if getattr(idx, "tz", None) is not None:
            return idx.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return idx


def _first_match(df: Optional[pd.DataFrame], keys):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _ttm_sum(df, synonyms, curr_date) -> Optional[float]:
    """Sum the four most-recent quarterly values whose period ends on or
    before ``curr_date``. Returns ``None`` if fewer than four are available
    or any of those four are NaN — partial TTM is worse than no TTM."""
    row = _first_match(df, synonyms)
    if row is None:
        return None
    cutoff = pd.Timestamp(curr_date)
    cols = [pd.Timestamp(c) for c in row.index if pd.notna(c)]
    cols = [c for c in cols if c <= cutoff]
    if len(cols) < 4:
        return None
    last4 = sorted(cols, reverse=True)[:4]
    vals = [row[c] for c in last4]
    if any(pd.isna(v) for v in vals):
        return None
    return float(sum(vals))


def _latest_le(df, synonyms, curr_date) -> Optional[float]:
    """Most recent point-in-time value of a balance-sheet line item with
    period ending on or before ``curr_date``."""
    row = _first_match(df, synonyms)
    if row is None:
        return None
    cutoff = pd.Timestamp(curr_date)
    cols = [pd.Timestamp(c) for c in row.index if pd.notna(c) and pd.Timestamp(c) <= cutoff]
    if not cols:
        return None
    latest = max(cols)
    val = row[latest]
    return float(val) if pd.notna(val) else None


def _close_at(history: pd.DataFrame, curr_date) -> Optional[float]:
    """Most recent close on or before ``curr_date``."""
    if history is None or history.empty or "Close" not in history.columns:
        return None
    h = history.copy()
    h.index = _strip_tz(h.index)
    cutoff = pd.Timestamp(curr_date)
    bars = h[h.index <= cutoff]
    if bars.empty:
        return None
    val = bars["Close"].iloc[-1]
    return float(val) if pd.notna(val) else None


def _shares_at(shares, curr_date) -> Optional[float]:
    """Share count on or before ``curr_date``. yfinance's ``get_shares_full``
    returns a Series indexed by datetime."""
    if shares is None or len(shares) == 0:
        return None
    s = shares.copy()
    s.index = _strip_tz(s.index)
    cutoff = pd.Timestamp(curr_date)
    s = s[s.index <= cutoff]
    if s.empty:
        return None
    val = s.iloc[-1]
    return float(val) if pd.notna(val) else None


def _safe_div(num, den):
    if num is None or den is None or den == 0:
        return None
    return num / den


def derive_pit_fundamentals(ticker_obj, curr_date: str) -> dict:
    """Reconstruct fundamental snapshot fields PIT-correctly.

    Returns a dict keyed by the same human-readable labels
    ``y_finance.get_fundamentals`` uses for live mode. Only fields that
    could be successfully derived appear; sparse/missing inputs degrade
    gracefully (one missing field does not poison the rest).

    Forward-looking analyst projections (Forward EPS, Forward P/E, PEG)
    are intentionally absent — there is no PIT-correct yfinance source
    for analyst estimates as-of a historical date.
    """
    cutoff = pd.Timestamp(curr_date)
    lookback_start = cutoff - pd.Timedelta(days=400)

    def _safe_call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    def _safe_attr(name):
        try:
            return getattr(ticker_obj, name)
        except Exception:
            return None

    history = _safe_call(
        ticker_obj.history,
        start=lookback_start.strftime("%Y-%m-%d"),
        end=(cutoff + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if history is None:
        history = pd.DataFrame()

    income = _safe_attr("quarterly_income_stmt")
    balance = _safe_attr("quarterly_balance_sheet")
    cashflow = _safe_attr("quarterly_cashflow")
    shares = _safe_call(
        ticker_obj.get_shares_full,
        start=lookback_start,
        end=cutoff + pd.Timedelta(days=1),
    )
    dividends = _safe_attr("dividends")

    close_px = _close_at(history, curr_date)
    shares_out = _shares_at(shares, curr_date)

    revenue_ttm = _ttm_sum(income, _INCOME_KEYS["revenue"], curr_date)
    gross_profit_ttm = _ttm_sum(income, _INCOME_KEYS["gross_profit"], curr_date)
    operating_income_ttm = _ttm_sum(income, _INCOME_KEYS["operating_income"], curr_date)
    net_income_ttm = _ttm_sum(income, _INCOME_KEYS["net_income"], curr_date)
    ebitda_ttm = _ttm_sum(income, _INCOME_KEYS["ebitda"], curr_date)
    fcf_ttm = _ttm_sum(cashflow, _CASHFLOW_KEYS["free_cash_flow"], curr_date)

    total_assets = _latest_le(balance, _BALANCE_KEYS["total_assets"], curr_date)
    total_equity = _latest_le(balance, _BALANCE_KEYS["total_equity"], curr_date)
    total_debt = _latest_le(balance, _BALANCE_KEYS["total_debt"], curr_date)
    current_assets = _latest_le(balance, _BALANCE_KEYS["current_assets"], curr_date)
    current_liab = _latest_le(balance, _BALANCE_KEYS["current_liabilities"], curr_date)

    out: dict = {}

    if not (history is None or history.empty):
        h = history.copy()
        h.index = _strip_tz(h.index)
        h = h[h.index <= cutoff]
        if not h.empty:
            year_window = h[h.index >= cutoff - pd.Timedelta(days=365)]
            if not year_window.empty and "High" in year_window.columns:
                out["52 Week High"] = round(float(year_window["High"].max()), 2)
                out["52 Week Low"] = round(float(year_window["Low"].min()), 2)
            window_50 = h.tail(50)
            if len(window_50) >= 10:
                out["50 Day Average"] = round(float(window_50["Close"].mean()), 2)
            window_200 = h.tail(200)
            if len(window_200) >= 50:
                out["200 Day Average"] = round(float(window_200["Close"].mean()), 2)

    if close_px is not None and shares_out is not None and shares_out > 0:
        out["Market Cap"] = int(round(close_px * shares_out))

    if revenue_ttm is not None:
        out["Revenue (TTM)"] = int(round(revenue_ttm))
    if gross_profit_ttm is not None:
        out["Gross Profit"] = int(round(gross_profit_ttm))
    if ebitda_ttm is not None:
        out["EBITDA"] = int(round(ebitda_ttm))
    if net_income_ttm is not None:
        out["Net Income"] = int(round(net_income_ttm))
    if fcf_ttm is not None:
        out["Free Cash Flow"] = int(round(fcf_ttm))

    margin = _safe_div(net_income_ttm, revenue_ttm)
    if margin is not None:
        out["Profit Margin"] = round(margin, 4)
    op_margin = _safe_div(operating_income_ttm, revenue_ttm)
    if op_margin is not None:
        out["Operating Margin"] = round(op_margin, 4)

    if net_income_ttm is not None and shares_out and shares_out > 0:
        eps_ttm = net_income_ttm / shares_out
        out["EPS (TTM)"] = round(eps_ttm, 2)
        if close_px is not None and eps_ttm > 0:
            out["PE Ratio (TTM)"] = round(close_px / eps_ttm, 2)

    roe = _safe_div(net_income_ttm, total_equity)
    if roe is not None:
        out["Return on Equity"] = round(roe, 4)
    roa = _safe_div(net_income_ttm, total_assets)
    if roa is not None:
        out["Return on Assets"] = round(roa, 4)

    if total_debt is not None and total_equity and total_equity != 0:
        out["Debt to Equity"] = round(total_debt / total_equity * 100, 2)
    if current_assets is not None and current_liab and current_liab != 0:
        out["Current Ratio"] = round(current_assets / current_liab, 2)

    if total_equity is not None and shares_out and shares_out > 0:
        bvps = total_equity / shares_out
        out["Book Value"] = round(bvps, 2)
        if close_px is not None and bvps > 0:
            out["Price to Book"] = round(close_px / bvps, 2)

    if dividends is not None and len(dividends) > 0 and close_px:
        d = dividends.copy()
        d.index = _strip_tz(d.index)
        ttm_div_window = d[(d.index <= cutoff) & (d.index > cutoff - pd.Timedelta(days=365))]
        ttm_div = float(ttm_div_window.sum()) if len(ttm_div_window) > 0 else 0.0
        if ttm_div > 0:
            out["Dividend Yield"] = round(ttm_div / close_px, 4)

    return out
