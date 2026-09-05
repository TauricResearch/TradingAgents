from datetime import date, datetime, timezone

from tradingagents.research_platform.data_contracts import DataProvenance
from tradingagents.research_platform.financial_quality import (
    build_financial_quality_history,
    build_financial_quality_snapshot,
)


def _provenance() -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=date(2026, 4, 1),
        retrieved_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        source="fixture.financials",
        vendor_symbol="600519.SH",
    )


def test_financial_quality_uses_latest_report_disclosed_by_as_of_date():
    previous = {"ann_date": "20260301", "end_date": "20251231"}
    future = {"ann_date": "20260425", "end_date": "20260331"}

    snapshot = build_financial_quality_snapshot(
        symbol="600519",
        as_of_date=date(2026, 4, 1),
        currency="CNY",
        income_rows=[
            previous | {"total_revenue": 1000.0, "n_income": 100.0},
            future | {"total_revenue": 1200.0, "n_income": 120.0},
        ],
        balance_rows=[
            previous | {"total_assets": 500.0, "total_liab": 100.0},
            future | {"total_assets": 600.0, "total_liab": 150.0},
        ],
        cashflow_rows=[
            previous | {"n_cashflow_act": 120.0},
            future | {"n_cashflow_act": 140.0},
        ],
        indicator_rows=[
            previous | {"roe": 15.0, "debt_to_assets": 20.0, "current_ratio": 2.0},
            future | {"roe": 16.0, "debt_to_assets": 25.0, "current_ratio": 1.5},
        ],
        provenance=_provenance(),
    )

    assert snapshot is not None
    assert snapshot.period_end == date(2025, 12, 31)
    assert snapshot.metrics["reported_total_revenue"] == 1000.0
    assert snapshot.metrics["return_on_equity_pct"] == 15.0
    assert snapshot.metrics["operating_cashflow_to_net_income_ratio"] == 1.2
    assert snapshot.metrics["calculated_liabilities_to_assets_ratio"] == 0.2
    assert snapshot.metrics["income_announcement_date"] == "2026-03-01"


def test_financial_quality_history_keeps_only_disclosed_periods_and_limits_length():
    records = [
        {"ann_date": "20250130", "end_date": "20241231"},
        {"ann_date": "20250430", "end_date": "20250331"},
        {"ann_date": "20250730", "end_date": "20250630"},
    ]
    history = build_financial_quality_history(
        symbol="600519",
        as_of_date=date(2025, 6, 30),
        currency="CNY",
        income_rows=[
            row | {"total_revenue": 1000.0 + index, "n_income": 100.0 + index}
            for index, row in enumerate(records)
        ],
        balance_rows=[
            row | {"total_assets": 500.0 + index, "total_liab": 100.0 + index}
            for index, row in enumerate(records)
        ],
        cashflow_rows=[
            row | {"n_cashflow_act": 120.0 + index} for index, row in enumerate(records)
        ],
        indicator_rows=[row | {"roe": 15.0 + index} for index, row in enumerate(records)],
        provenance=_provenance(),
        max_periods=2,
    )

    assert [snapshot.period_end for snapshot in history] == [date(2024, 12, 31), date(2025, 3, 31)]
    assert [snapshot.metrics["return_on_equity_pct"] for snapshot in history] == [15.0, 16.0]
