from __future__ import annotations

from typing import Iterable

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.stockstats_utils import load_ohlcv


DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema",
    "close_50_sma",
    "close_200_sma",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
    "macd",
    "macds",
    "macdh",
    "atr",
)


def _normalize_ohlcv(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    if data is None or data.empty:
        raise ValueError("No OHLCV data was returned for verification.")

    df = data.copy()

    if "Date" not in df.columns:
        df = df.reset_index()
        if "Date" not in df.columns:
            df = df.rename(columns={df.columns[0]: "Date"})

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    cutoff = pd.to_datetime(curr_date)
    df = df[df["Date"] <= cutoff].sort_values("Date")

    if df.empty:
        raise ValueError(f"No OHLCV rows are available on or before {curr_date}.")

    return df


def _row_value(row: pd.Series, name: str):
    candidates = (name, name.lower(), name.upper(), name.title())

    for candidate in candidates:
        if candidate in row.index and pd.notna(row[candidate]):
            return row[candidate]

    return None


def _format_value(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        return f"{value:.2f}"

    return str(value)


def _latest_date(row: pd.Series) -> str:
    value = _row_value(row, "Date")

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")

    return str(value)


def build_verified_market_snapshot(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
    indicators: Iterable[str] | None = None,
) -> str:
    df = _normalize_ohlcv(load_ohlcv(symbol, curr_date), curr_date)

    stock_df = wrap(df.copy())
    stock_df["Date"] = pd.to_datetime(stock_df["Date"], errors="coerce")

    selected_indicators = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)

    indicator_values: dict[str, str] = {}

    for indicator in selected_indicators:
        try:
            stock_df[indicator]
            value = stock_df.iloc[-1][indicator]
            indicator_values[indicator] = _format_value(value)
        except Exception as exc:
            indicator_values[indicator] = f"N/A ({type(exc).__name__})"

    latest = stock_df.iloc[-1]
    latest_date = _latest_date(latest)

    price_rows = [
        ("Date", latest_date),
        ("Open", _format_value(_row_value(latest, "Open"))),
        ("High", _format_value(_row_value(latest, "High"))),
        ("Low", _format_value(_row_value(latest, "Low"))),
        ("Close", _format_value(_row_value(latest, "Close"))),
        ("Volume", _format_value(_row_value(latest, "Volume"))),
    ]

    recent_window = max(1, min(int(look_back_days), 30))
    recent = stock_df.tail(recent_window)

    lines: list[str] = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {latest_date}",
        "- Data rows after the requested analysis date are excluded before verification.",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]

    for field, value in price_rows:
        lines.append(f"| {field} | {value} |")

    lines.extend(
        [
            "",
            "### Verified technical indicators on latest trading row",
            "",
            "| Indicator | Value |",
            "|---|---:|",
        ]
    )

    for indicator, value in indicator_values.items():
        lines.append(f"| {indicator} | {value} |")

    lines.extend(
        [
            "",
            "### Recent verified closes",
            "",
            "| Date | Close |",
            "|---|---:|",
        ]
    )

    for _, row in recent.iterrows():
        row_date = _latest_date(row)
        close = _format_value(_row_value(row, "Close"))
        lines.append(f"| {row_date} | {close} |")

    lines.extend(
        [
            "",
            "Verification instruction: use this snapshot as the source of truth for exact OHLCV, price-level, and indicator-value claims. If another tool output conflicts with this snapshot, explicitly flag the discrepancy instead of inventing a reconciled number. Do not claim historical validation, support/resistance bounces, or exact percentage moves unless they are directly supported by tool output with concrete dates and prices.",
        ]
    )

    return "\n".join(lines)