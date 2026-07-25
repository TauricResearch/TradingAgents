"""Deterministic market-data verification snapshot.

The market analyst is an LLM that can confabulate exact numbers — citing a
Bollinger band or a "historically validated bounce" that the underlying data
doesn't support (#830). This module computes a ground-truth snapshot (latest
OHLCV row on or before the analysis date, common indicators, recent closes)
the analyst is told to treat as the source of truth for any exact numeric
claim. Deterministic, no LLM involved.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.stockstats_utils import load_ohlcv

# A fixed, common indicator set so the snapshot is the same shape every run.
DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)

# Tencent's public quote vector is a positional protocol, not a semantic JSON
# object.  Keep only field positions verified for this product contract.  In
# particular, do not infer a last price from an undocumented field index.
TENCENT_QUOTE_88_FIELD_INDEX: dict[str, int] = {
    "pe_ttm": 39,
    "pb": 46,
    "limit_up_price": 47,
}


class TencentQuoteContractError(ValueError):
    """The supplied Tencent quote vector cannot prove the documented fields."""


@dataclass(frozen=True)
class TencentQuoteGroundTruth:
    """Values proven by explicit Tencent 88-field positions only."""

    pe_ttm: Decimal | None
    pb: Decimal | None
    limit_up_price: Decimal | None


def parse_tencent_quote_ground_truth(fields: Sequence[object]) -> TencentQuoteGroundTruth:
    """Read the documented Tencent vector fields without inventing a price.

    A short vector is a source-contract failure, rather than evidence that a
    missing field is zero.  Empty values remain ``None`` and are rendered as
    unavailable.  This parser deliberately does *not* expose a current price:
    the verified OHLCV row remains the sole exact price source in this module.
    """
    highest_required = max(TENCENT_QUOTE_88_FIELD_INDEX.values())
    if len(fields) <= highest_required:
        raise TencentQuoteContractError(
            "Tencent quote vector has fewer fields than the verified 88-field contract."
        )
    return TencentQuoteGroundTruth(
        pe_ttm=_optional_decimal(fields[TENCENT_QUOTE_88_FIELD_INDEX["pe_ttm"]]),
        pb=_optional_decimal(fields[TENCENT_QUOTE_88_FIELD_INDEX["pb"]]),
        limit_up_price=_optional_decimal(fields[TENCENT_QUOTE_88_FIELD_INDEX["limit_up_price"]]),
    )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise TencentQuoteContractError(f"Tencent quote field is not numeric: {value!r}") from exc


def _verified_rows(symbol: str, curr_date: str) -> pd.DataFrame:
    """OHLCV on or before curr_date, date-sorted. Raises if nothing usable.

    ``load_ohlcv`` already normalizes the Date column and filters out
    look-ahead rows, but we re-apply the cutoff defensively — this is a
    verification path, so it must not trust its input to be pre-filtered.
    """
    data = load_ohlcv(symbol, curr_date, via_vendor=True)
    if data is None or data.empty:
        raise ValueError(f"No OHLCV data available for {symbol}.")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise ValueError(f"No OHLCV rows on or before {curr_date} for {symbol}.")
    return df


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_verified_market_snapshot(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
    indicators: Iterable[str] | None = None,
    tencent_quote_fields: Sequence[object] | None = None,
) -> str:
    """Render a ground-truth snapshot: latest OHLCV row, indicators, recent closes."""
    # `df` keeps the original capitalized OHLCV columns (Open/High/Low/Close/
    # Volume); stockstats `wrap()` lowercases columns and adds indicator
    # columns, so read raw prices from `df` and indicators from `stock_df`.
    df = _verified_rows(symbol, curr_date)
    stock_df = wrap(df.copy())

    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]  # triggers stockstats calculation
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — one bad indicator shouldn't sink the snapshot
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {latest_date}",
        "- Rows after the requested analysis date are excluded before verification.",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    if tencent_quote_fields is not None:
        quote = parse_tencent_quote_ground_truth(tencent_quote_fields)
        lines += [
            "",
            "### Supplemental Tencent 88-field ground truth",
            "",
            "| Field | Verified field index | Value |",
            "|---|---:|---:|",
        ]
        for name, value in (
            ("PE (TTM)", quote.pe_ttm),
            ("PB", quote.pb),
            ("Limit-up price", quote.limit_up_price),
        ):
            key = {"PE (TTM)": "pe_ttm", "PB": "pb", "Limit-up price": "limit_up_price"}[name]
            lines.append(f"| {name} | {TENCENT_QUOTE_88_FIELD_INDEX[key]} | {_fmt(value)} |")
        lines.append(
            "Tencent fields above supplement valuation and limit data only; they do not establish an "
            "exact current price or replace the verified OHLCV row."
        )

    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]
    return "\n".join(lines)
