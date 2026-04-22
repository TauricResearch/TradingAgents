"""
DEPRECATED — Alpha Vantage removed in the FMP-primary migration.
See alpha_vantage_common.py for context. Stub.
"""
from __future__ import annotations


def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    interval: str = "daily",
    time_period: int = 14,
    series_type: str = "close",
) -> str:
    return ""
