from datetime import date

from tradingagents.research_platform.data_contracts import DataProvenance, FundamentalSnapshot
from tradingagents.research_platform.financial_health import (
    FinancialHealthStatus,
    assess_financial_health,
)


def test_financial_health_assessment_is_transparent_about_checks():
    snapshot = FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 3, 31),
        metrics={
            "operating_cashflow_to_net_income_ratio": 0.9,
            "debt_to_assets_pct": 20.0,
            "current_ratio": 1.2,
            "return_on_equity_pct": 12.0,
        },
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 4, 1)),
    )

    assessment = assess_financial_health(snapshot)

    assert assessment.status == FinancialHealthStatus.HEALTHY
    assert assessment.score == 4
    assert assessment.checks[0].name == "cash_conversion"


def test_financial_health_marks_missing_metrics_unknown_and_high_leverage_caution():
    snapshot = FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 3, 31),
        metrics={"debt_to_assets_pct": 75.0},
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 4, 1)),
    )

    assessment = assess_financial_health(snapshot)

    assert assessment.status == FinancialHealthStatus.CAUTION
    assert assessment.score == 0
    assert assessment.checks[0].status == FinancialHealthStatus.UNKNOWN
