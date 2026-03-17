"""Trailing Twelve Months (TTM) trend analysis across 8 quarters."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Column name normalisers for inconsistent vendor schemas
# ---------------------------------------------------------------------------

_INCOME_REVENUE_COLS = [
    "Total Revenue", "TotalRevenue", "totalRevenue",
    "Revenue", "revenue",
]
_INCOME_GROSS_PROFIT_COLS = [
    "Gross Profit", "GrossProfit", "grossProfit",
]
_INCOME_OPERATING_INCOME_COLS = [
    "Operating Income", "OperatingIncome", "operatingIncome",
    "Total Operating Income As Reported",
]
_INCOME_EBITDA_COLS = [
    "EBITDA", "Ebitda", "ebitda",
    "Normalized EBITDA",
]
_INCOME_NET_INCOME_COLS = [
    "Net Income", "NetIncome", "netIncome",
    "Net Income From Continuing Operation Net Minority Interest",
]

_BALANCE_TOTAL_ASSETS_COLS = [
    "Total Assets", "TotalAssets", "totalAssets",
]
_BALANCE_TOTAL_DEBT_COLS = [
    "Total Debt", "TotalDebt", "totalDebt",
    "Long Term Debt", "LongTermDebt",
]
_BALANCE_EQUITY_COLS = [
    "Stockholders Equity", "StockholdersEquity",
    "Total Stockholder Equity", "TotalStockholderEquity",
    "Common Stock Equity", "CommonStockEquity",
]

_CASHFLOW_FCF_COLS = [
    "Free Cash Flow", "FreeCashFlow", "freeCashFlow",
]
_CASHFLOW_OPERATING_COLS = [
    "Operating Cash Flow", "OperatingCashflow", "operatingCashflow",
    "Total Cash From Operating Activities",
]
_CASHFLOW_CAPEX_COLS = [
    "Capital Expenditure", "CapitalExpenditure", "capitalExpenditure",
    "Capital Expenditures",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the first matching column name, or None."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _parse_financial_csv(csv_text: str) -> Optional[pd.DataFrame]:
    """
    Parse a CSV string returned by vendor data functions.

    Alpha Vantage and yfinance both return CSV strings where:
    - Rows are metrics, columns are dates  (transposed layout for AV)
    - OR columns are metrics, rows are dates  (yfinance layout)

    We normalise to: index=date (ascending), columns=metrics.
    """
    if not csv_text or not csv_text.strip():
        return None
    try:
        df = pd.read_csv(StringIO(csv_text), index_col=0)
    except Exception:
        return None

    if df.empty:
        return None

    # Detect orientation: if index looks like dates, columns are metrics.
    # If columns look like dates, transpose.
    def _looks_like_dates(values) -> bool:
        count = 0
        for v in list(values)[:5]:
            try:
                pd.to_datetime(str(v))
                count += 1
            except Exception:
                pass
        return count >= min(2, len(list(values)[:5]))

    if _looks_like_dates(df.columns):
        # AV-style: rows=metrics, cols=dates — transpose
        df = df.T

    # Parse index as dates
    try:
        df.index = pd.to_datetime(df.index)
    except Exception:
        return None

    df.sort_index(inplace=True)  # ascending (oldest first)

    # Convert all columns to numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _safe_get(df: pd.DataFrame, col_candidates: list[str], row_idx: int) -> Optional[float]:
    """Get a value from a DataFrame by column candidates and row index."""
    col = _find_col(df, col_candidates)
    if col is None:
        return None
    try:
        val = df.iloc[row_idx][col]
        return float(val) if pd.notna(val) else None
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


def _fmt(val: Optional[float], billions: bool = True, suffix: str = "") -> str:
    if val is None:
        return "N/A"
    if billions:
        return f"${val / 1e9:.2f}B{suffix}"
    return f"{val:.2f}{suffix}"


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_ttm_metrics(
    income_csv: str,
    balance_csv: str,
    cashflow_csv: str,
    n_quarters: int = 8,
) -> dict:
    """
    Compute TTM and multi-quarter trend metrics from vendor CSV strings.

    Args:
        income_csv: CSV text from get_income_statement (quarterly)
        balance_csv: CSV text from get_balance_sheet (quarterly)
        cashflow_csv: CSV text from get_cashflow (quarterly)
        n_quarters: Number of quarters to include (default 8)

    Returns:
        dict with keys: quarters_available, ttm, quarterly, trends, metadata
    """
    income_df = _parse_financial_csv(income_csv)
    balance_df = _parse_financial_csv(balance_csv)
    cashflow_df = _parse_financial_csv(cashflow_csv)

    result = {
        "quarters_available": 0,
        "ttm": {},
        "quarterly": [],
        "trends": {},
        "metadata": {"parse_errors": []},
    }

    if income_df is None:
        result["metadata"]["parse_errors"].append("income statement parse failed")
    if balance_df is None:
        result["metadata"]["parse_errors"].append("balance sheet parse failed")
    if cashflow_df is None:
        result["metadata"]["parse_errors"].append("cash flow parse failed")

    # Use income statement to anchor quarters
    if income_df is None:
        return result

    # Limit to last n_quarters
    income_df = income_df.tail(n_quarters)
    n = len(income_df)
    result["quarters_available"] = n

    if balance_df is not None:
        balance_df = balance_df.tail(n_quarters)
    if cashflow_df is not None:
        cashflow_df = cashflow_df.tail(n_quarters)

    # --- TTM: sum last 4 quarters for flow items ---
    ttm_n = min(4, n)
    ttm_income = income_df.tail(ttm_n)

    def _ttm_sum(df, cols) -> Optional[float]:
        col = _find_col(df, cols)
        if col is None:
            return None
        vals = pd.to_numeric(df.tail(ttm_n)[col], errors="coerce").dropna()
        return float(vals.sum()) if len(vals) > 0 else None

    def _ttm_latest(df, cols) -> Optional[float]:
        """Stock items: use most recent value."""
        if df is None:
            return None
        col = _find_col(df, cols)
        if col is None:
            return None
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        return float(series.iloc[-1]) if len(series) > 0 else None

    ttm_revenue = _ttm_sum(ttm_income, _INCOME_REVENUE_COLS)
    ttm_gross_profit = _ttm_sum(ttm_income, _INCOME_GROSS_PROFIT_COLS)
    ttm_operating_income = _ttm_sum(ttm_income, _INCOME_OPERATING_INCOME_COLS)
    ttm_ebitda = _ttm_sum(ttm_income, _INCOME_EBITDA_COLS)
    ttm_net_income = _ttm_sum(ttm_income, _INCOME_NET_INCOME_COLS)

    ttm_total_assets = _ttm_latest(balance_df, _BALANCE_TOTAL_ASSETS_COLS)
    ttm_total_debt = _ttm_latest(balance_df, _BALANCE_TOTAL_DEBT_COLS)
    ttm_equity = _ttm_latest(balance_df, _BALANCE_EQUITY_COLS)

    ttm_fcf = _ttm_sum(cashflow_df, _CASHFLOW_FCF_COLS) if cashflow_df is not None else None
    ttm_operating_cf = _ttm_sum(cashflow_df, _CASHFLOW_OPERATING_COLS) if cashflow_df is not None else None

    # Derived ratios
    ttm_gross_margin = (ttm_gross_profit / ttm_revenue * 100) if ttm_revenue and ttm_gross_profit else None
    ttm_operating_margin = (ttm_operating_income / ttm_revenue * 100) if ttm_revenue and ttm_operating_income else None
    ttm_net_margin = (ttm_net_income / ttm_revenue * 100) if ttm_revenue and ttm_net_income else None
    ttm_roe = (ttm_net_income / ttm_equity * 100) if ttm_net_income and ttm_equity and ttm_equity != 0 else None
    ttm_debt_to_equity = (ttm_total_debt / ttm_equity) if ttm_total_debt and ttm_equity and ttm_equity != 0 else None

    result["ttm"] = {
        "revenue": ttm_revenue,
        "gross_profit": ttm_gross_profit,
        "operating_income": ttm_operating_income,
        "ebitda": ttm_ebitda,
        "net_income": ttm_net_income,
        "free_cash_flow": ttm_fcf,
        "operating_cash_flow": ttm_operating_cf,
        "total_assets": ttm_total_assets,
        "total_debt": ttm_total_debt,
        "equity": ttm_equity,
        "gross_margin_pct": ttm_gross_margin,
        "operating_margin_pct": ttm_operating_margin,
        "net_margin_pct": ttm_net_margin,
        "roe_pct": ttm_roe,
        "debt_to_equity": ttm_debt_to_equity,
    }

    # --- Quarterly breakdown ---
    quarterly = []
    for i in range(n):
        q_date = income_df.index[i].strftime("%Y-%m-%d") if hasattr(income_df.index[i], "strftime") else str(income_df.index[i])
        q_rev = _safe_get(income_df, _INCOME_REVENUE_COLS, i)
        q_gp = _safe_get(income_df, _INCOME_GROSS_PROFIT_COLS, i)
        q_oi = _safe_get(income_df, _INCOME_OPERATING_INCOME_COLS, i)
        q_ni = _safe_get(income_df, _INCOME_NET_INCOME_COLS, i)
        q_gm = (q_gp / q_rev * 100) if q_rev and q_gp else None
        q_om = (q_oi / q_rev * 100) if q_rev and q_oi else None
        q_nm = (q_ni / q_rev * 100) if q_rev and q_ni else None

        q_eq = _safe_get(balance_df, _BALANCE_EQUITY_COLS, i) if balance_df is not None and i < len(balance_df) else None
        q_debt = _safe_get(balance_df, _BALANCE_TOTAL_DEBT_COLS, i) if balance_df is not None and i < len(balance_df) else None
        q_fcf = _safe_get(cashflow_df, _CASHFLOW_FCF_COLS, i) if cashflow_df is not None and i < len(cashflow_df) else None

        quarterly.append({
            "date": q_date,
            "revenue": q_rev,
            "gross_profit": q_gp,
            "operating_income": q_oi,
            "net_income": q_ni,
            "gross_margin_pct": q_gm,
            "operating_margin_pct": q_om,
            "net_margin_pct": q_nm,
            "equity": q_eq,
            "total_debt": q_debt,
            "free_cash_flow": q_fcf,
        })

    result["quarterly"] = quarterly

    # --- Trend analysis ---
    if n >= 2:
        latest_rev = quarterly[-1]["revenue"]
        prev_rev = quarterly[-2]["revenue"]
        yoy_rev = quarterly[-4]["revenue"] if n >= 5 else None

        result["trends"] = {
            "revenue_qoq_pct": _pct_change(latest_rev, prev_rev),
            "revenue_yoy_pct": _pct_change(latest_rev, yoy_rev),
            "gross_margin_direction": _margin_trend([q["gross_margin_pct"] for q in quarterly]),
            "operating_margin_direction": _margin_trend([q["operating_margin_pct"] for q in quarterly]),
            "net_margin_direction": _margin_trend([q["net_margin_pct"] for q in quarterly]),
        }

    return result


def _margin_trend(margins: list) -> str:
    """Classify margin trend from list of quarterly values (oldest first)."""
    clean = [m for m in margins if m is not None]
    if len(clean) < 3:
        return "insufficient data"
    recent = clean[-3:]
    if recent[-1] > recent[0]:
        return "expanding"
    elif recent[-1] < recent[0]:
        return "contracting"
    return "stable"


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_ttm_report(metrics: dict, ticker: str) -> str:
    """Format compute_ttm_metrics output as a detailed Markdown report."""
    n = metrics["quarters_available"]
    ttm = metrics["ttm"]
    quarterly = metrics["quarterly"]
    trends = metrics.get("trends", {})
    errors = metrics["metadata"].get("parse_errors", [])

    lines = [
        f"# TTM Fundamental Analysis: {ticker.upper()}",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Quarters available: {n} (target: 8)",
        "",
    ]

    if errors:
        lines.append(f"**Data warnings:** {'; '.join(errors)}")
        lines.append("")

    if n == 0:
        lines.append("_No quarterly data available._")
        return "\n".join(lines)

    # TTM Summary
    lines += [
        "## Trailing Twelve Months (TTM) Summary",
        "",
        f"| Metric | TTM Value |",
        f"|--------|-----------|",
        f"| Revenue | {_fmt(ttm.get('revenue'))} |",
        f"| Gross Profit | {_fmt(ttm.get('gross_profit'))} |",
        f"| Operating Income | {_fmt(ttm.get('operating_income'))} |",
        f"| EBITDA | {_fmt(ttm.get('ebitda'))} |",
        f"| Net Income | {_fmt(ttm.get('net_income'))} |",
        f"| Free Cash Flow | {_fmt(ttm.get('free_cash_flow'))} |",
        f"| Operating Cash Flow | {_fmt(ttm.get('operating_cash_flow'))} |",
        f"| Total Debt | {_fmt(ttm.get('total_debt'))} |",
        f"| Equity | {_fmt(ttm.get('equity'))} |",
        f"| Gross Margin | {_fmt_pct(ttm.get('gross_margin_pct'))} |",
        f"| Operating Margin | {_fmt_pct(ttm.get('operating_margin_pct'))} |",
        f"| Net Margin | {_fmt_pct(ttm.get('net_margin_pct'))} |",
        f"| Return on Equity | {_fmt_pct(ttm.get('roe_pct'))} |",
        f"| Debt / Equity | {(str(round(ttm['debt_to_equity'], 2)) + 'x') if ttm.get('debt_to_equity') is not None else 'N/A'} |",
        "",
    ]

    # Trend signals
    if trends:
        lines += [
            "## Trend Signals",
            "",
            f"| Signal | Value |",
            f"|--------|-------|",
            f"| Revenue QoQ Growth | {_fmt_pct(trends.get('revenue_qoq_pct'))} |",
            f"| Revenue YoY Growth | {_fmt_pct(trends.get('revenue_yoy_pct'))} |",
            f"| Gross Margin Trend | {trends.get('gross_margin_direction', 'N/A')} |",
            f"| Operating Margin Trend | {trends.get('operating_margin_direction', 'N/A')} |",
            f"| Net Margin Trend | {trends.get('net_margin_direction', 'N/A')} |",
            "",
        ]

    # 8-quarter table
    if quarterly:
        lines += [
            f"## {n}-Quarter Revenue & Margin History (oldest → newest)",
            "",
            "| Quarter | Revenue | Gross Margin | Operating Margin | Net Margin | FCF |",
            "|---------|---------|--------------|------------------|------------|-----|",
        ]
        for q in quarterly:
            lines.append(
                f"| {q['date']} "
                f"| {_fmt(q['revenue'])} "
                f"| {_fmt_pct(q['gross_margin_pct'])} "
                f"| {_fmt_pct(q['operating_margin_pct'])} "
                f"| {_fmt_pct(q['net_margin_pct'])} "
                f"| {_fmt(q['free_cash_flow'])} |"
            )
        lines.append("")

    return "\n".join(lines)
