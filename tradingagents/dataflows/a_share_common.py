from __future__ import annotations

from functools import lru_cache
import re
from types import SimpleNamespace

import pandas as pd

try:
    import akshare as ak
except ImportError:  # pragma: no cover - covered indirectly via patched tests
    ak = SimpleNamespace()


SH_PREFIXES = ("600", "601", "603", "605", "688", "689")
SZ_PREFIXES = ("000", "001", "002", "003", "300", "301")
BJ_PREFIXES = (
    "430", "431", "832", "833", "834", "835", "836", "837", "838", "839",
    "870", "871", "872", "873", "874", "875", "876", "877", "878", "879", "920",
)


def _infer_exchange(code: str) -> str:
    if code.startswith(SH_PREFIXES):
        return "SH"
    if code.startswith(SZ_PREFIXES):
        return "SZ"
    if code.startswith(BJ_PREFIXES):
        return "BJ"
    raise ValueError(
        f"Unsupported A-share symbol '{code}'. Expected a 6-digit Shanghai, Shenzhen, or Beijing code."
    )


def normalize_ashare_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("Ticker symbol cannot be empty.")

    exchange_prefix_match = re.fullmatch(r"(SH|SZ|BJ)(\d{6})", normalized)
    if exchange_prefix_match:
        exchange, code = exchange_prefix_match.groups()
        return f"{code}.{exchange}"

    exchange_suffix_match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", normalized)
    if exchange_suffix_match:
        code, exchange = exchange_suffix_match.groups()
        return f"{code}.{exchange}"

    digits_match = re.fullmatch(r"\d{6}", normalized)
    if digits_match:
        code = digits_match.group(0)
        return f"{code}.{_infer_exchange(code)}"

    raise ValueError(
        "Unsupported A-share symbol format. Use a 6-digit code such as 600519 or 000001."
    )


def to_plain_symbol(symbol: str) -> str:
    return normalize_ashare_symbol(symbol).split(".", 1)[0]


def to_exchange_prefixed_symbol(symbol: str) -> str:
    code, exchange = normalize_ashare_symbol(symbol).split(".", 1)
    return f"{exchange}{code}"


def to_yfinance_symbol(symbol: str) -> str:
    code, exchange = normalize_ashare_symbol(symbol).split(".", 1)
    if exchange == "SH":
        return f"{code}.SS"
    return f"{code}.{exchange}"


def get_ashare_exchange(symbol: str) -> str:
    """Return the exchange suffix (``SH``/``SZ``/``BJ``) for an A-share ticker."""
    return normalize_ashare_symbol(symbol).split(".", 1)[1]


def format_date_for_api(date_str: str) -> str:
    return pd.Timestamp(date_str).strftime("%Y%m%d")


@lru_cache(maxsize=1)
def get_trade_calendar() -> tuple[pd.Timestamp, ...]:
    fetcher = getattr(ak, "tool_trade_date_hist_sina", None)
    if fetcher is None:
        return tuple()
    trade_dates = fetcher()["trade_date"]
    return tuple(pd.to_datetime(trade_dates, errors="coerce").dropna().sort_values())


def is_trade_date(date_str: str) -> bool:
    target = pd.Timestamp(date_str).normalize()
    return target in set(get_trade_calendar())


def get_previous_trade_date(date_str: str) -> str:
    calendar = get_trade_calendar()
    if not calendar:
        return pd.Timestamp(date_str).strftime("%Y-%m-%d")

    target = pd.Timestamp(date_str).normalize()
    eligible = [trade_date for trade_date in calendar if trade_date <= target]
    if not eligible:
        raise ValueError(f"No A-share trading date found on or before {date_str}.")
    return eligible[-1].strftime("%Y-%m-%d")


def get_date_range(start_date: str, end_date: str) -> list[str]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return [value.strftime("%Y-%m-%d") for value in pd.date_range(start=start, end=end, freq="D")]


def parse_date_column(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")
