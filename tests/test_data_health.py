from datetime import date, datetime, timezone

from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    NewsItem,
    PriceBar,
)
from tradingagents.research_platform.data_health import build_cache_data_health


def _provenance(as_of_date: date) -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=as_of_date,
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )


def test_data_health_compares_cache_to_selected_research_date():
    health = build_cache_data_health(
        price_bars=[
            PriceBar(
                symbol="NVDA",
                date=date(2026, 1, 5),
                open=100,
                high=105,
                low=99,
                close=103,
                provenance=_provenance(date(2026, 1, 5)),
            )
        ],
        fundamentals=[
            FundamentalSnapshot(
                symbol="NVDA",
                period_end=date(2026, 1, 4),
                metrics={"market_cap": 1_000_000},
                provenance=_provenance(date(2026, 1, 4)),
            )
        ],
        news=[],
        reference_as_of_date=date(2026, 1, 5),
    )

    statuses = {item["key"]: item["status"] for item in health["items"]}
    assert health["reference_as_of_date"] == "2026-01-05"
    assert statuses == {
        "market_data": "aligned",
        "fundamentals": "lagging",
        "news": "missing",
    }


def test_data_health_without_reference_marks_available_cache():
    health = build_cache_data_health(
        price_bars=[],
        fundamentals=[],
        news=[
            NewsItem(
                symbol="NVDA",
                title="Fixture headline",
                published_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 5),
                provider="fixture-news",
            )
        ],
    )

    assert health["reference_as_of_date"] is None
    assert health["items"][2]["status"] == "available"
