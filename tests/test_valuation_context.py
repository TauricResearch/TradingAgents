from datetime import date, timedelta

import pytest

from tradingagents.research_platform.data_contracts import DataProvenance, FundamentalSnapshot
from tradingagents.research_platform.valuation_context import build_valuation_context


def _snapshot(day: date, pe_ratio_ttm: float, *, price_to_book: float = 3.0) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        symbol="600519",
        period_end=day,
        fiscal_period="daily_snapshot",
        metrics={
            "pe_ratio_ttm": pe_ratio_ttm,
            "price_to_book": price_to_book,
            "price_to_sales_ttm": pe_ratio_ttm / 2,
            "dividend_yield_pct": 2.0,
        },
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 4, 1)),
    )


def test_valuation_context_uses_same_stock_daily_history_only():
    snapshots = [
        _snapshot(date(2026, 1, 1) + timedelta(days=index), float(index + 10))
        for index in range(20)
    ]
    snapshots.append(
        FundamentalSnapshot(
            symbol="600519",
            period_end=date(2025, 12, 31),
            fiscal_period="financial_report_2025-12-31",
            metrics={"pe_ratio_ttm": 999.0},
            provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 4, 1)),
        )
    )

    context = build_valuation_context(snapshots)
    pe = context.metrics[0]

    assert context.available is True
    assert context.daily_snapshot_count == 20
    assert context.as_of_date == "2026-01-20"
    assert pe.available is True
    assert pe.latest == 29.0
    assert pe.low == 10.0
    assert pe.median == 19.5
    assert pe.high == 29.0
    assert pe.percentile == 100.0


def test_valuation_context_marks_short_or_invalid_history_unavailable():
    snapshots = [
        _snapshot(date(2026, 1, 1), float("nan")),
        _snapshot(date(2026, 1, 2), 12.0),
    ]

    context = build_valuation_context(snapshots)
    pe = context.metrics[0]

    assert context.available is False
    assert pe.available is False
    assert pe.latest == 12.0
    assert pe.observations == 1


def test_valuation_context_validates_observation_bounds():
    with pytest.raises(ValueError, match="minimum_observations"):
        build_valuation_context([], minimum_observations=0)
    with pytest.raises(ValueError, match="maximum_observations"):
        build_valuation_context([], minimum_observations=21, maximum_observations=20)
