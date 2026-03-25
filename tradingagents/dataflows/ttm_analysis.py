"""Trailing Twelve Months (TTM) trend analysis across up to 8 quarters."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from typing import Optional

import pandas as pd


_INCOME_REVENUE_COLS = [
    "Total Revenue",
    "TotalRevenue",
    "totalRevenue",
    "Revenue",
    "revenue",
]
_INCOME_GROSS_PROFIT_COLS = [
    "Gross Profit",
    "GrossProfit",
    "grossProfit",
]
_INCOME_OPERATING_INCOME_COLS = [
    "Operating Income",
    "OperatingIncome",
    "operatingIncome",
    "Total Operating Income As Reported",
]
_INCOME_EBITDA_COLS = [
    "EBITDA",
    "Ebitda",
    "ebitda",
    "Normalized EBITDA",
]
_INCOME_NET_INCOME_COLS = [
    "Net Income",
    "NetIncome",
    "netIncome",
    "Net Income From Continuing Operation Net Minority Interest",
]

_BALANCE_TOTAL_ASSETS_COLS = [
    "Total Assets",
    "TotalAssets",
    "totalAssets",
]
_BALANCE_TOTAL_DEBT_COLS = [
    "Total Debt",
    "TotalDebt",
    "totalDebt",
    "Long Term Debt",
    "LongTermDebt",
]
_BALANCE_EQUITY_COLS = [
    "Stockholders Equity",
    "StockholdersEquity",
    "Total Stockholder Equity",
    "TotalStockholderEquity",
    "Common Stock Equity",
    "CommonStockEquity",
]

_CASHFLOW_FCF_COLS = [
    "Free Cash Flow",
    "FreeCashFlow",
    "freeCashFlow",
]
_CASHFLOW_OPERATING_COLS = [
    "Operating Cash Flow",
    "OperatingCashflow",
    "operatingCashflow",
    "Total Cash From Operating Activities",
]


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _looks_like_dates(values) -> bool:
    sample = list(values)[:5]
    count = 0
    for value in sample:
        try:
            pd.to_datetime(str(value))
            count += 1
        except Exception:
            pass
    return count >= min(2, len(sample))


def _parse_financial_csv(csv_text: str) -> Optional[pd.DataFrame]:
    if not csv_text or not csv_text.strip():
        return None

    try:
        df = pd.read_csv(StringIO(csv_text), index_col=0)
    except Exception:
        return None

    if df.empty:
        return None

    if _looks_like_dates(df.columns):
        df = df.T

    try:
        df.index = pd.to_datetime(df.index)
    except Exception:
        return None

    df.sort_index(inplace=True)

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _safe_get(
    df: Optional[pd.DataFrame],
    col_candidates: list[str],
    row_idx: int,
) -> Optional[float]:
    if df is None:
        return None
    col = _find_col(df, col_candidates)
    if col is None:
        return None
    try:
        value = df.iloc[row_idx][col]
    except (IndexError, KeyError):
        return None
    return float(value) if pd.notna(value) else None


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


def _margin_trend(margins: list[Optional[float]]) -> str:
    clean = [margin for margin in margins if margin is not None]
    if len(clean) < 3:
        return "insufficient data"
    recent = clean[-3:]
    if recent[-1] > recent[0]:
        return "expanding"
    if recent[-1] < recent[0]:
        return "contracting"
    return "stable"


def _fmt(value: Optional[float], billions: bool = True) -> str:
    if value is None:
        return "N/A"
    if billions:
        return f"${value / 1e9:.2f}B"
    return f"{value:.2f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def compute_ttm_metrics(
    income_csv: str,
    balance_csv: str,
    cashflow_csv: str,
    n_quarters: int = 8,
) -> dict:
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

    if income_df is None:
        return result

    income_df = income_df.tail(n_quarters)
    result["quarters_available"] = len(income_df)

    if balance_df is not None:
        balance_df = balance_df.tail(n_quarters)
    if cashflow_df is not None:
        cashflow_df = cashflow_df.tail(n_quarters)

    ttm_n = min(4, len(income_df))
    ttm_income = income_df.tail(ttm_n)

    def _ttm_sum(df: Optional[pd.DataFrame], cols: list[str]) -> Optional[float]:
        if df is None:
            return None
        col = _find_col(df, cols)
        if col is None:
            return None
        values = pd.to_numeric(df.tail(ttm_n)[col], errors="coerce").dropna()
        return float(values.sum()) if len(values) > 0 else None

    def _latest(df: Optional[pd.DataFrame], cols: list[str]) -> Optional[float]:
        if df is None:
            return None
        col = _find_col(df, cols)
        if col is None:
            return None
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        return float(values.iloc[-1]) if len(values) > 0 else None

    ttm_revenue = _ttm_sum(ttm_income, _INCOME_REVENUE_COLS)
    ttm_gross_profit = _ttm_sum(ttm_income, _INCOME_GROSS_PROFIT_COLS)
    ttm_operating_income = _ttm_sum(ttm_income, _INCOME_OPERATING_INCOME_COLS)
    ttm_ebitda = _ttm_sum(ttm_income, _INCOME_EBITDA_COLS)
    ttm_net_income = _ttm_sum(ttm_income, _INCOME_NET_INCOME_COLS)

    ttm_total_assets = _latest(balance_df, _BALANCE_TOTAL_ASSETS_COLS)
    ttm_total_debt = _latest(balance_df, _BALANCE_TOTAL_DEBT_COLS)
    ttm_equity = _latest(balance_df, _BALANCE_EQUITY_COLS)
    ttm_fcf = _ttm_sum(cashflow_df, _CASHFLOW_FCF_COLS)
    ttm_operating_cf = _ttm_sum(cashflow_df, _CASHFLOW_OPERATING_COLS)

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
        "gross_margin_pct": (
            ttm_gross_profit / ttm_revenue * 100
            if ttm_revenue is not None and ttm_revenue != 0 and ttm_gross_profit is not None
            else None
        ),
        "operating_margin_pct": (
            ttm_operating_income / ttm_revenue * 100
            if ttm_revenue is not None and ttm_revenue != 0 and ttm_operating_income is not None
            else None
        ),
        "net_margin_pct": (
            ttm_net_income / ttm_revenue * 100
            if ttm_revenue is not None and ttm_revenue != 0 and ttm_net_income is not None
            else None
        ),
        "roe_pct": (
            ttm_net_income / ttm_equity * 100
            if ttm_net_income is not None and ttm_equity is not None and ttm_equity != 0
            else None
        ),
        "debt_to_equity": (
            ttm_total_debt / ttm_equity
            if ttm_total_debt is not None and ttm_equity is not None and ttm_equity != 0
            else None
        ),
    }

    quarterly = []
    for index in range(len(income_df)):
        revenue = _safe_get(income_df, _INCOME_REVENUE_COLS, index)
        gross_profit = _safe_get(income_df, _INCOME_GROSS_PROFIT_COLS, index)
        operating_income = _safe_get(income_df, _INCOME_OPERATING_INCOME_COLS, index)
        net_income = _safe_get(income_df, _INCOME_NET_INCOME_COLS, index)
        quarterly.append(
            {
                "date": income_df.index[index].strftime("%Y-%m-%d"),
                "revenue": revenue,
                "gross_margin_pct": (
                    gross_profit / revenue * 100
                    if revenue is not None and revenue != 0 and gross_profit is not None
                    else None
                ),
                "operating_margin_pct": (
                    operating_income / revenue * 100
                    if revenue is not None and revenue != 0 and operating_income is not None
                    else None
                ),
                "net_margin_pct": (
                    net_income / revenue * 100
                    if revenue is not None and revenue != 0 and net_income is not None
                    else None
                ),
                "free_cash_flow": _safe_get(cashflow_df, _CASHFLOW_FCF_COLS, index),
            }
        )

    result["quarterly"] = quarterly

    if len(quarterly) >= 2:
        latest_revenue = quarterly[-1]["revenue"]
        previous_revenue = quarterly[-2]["revenue"]
        year_ago_revenue = quarterly[-5]["revenue"] if len(quarterly) >= 5 else None
        result["trends"] = {
            "revenue_qoq_pct": _pct_change(latest_revenue, previous_revenue),
            "revenue_yoy_pct": _pct_change(latest_revenue, year_ago_revenue),
            "gross_margin_direction": _margin_trend(
                [quarter["gross_margin_pct"] for quarter in quarterly]
            ),
            "operating_margin_direction": _margin_trend(
                [quarter["operating_margin_pct"] for quarter in quarterly]
            ),
            "net_margin_direction": _margin_trend(
                [quarter["net_margin_pct"] for quarter in quarterly]
            ),
        }

    return result


def format_ttm_report(metrics: dict, ticker: str) -> str:
    lines = [
        f"# TTM Fundamental Analysis: {ticker.upper()}",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Quarters available: {metrics['quarters_available']}",
        "",
    ]

    errors = metrics["metadata"].get("parse_errors", [])
    if errors:
        lines.append(f"**Data warnings:** {'; '.join(errors)}")
        lines.append("")

    if metrics["quarters_available"] == 0:
        lines.append("_No quarterly data available._")
        return "\n".join(lines)

    ttm = metrics["ttm"]
    lines.extend(
        [
            "## Trailing Twelve Months (TTM) Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Revenue | {_fmt(ttm.get('revenue'))} |",
            f"| Gross Margin | {_fmt_pct(ttm.get('gross_margin_pct'))} |",
            f"| Operating Margin | {_fmt_pct(ttm.get('operating_margin_pct'))} |",
            f"| Net Margin | {_fmt_pct(ttm.get('net_margin_pct'))} |",
            f"| Return on Equity | {_fmt_pct(ttm.get('roe_pct'))} |",
            f"| Debt / Equity | {ttm.get('debt_to_equity') if ttm.get('debt_to_equity') is not None else 'N/A'} |",
            "",
            "## Trend Signals",
            "",
            "| Signal | Value |",
            "|--------|-------|",
            f"| Revenue QoQ Growth | {_fmt_pct(metrics['trends'].get('revenue_qoq_pct'))} |",
            f"| Revenue YoY Growth | {_fmt_pct(metrics['trends'].get('revenue_yoy_pct'))} |",
            f"| Gross Margin Trend | {metrics['trends'].get('gross_margin_direction', 'N/A')} |",
            f"| Operating Margin Trend | {metrics['trends'].get('operating_margin_direction', 'N/A')} |",
            f"| Net Margin Trend | {metrics['trends'].get('net_margin_direction', 'N/A')} |",
            "",
            "## Quarter History",
            "",
            "| Quarter | Revenue | Gross Margin | Operating Margin | Net Margin | FCF |",
            "|---------|---------|--------------|------------------|------------|-----|",
        ]
    )

    for quarter in metrics["quarterly"]:
        lines.append(
            f"| {quarter['date']} "
            f"| {_fmt(quarter['revenue'])} "
            f"| {_fmt_pct(quarter['gross_margin_pct'])} "
            f"| {_fmt_pct(quarter['operating_margin_pct'])} "
            f"| {_fmt_pct(quarter['net_margin_pct'])} "
            f"| {_fmt(quarter['free_cash_flow'])} |"
        )

    return "\n".join(lines)
