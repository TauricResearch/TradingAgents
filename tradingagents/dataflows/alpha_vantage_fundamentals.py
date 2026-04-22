"""
DEPRECATED — Alpha Vantage removed in the FMP-primary migration.
See alpha_vantage_common.py for context. All stubs.
"""
from __future__ import annotations


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    return ""


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return ""


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return ""


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return ""
