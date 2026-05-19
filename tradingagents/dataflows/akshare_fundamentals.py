"""Akshare-based fundamental data fetchers for China A-share market.

Provides company fundamentals, balance sheet, cash flow, and income
statement data with the same function signatures as the yfinance
implementations.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

import pandas as pd

from .a_share_common import normalize_ashare_symbol, to_plain_code, ensure_ipv4
from .akshare_stock import _ak_retry


# ── Company profile & key metrics ───────────────────────────────────────

def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date (not used for akshare)"] = None,
) -> str:
    """Retrieve A-share company fundamentals overview via akshare.

    Returns key metrics similar to yfinance's ``info`` dict: sector,
    industry, market cap, PE ratio, EPS, etc.
    """
    import akshare as ak

    normalized = normalize_ashare_symbol(ticker)
    code = to_plain_code(ticker)

    try:
        ensure_ipv4()

        # Company profile (巨潮 info优先, 东财 fallback)
        try:
            profile = _ak_retry(ak.stock_profile_cninfo, symbol=code)
        except Exception:
            profile = _ak_retry(ak.stock_individual_info_em, symbol=code)

        # Key financial indicators (东财)
        indicator_df = _ak_retry(
            ak.stock_financial_abstract_ths,
            symbol=code,
            indicator="按报告期",
        )
    except Exception as exc:
        return (
            f"# Company Fundamentals for {normalized}\n"
            f"# Error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    lines = [f"# Company Fundamentals for {normalized}"]
    lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Extract profile info
    if profile is not None and not profile.empty:
        profile_dict = {}
        for _, row in profile.iterrows():
            if len(row) >= 2:
                key = str(row.iloc[0]).strip()
                val = str(row.iloc[1]).strip()
                if key and val and val != "nan":
                    profile_dict[key] = val

        interesting_keys = [
            "公司名称", "公司简称", "英文名称", "所属行业", "行业",
            "上市日期", "总股本", "流通股", "注册资本",
            "Name", "Sector", "Industry", "Market Cap",
        ]
        for key in interesting_keys:
            if key in profile_dict:
                lines.append(f"{key}: {profile_dict[key]}")

        # If we got a dict-style profile, show all non-empty values
        if not any(k in profile_dict for k in interesting_keys):
            for k, v in list(profile_dict.items())[:15]:
                lines.append(f"{k}: {v}")

    lines.append("")

    # Extract key financial indicators
    if indicator_df is not None and not indicator_df.empty:
        lines.append("## Key Financial Indicators (Latest)")
        # Take the most recent row
        latest = indicator_df.head(1)
        for col in latest.columns:
            val = latest[col].iloc[0]
            if pd.notna(val) and str(val).strip() and val is not False and str(val) != "False":
                lines.append(f"{col}: {val}")

    return "\n".join(lines)


# ── Balance sheet ───────────────────────────────────────────────────────

def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve A-share balance sheet data via akshare."""
    import akshare as ak

    normalized = normalize_ashare_symbol(ticker)
    code = to_plain_code(ticker)

    try:
        df = _ak_retry(
            ak.stock_balance_sheet_by_report_em,
            symbol=code,
        )
    except Exception as exc:
        return (
            f"# Balance Sheet for {normalized}\n"
            f"# Error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    if df is None or df.empty:
        return f"No balance sheet data found for {normalized}"

    # Filter by curr_date to prevent look-ahead
    if curr_date and "REPORT_DATE_NAME" in df.columns:
        df["REPORT_DATE_NAME"] = pd.to_datetime(df["REPORT_DATE_NAME"], errors="coerce")
        cutoff = pd.Timestamp(curr_date)
        df = df[df["REPORT_DATE_NAME"] <= cutoff]
        df = df.sort_values("REPORT_DATE_NAME", ascending=False)

    # Select key columns
    preferred = [
        "REPORT_DATE_NAME", "TOTAL_ASSETS", "TOTAL_LIABILITIES",
        "TOTAL_PARENT_EQUITY", "MONETARYFUNDS", "INVENTORY",
        "ACCOUNTS_RECE", "GOODWILL",
    ]
    available = [c for c in preferred if c in df.columns]
    if available:
        df = df[available]

    # Limit rows for prompt size
    df = df.head(8)

    header = (
        f"# Balance Sheet for {normalized} ({freq})\n"
        f"# Data source: akshare (East Money)\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)


# ── Cash flow ───────────────────────────────────────────────────────────

def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve A-share cash flow statement via akshare."""
    import akshare as ak

    normalized = normalize_ashare_symbol(ticker)
    code = to_plain_code(ticker)

    try:
        df = _ak_retry(
            ak.stock_cash_flow_sheet_by_report_em,
            symbol=code,
        )
    except Exception as exc:
        return (
            f"# Cash Flow Statement for {normalized}\n"
            f"# Error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    if df is None or df.empty:
        return f"No cash flow data found for {normalized}"

    if curr_date and "REPORT_DATE_NAME" in df.columns:
        df["REPORT_DATE_NAME"] = pd.to_datetime(df["REPORT_DATE_NAME"], errors="coerce")
        cutoff = pd.Timestamp(curr_date)
        df = df[df["REPORT_DATE_NAME"] <= cutoff]
        df = df.sort_values("REPORT_DATE_NAME", ascending=False)

    preferred = [
        "REPORT_DATE_NAME", "NETCASH_OPERATE", "NETCASH_INVEST",
        "NETCASH_FINANCE", "CCE_ADD", "PAY_STAFF_CASH",
    ]
    available = [c for c in preferred if c in df.columns]
    if available:
        df = df[available]

    df = df.head(8)

    header = (
        f"# Cash Flow Statement for {normalized} ({freq})\n"
        f"# Data source: akshare (East Money)\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)


# ── Income statement ────────────────────────────────────────────────────

def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve A-share income statement via akshare."""
    import akshare as ak

    normalized = normalize_ashare_symbol(ticker)
    code = to_plain_code(ticker)

    try:
        df = _ak_retry(
            ak.stock_profit_sheet_by_report_em,
            symbol=code,
        )
    except Exception as exc:
        return (
            f"# Income Statement for {normalized}\n"
            f"# Error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    if df is None or df.empty:
        return f"No income statement data found for {normalized}"

    if curr_date and "REPORT_DATE_NAME" in df.columns:
        df["REPORT_DATE_NAME"] = pd.to_datetime(df["REPORT_DATE_NAME"], errors="coerce")
        cutoff = pd.Timestamp(curr_date)
        df = df[df["REPORT_DATE_NAME"] <= cutoff]
        df = df.sort_values("REPORT_DATE_NAME", ascending=False)

    preferred = [
        "REPORT_DATE_NAME", "TOTAL_OPERATE_INCOME", "OPERATE_PROFIT",
        "TOTAL_PROFIT", "NETPROFIT", "PARENT_NETPROFIT",
        "DEDUCT_PARENT_NETPROFIT", "BASIC_EPS",
    ]
    available = [c for c in preferred if c in df.columns]
    if available:
        df = df[available]

    df = df.head(8)

    header = (
        f"# Income Statement for {normalized} ({freq})\n"
        f"# Data source: akshare (East Money)\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)


# ── Insider transactions (shareholder changes) ─────────────────────────

def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Retrieve major shareholder changes for an A-share stock via akshare.

    Approximates the yfinance ``insider_transactions`` concept using
    East Money's shareholder data.
    """
    import akshare as ak

    normalized = normalize_ashare_symbol(ticker)
    code = to_plain_code(ticker)

    try:
        df = _ak_retry(
            ak.stock_main_stock_holder,
            stock=code,
        )
    except Exception as exc:
        return (
            f"# Major Shareholders for {normalized}\n"
            f"# Error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    if df is None or df.empty:
        return f"No shareholder data found for {normalized}"

    df = df.head(20)

    header = (
        f"# Major Shareholders for {normalized}\n"
        f"# Data source: akshare (East Money)\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)
