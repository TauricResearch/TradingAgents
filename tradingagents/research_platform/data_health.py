"""Point-in-time health summaries for mutable cached research data."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from .data_contracts import FundamentalSnapshot, NewsItem, PriceBar


def build_cache_data_health(
    *,
    price_bars: Sequence[PriceBar],
    fundamentals: Sequence[FundamentalSnapshot],
    news: Sequence[NewsItem],
    reference_as_of_date: date | None = None,
) -> dict[str, Any]:
    """Describe cache availability relative to an optional research as-of date."""

    return {
        "reference_as_of_date": (
            reference_as_of_date.isoformat() if reference_as_of_date is not None else None
        ),
        "items": [
            _price_health(price_bars, reference_as_of_date),
            _fundamentals_health(fundamentals, reference_as_of_date),
            _news_health(news, reference_as_of_date),
        ],
    }


def _price_health(records: Sequence[PriceBar], reference_as_of_date: date | None) -> dict[str, Any]:
    if not records:
        return _missing_item("market_data", "Market data")
    latest_available = max(record.provenance.as_of_date for record in records)
    observed_through = max(record.date for record in records)
    return _available_item(
        "market_data",
        "Market data",
        latest_available,
        reference_as_of_date,
        f"{len(records)} cached bars through {observed_through.isoformat()}",
    )


def _fundamentals_health(
    records: Sequence[FundamentalSnapshot],
    reference_as_of_date: date | None,
) -> dict[str, Any]:
    if not records:
        return _missing_item("fundamentals", "Fundamentals")
    latest = max(records, key=lambda record: (record.provenance.as_of_date, record.period_end))
    return _available_item(
        "fundamentals",
        "Fundamentals",
        latest.provenance.as_of_date,
        reference_as_of_date,
        f"{len(records)} cached snapshots; period end {latest.period_end.isoformat()}",
    )


def _news_health(records: Sequence[NewsItem], reference_as_of_date: date | None) -> dict[str, Any]:
    if not records:
        return _missing_item("news", "News")
    latest_available = max(record.as_of_date for record in records)
    latest_published = max(record.published_at.date() for record in records)
    return _available_item(
        "news",
        "News",
        latest_available,
        reference_as_of_date,
        f"{len(records)} cached items; latest published {latest_published.isoformat()}",
    )


def _missing_item(key: str, label: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": "missing",
        "available_as_of_date": None,
        "detail": "No cached data",
    }


def _available_item(
    key: str,
    label: str,
    available_as_of_date: date,
    reference_as_of_date: date | None,
    detail: str,
) -> dict[str, Any]:
    if reference_as_of_date is None:
        status = "available"
    elif available_as_of_date >= reference_as_of_date:
        status = "aligned"
    else:
        status = "lagging"
    return {
        "key": key,
        "label": label,
        "status": status,
        "available_as_of_date": available_as_of_date.isoformat(),
        "detail": detail,
    }
