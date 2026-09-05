"""Adapters that expose legacy `dataflows` results through platform contracts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timezone
from io import StringIO
from typing import Any

import pandas as pd

from .data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    InstrumentIdentity,
    NewsItem,
    PriceBar,
)

TextFetcher = Callable[..., str]


class DataUnavailableError(RuntimeError):
    """Raised when a legacy dataflow returns an explicit no-data or error sentinel."""


def _route(method: str, *args, **kwargs) -> str:
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(method, *args, **kwargs)


def _fetch_prices(symbol: str, start_date: str, end_date: str) -> str:
    return _route("get_stock_data", symbol, start_date, end_date)


def _fetch_fundamentals(symbol: str, curr_date: str) -> str:
    return _route("get_fundamentals", symbol, curr_date)


def _fetch_news(symbol: str, start_date: str, end_date: str) -> str:
    return _route("get_news", symbol, start_date, end_date)


class LegacyDataflowProvider:
    """Wrap legacy string-returning dataflows as normalized data contracts.

    This adapter keeps the existing vendor routing alive while giving new
    research-platform code typed records with provenance. It is intentionally
    conservative: parsing failures are explicit and no LLM-facing prose is
    passed downstream as if it were clean data.
    """

    name = "legacy-dataflows"

    def __init__(
        self,
        *,
        price_fetcher: TextFetcher | None = None,
        fundamentals_fetcher: TextFetcher | None = None,
        news_fetcher: TextFetcher | None = None,
    ):
        self._price_fetcher = price_fetcher or _fetch_prices
        self._fundamentals_fetcher = fundamentals_fetcher or _fetch_fundamentals
        self._news_fetcher = news_fetcher or _fetch_news

    def get_price_bars(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[PriceBar]:
        availability_date = as_of_date or end
        raw = self._price_fetcher(identity.symbol, start.isoformat(), end.isoformat())
        _raise_if_unavailable(raw, "price data", identity.symbol)

        df = _read_legacy_csv(raw)
        if df.empty:
            return []

        date_col = _find_date_column(df)
        columns = _column_map(df)
        required = ["open", "high", "low", "close"]
        missing = [name for name in required if name not in columns]
        if missing:
            raise ValueError(f"legacy price data missing columns: {missing}")

        bars: list[PriceBar] = []
        for _, row in df.iterrows():
            bar_date = _parse_date(row[date_col])
            if bar_date < start or bar_date > end or bar_date > availability_date:
                continue
            bars.append(
                PriceBar(
                    symbol=identity.symbol,
                    date=bar_date,
                    open=_as_float(row[columns["open"]]),
                    high=_as_float(row[columns["high"]]),
                    low=_as_float(row[columns["low"]]),
                    close=_as_float(row[columns["close"]]),
                    adjusted_close=_optional_float(
                        row[columns["adj_close"]]
                        if "adj_close" in columns
                        else row[columns["close"]]
                    ),
                    volume=_optional_int(row[columns["volume"]])
                    if "volume" in columns
                    else None,
                    currency=identity.currency,
                    provenance=_provenance(
                        self.name,
                        availability_date,
                        source="legacy:dataflows.get_stock_data",
                        vendor_symbol=identity.vendor_symbol or identity.symbol,
                    ),
                )
            )
        return bars

    def get_fundamentals(
        self,
        identity: InstrumentIdentity,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[FundamentalSnapshot]:
        availability_date = as_of_date or date.today()
        raw = self._fundamentals_fetcher(identity.symbol, availability_date.isoformat())
        _raise_if_unavailable(raw, "fundamentals", identity.symbol)

        metrics = _parse_key_value_metrics(raw)
        if not metrics:
            return []

        return [
            FundamentalSnapshot(
                symbol=identity.symbol,
                period_end=availability_date,
                fiscal_period="snapshot",
                currency=identity.currency,
                metrics=metrics,
                provenance=_provenance(
                    self.name,
                    availability_date,
                    source="legacy:dataflows.get_fundamentals",
                    vendor_symbol=identity.vendor_symbol or identity.symbol,
                ),
            )
        ]

    def get_news(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[NewsItem]:
        availability_date = as_of_date or end
        raw = self._news_fetcher(identity.symbol, start.isoformat(), end.isoformat())
        if raw.strip().lower().startswith("no news found"):
            return []
        _raise_if_unavailable(raw, "news", identity.symbol)

        return _parse_news_items(
            raw,
            symbol=identity.symbol,
            provider=self.name,
            as_of_date=availability_date,
        )


def _provenance(
    provider: str,
    as_of_date: date,
    *,
    source: str,
    vendor_symbol: str,
) -> DataProvenance:
    return DataProvenance(
        provider=provider,
        as_of_date=as_of_date,
        retrieved_at=datetime.now(timezone.utc),
        source=source,
        vendor_symbol=vendor_symbol,
    )


def _raise_if_unavailable(raw: str, label: str, symbol: str) -> None:
    normalized = raw.strip().lower()
    if normalized.startswith(("no_data_available", "data_unavailable", "error ")):
        raise DataUnavailableError(f"legacy {label} unavailable for {symbol}: {raw}")
    if normalized.startswith("error retrieving") or normalized.startswith("error fetching"):
        raise DataUnavailableError(f"legacy {label} unavailable for {symbol}: {raw}")


def _read_legacy_csv(raw: str) -> pd.DataFrame:
    lines = [
        line
        for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return pd.DataFrame()
    return pd.read_csv(StringIO("\n".join(lines)))


def _find_date_column(df: pd.DataFrame) -> str:
    for col in df.columns:
        normalized = _normalize_key(str(col))
        if normalized in {"date", "datetime", "unnamed_0"}:
            return str(col)
    first = str(df.columns[0])
    try:
        pd.to_datetime(df[first].iloc[0])
    except Exception as exc:
        raise ValueError("legacy price data missing date column") from exc
    return first


def _column_map(df: pd.DataFrame) -> dict[str, str]:
    return {_normalize_key(str(col)): str(col) for col in df.columns}


def _normalize_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _parse_date(value: Any) -> date:
    parsed = pd.to_datetime(value)
    return parsed.date()


def _as_float(value: Any) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise ValueError("expected numeric value")
    return parsed


def _optional_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned == "":
            return None
        return float(cleaned)
    return float(value)


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return None if parsed is None else int(parsed)


def _parse_key_value_metrics(raw: str) -> dict[str, float | int | str | None]:
    metrics: dict[str, float | int | str | None] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        normalized = _normalize_key(key)
        if normalized:
            metrics[normalized] = _coerce_metric_value(value.strip())
    return metrics


def _coerce_metric_value(value: str) -> float | int | str | None:
    if value == "":
        return None
    cleaned = value.replace(",", "")
    try:
        parsed = float(cleaned)
    except ValueError:
        return value
    return int(parsed) if parsed.is_integer() else parsed


def _parse_news_items(
    raw: str,
    *,
    symbol: str,
    provider: str,
    as_of_date: date,
) -> list[NewsItem]:
    items: list[NewsItem] = []
    current_title: str | None = None
    current_publisher = provider
    body: list[str] = []

    def flush() -> None:
        nonlocal body, current_title, current_publisher
        if current_title is None:
            return
        summary_lines: list[str] = []
        url: str | None = None
        for line in body:
            if line.startswith("Link:"):
                url = line.removeprefix("Link:").strip() or None
            elif line.strip():
                summary_lines.append(line.strip())

        source_id = _stable_source_id(provider, symbol, current_title, url)
        items.append(
            NewsItem(
                symbol=symbol,
                title=current_title,
                published_at=datetime.combine(as_of_date, time.min, tzinfo=timezone.utc),
                as_of_date=as_of_date,
                provider=current_publisher or provider,
                url=url,
                summary="\n".join(summary_lines) or None,
                source_id=source_id,
            )
        )
        body = []
        current_title = None
        current_publisher = provider

    for line in raw.splitlines():
        match = re.match(r"^###\s+(.+?)\s+\(source:\s*(.+?)\)\s*$", line)
        if match:
            flush()
            current_title = match.group(1).strip()
            current_publisher = match.group(2).strip()
            continue
        if current_title is not None:
            body.append(line)
    flush()

    return items


def _stable_source_id(provider: str, symbol: str, title: str, url: str | None) -> str:
    raw = "|".join([provider, symbol, title, url or ""])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"legacy-news:{digest}"
