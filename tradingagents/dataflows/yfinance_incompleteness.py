"""Yfinance result-completeness checks and data-result summaries.

Extracted from ``interface.py``. When yfinance is the primary vendor for an
A-share ticker, its OHLCV / fundamentals / statement data is often incomplete
(poor A-share coverage). These functions detect that incompleteness so the
router can supplement with a China-only vendor, and produce short data-result
summaries for progress events.

The module depends on pandas, config, and ticker classification. It reaches
``_is_missing_required_data_result`` (still in ``interface.py``) via a
function-local import to avoid a circular dependency.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from .config import get_config
from .ticker_utils import is_a_share_ticker


def _summarize_data_result(method: str, result: Any) -> str:
    if method in {"get_stock_data", "get_balance_sheet", "get_cashflow", "get_income_statement"}:
        df = _parse_csv_from_report(result)
        if df is not None:
            return f"返回 {len(df)} 行数据"
    if method == "get_fundamentals":
        return "返回基本面数据"
    return "调用完成"


def _should_supplement_yfinance_result(
    method: str,
    vendor: str,
    args: tuple[Any, ...],
    result: Any,
) -> bool:
    if vendor != "yfinance" or not args or not is_a_share_ticker(str(args[0])):
        return False
    if method not in {
        "get_stock_data",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    }:
        return False
    return _summarize_yfinance_incompleteness(method, args, result) != ""


def _summarize_yfinance_incompleteness(
    method: str,
    args: tuple[Any, ...],
    result: Any,
) -> str:
    if method == "get_stock_data":
        return _summarize_yfinance_stock_incompleteness(args, result)
    if method == "get_fundamentals":
        return _summarize_yfinance_fundamentals_incompleteness(result)
    if method in {"get_balance_sheet", "get_cashflow", "get_income_statement"}:
        return _summarize_yfinance_statement_incompleteness(result)
    return ""


def _summarize_yfinance_stock_incompleteness(args: tuple[Any, ...], result: Any) -> str:
    df = _parse_csv_from_report(result)
    if df is None or df.empty:
        return "Yahoo Finance returned no parseable OHLCV rows for this A-share."

    missing_cols = [
        col for col in ("Open", "High", "Low", "Close", "Volume") if col not in df.columns
    ]
    if missing_cols:
        return f"Yahoo Finance OHLCV data is missing required columns: {', '.join(missing_cols)}."

    core = df[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    null_ratio = float(core.isna().mean().max())
    if null_ratio > 0.4:
        return f"Yahoo Finance OHLCV data has too many missing core values ({null_ratio:.0%})."

    cfg = get_config()
    min_rows = int(cfg.get("a_share_yfinance_min_rows", 3))
    if len(df) < min_rows:
        return f"Yahoo Finance returned only {len(df)} OHLCV row(s), below the minimum {min_rows}."

    if len(args) >= 3:
        expected = _expected_weekday_count(str(args[1]), str(args[2]))
        if expected > 0:
            ratio = len(df) / expected
            min_ratio = float(cfg.get("a_share_yfinance_min_coverage_ratio", 0.6))
            if ratio < min_ratio:
                return (
                    f"Yahoo Finance OHLCV coverage is {ratio:.0%} "
                    f"({len(df)}/{expected} weekdays), below the configured {min_ratio:.0%} threshold."
                )

    return ""


def _summarize_yfinance_fundamentals_incompleteness(result: Any) -> str:
    text = str(result or "")
    if _check_missing_required_data(text):
        return "Yahoo Finance returned no fundamentals data for this A-share."
    field_count = sum(1 for line in text.splitlines() if ":" in line and not line.startswith("#"))
    min_fields = int(get_config().get("a_share_yfinance_min_fundamental_fields", 5))
    if field_count < min_fields:
        return (
            f"Yahoo Finance fundamentals contain only {field_count} populated field(s), "
            f"below the minimum {min_fields}."
        )
    return ""


def _summarize_yfinance_statement_incompleteness(result: Any) -> str:
    if _check_missing_required_data(result):
        return "Yahoo Finance returned no usable financial statement data for this A-share."
    df = _parse_csv_from_report(result)
    if df is None or df.empty:
        return "Yahoo Finance statement data is not parseable as a populated table."
    if len(df.columns) <= 1:
        return "Yahoo Finance statement data has no dated statement columns."
    return ""


def _parse_csv_from_report(result: Any) -> pd.DataFrame | None:
    text = str(result or "")
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if not lines:
        return None
    try:
        return pd.read_csv(StringIO("\n".join(lines)))
    except Exception:
        return None


def _expected_weekday_count(start_date: str, end_date: str) -> int:
    try:
        dates = pd.date_range(start=start_date, end=end_date, freq="B")
    except Exception:
        return 0
    return len(dates)


def _check_missing_required_data(result: Any) -> bool:
    """Forward to the routing core's missing-data detector.

    Function-local import avoids a circular dependency: ``interface.py``
    re-exports this module's symbols, so importing it at module level would
    cycle.
    """
    from .interface import _is_missing_required_data_result

    return _is_missing_required_data_result(result)
