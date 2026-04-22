"""
DEPRECATED — Alpha Vantage removed in the FMP-primary migration.
See alpha_vantage_common.py for context. Stubs.
"""
from __future__ import annotations


def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    return ""


def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> dict[str, str] | str:
    return ""


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    return ""
