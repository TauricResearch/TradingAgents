from datetime import date

from tradingagents.research_platform.agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputType,
)
from tradingagents.research_platform.data_contracts import DataProvenance, FundamentalSnapshot
from tradingagents.research_platform.financial_health import assess_financial_health
from tradingagents.research_platform.research_readiness import (
    ReadinessItemStatus,
    ReadinessStatus,
    build_research_readiness,
)
from tradingagents.research_platform.valuation_context import build_valuation_context


def _data_health(*, market: str = "aligned", fundamentals: str = "aligned"):
    return {
        "items": [
            {"key": "market_data", "status": market, "detail": "Market fixture."},
            {"key": "fundamentals", "status": fundamentals, "detail": "Fundamental fixture."},
            {"key": "news", "status": "missing", "detail": "No events."},
        ]
    }


def _daily_snapshot(index: int) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 1, index + 1),
        fiscal_period="daily_snapshot",
        metrics={
            "pe_ratio_ttm": float(index + 10),
            "price_to_book": 3.0,
            "price_to_sales_ttm": 2.0,
            "dividend_yield_pct": 2.0,
        },
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 2, 1)),
    )


def _financial_snapshot() -> FundamentalSnapshot:
    return FundamentalSnapshot(
        symbol="600519",
        period_end=date(2025, 12, 31),
        fiscal_period="financial_report_2025-12-31",
        metrics={"return_on_equity_pct": 15.0},
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 2, 1)),
    )


def _thesis() -> AgentOutputEnvelope:
    return AgentOutputEnvelope(
        symbol="600519",
        as_of_date=date(2026, 2, 1),
        agent_id="research-manager",
        agent_role="Research Manager",
        output_type=AgentOutputType.INVESTMENT_THESIS,
        headline="Fixture thesis",
        summary="Fixture thesis.",
    )


def test_readiness_is_ready_when_required_evidence_is_present():
    valuation = build_valuation_context([_daily_snapshot(index) for index in range(20)])
    financial = assess_financial_health(_financial_snapshot())

    readiness = build_research_readiness(
        data_health=_data_health(),
        valuation_context=valuation,
        financial_health=financial,
        agent_outputs=[_thesis()],
    )

    assert readiness.status == ReadinessStatus.READY
    assert readiness.required_ready == 5
    assert readiness.required_total == 5
    assert readiness.items[3].status == ReadinessItemStatus.READY
    assert readiness.items[3].detail.endswith("watch.")


def test_readiness_is_incomplete_when_required_evidence_is_missing():
    readiness = build_research_readiness(
        data_health=_data_health(market="missing"),
        valuation_context=build_valuation_context([]),
        financial_health=assess_financial_health(None),
        agent_outputs=[],
    )

    assert readiness.status == ReadinessStatus.INCOMPLETE
    assert readiness.required_ready == 1
    assert readiness.items[0].status == ReadinessItemStatus.MISSING
    assert readiness.items[2].status == ReadinessItemStatus.MISSING
    assert readiness.items[6].status == ReadinessItemStatus.NOT_STARTED


def test_readiness_marks_lagging_required_cache_for_attention():
    valuation = build_valuation_context([_daily_snapshot(index) for index in range(20)])
    readiness = build_research_readiness(
        data_health=_data_health(market="lagging"),
        valuation_context=valuation,
        financial_health=assess_financial_health(_financial_snapshot()),
        agent_outputs=[_thesis()],
    )

    assert readiness.status == ReadinessStatus.ATTENTION
    assert readiness.required_ready == 4
    assert readiness.items[0].status == ReadinessItemStatus.ATTENTION
