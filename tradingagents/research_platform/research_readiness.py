"""Deterministic evidence-readiness checklist for personal research."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import AgentOutputEnvelope, AgentOutputType, TradeSignal
from .backtest_contracts import BacktestResult
from .financial_health import FinancialHealthAssessment, FinancialHealthStatus
from .risk_contracts import RiskReview
from .valuation_context import ValuationContext


class ReadinessStatus(str, Enum):
    READY = "ready"
    ATTENTION = "attention"
    INCOMPLETE = "incomplete"


class ReadinessItemStatus(str, Enum):
    READY = "ready"
    ATTENTION = "attention"
    MISSING = "missing"
    NOT_STARTED = "not_started"


class ResearchReadinessItem(BaseModel):
    """One visible evidence or review requirement."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    status: ReadinessItemStatus
    detail: str
    required: bool = False


class ResearchReadiness(BaseModel):
    """Readiness to review a research package, not a trade recommendation."""

    model_config = ConfigDict(frozen=True)

    status: ReadinessStatus
    required_ready: int = Field(ge=0)
    required_total: int = Field(ge=0)
    items: list[ResearchReadinessItem]


def build_research_readiness(
    *,
    data_health: dict[str, Any],
    valuation_context: ValuationContext,
    financial_health: FinancialHealthAssessment,
    agent_outputs: list[AgentOutputEnvelope],
    signal: TradeSignal | None = None,
    risk_review: RiskReview | None = None,
    backtest_result: BacktestResult | None = None,
) -> ResearchReadiness:
    """Summarize data coverage and review gaps without proposing a trade."""

    health_by_key = {item["key"]: item for item in data_health.get("items", [])}
    items = [
        _data_item("market_data", "Market data", health_by_key.get("market_data")),
        _data_item("fundamentals", "Fundamentals", health_by_key.get("fundamentals")),
        _valuation_item(valuation_context),
        _financial_health_item(financial_health),
        _thesis_item(agent_outputs),
        _event_item(health_by_key.get("news")),
        _decision_item(signal),
        _risk_item(signal, risk_review),
        _backtest_item(signal, backtest_result),
    ]
    required_items = [item for item in items if item.required]
    required_ready = sum(item.status == ReadinessItemStatus.READY for item in required_items)
    required_missing = any(item.status == ReadinessItemStatus.MISSING for item in required_items)
    required_attention = any(item.status == ReadinessItemStatus.ATTENTION for item in required_items)
    status = (
        ReadinessStatus.INCOMPLETE
        if required_missing
        else ReadinessStatus.ATTENTION
        if required_attention
        else ReadinessStatus.READY
    )
    return ResearchReadiness(
        status=status,
        required_ready=required_ready,
        required_total=len(required_items),
        items=items,
    )


def _data_item(
    key: str,
    label: str,
    health: dict[str, Any] | None,
) -> ResearchReadinessItem:
    if health is None or health.get("status") == "missing":
        return ResearchReadinessItem(
            key=key,
            label=label,
            status=ReadinessItemStatus.MISSING,
            detail="No cached evidence is available.",
            required=True,
        )
    if health.get("status") == "lagging":
        return ResearchReadinessItem(
            key=key,
            label=label,
            status=ReadinessItemStatus.ATTENTION,
            detail=str(health.get("detail") or "Cached evidence predates this research run."),
            required=True,
        )
    return ResearchReadinessItem(
        key=key,
        label=label,
        status=ReadinessItemStatus.READY,
        detail=str(health.get("detail") or "Cached evidence is available."),
        required=True,
    )


def _valuation_item(context: ValuationContext) -> ResearchReadinessItem:
    if context.available:
        return ResearchReadinessItem(
            key="valuation_context",
            label="Valuation context",
            status=ReadinessItemStatus.READY,
            detail=f"{context.daily_snapshot_count} cached daily valuation snapshots.",
            required=True,
        )
    return ResearchReadinessItem(
        key="valuation_context",
        label="Valuation context",
        status=ReadinessItemStatus.MISSING,
        detail="Fewer than 20 valid cached daily valuation observations are available.",
        required=True,
    )


def _financial_health_item(assessment: FinancialHealthAssessment) -> ResearchReadinessItem:
    if assessment.status == FinancialHealthStatus.UNKNOWN:
        return ResearchReadinessItem(
            key="financial_health",
            label="Financial health",
            status=ReadinessItemStatus.MISSING,
            detail="No disclosed financial-health metrics are available.",
            required=True,
        )
    return ResearchReadinessItem(
        key="financial_health",
        label="Financial health",
        status=ReadinessItemStatus.READY,
        detail=f"Disclosed checks available; current status: {assessment.status.value}.",
        required=True,
    )


def _thesis_item(outputs: list[AgentOutputEnvelope]) -> ResearchReadinessItem:
    if any(output.output_type == AgentOutputType.INVESTMENT_THESIS for output in outputs):
        return ResearchReadinessItem(
            key="investment_thesis",
            label="Investment thesis",
            status=ReadinessItemStatus.READY,
            detail="At least one structured investment thesis is available.",
            required=True,
        )
    return ResearchReadinessItem(
        key="investment_thesis",
        label="Investment thesis",
        status=ReadinessItemStatus.MISSING,
        detail="No structured investment thesis is available.",
        required=True,
    )


def _event_item(health: dict[str, Any] | None) -> ResearchReadinessItem:
    if health is not None and health.get("status") != "missing":
        return ResearchReadinessItem(
            key="corporate_events",
            label="Corporate events",
            status=ReadinessItemStatus.READY,
            detail=str(health.get("detail") or "Normalized corporate-event evidence is available."),
        )
    return ResearchReadinessItem(
        key="corporate_events",
        label="Corporate events",
        status=ReadinessItemStatus.NOT_STARTED,
        detail="No normalized corporate-event evidence is available for this run.",
    )


def _decision_item(signal: TradeSignal | None) -> ResearchReadinessItem:
    return ResearchReadinessItem(
        key="manual_decision",
        label="Manual decision",
        status=ReadinessItemStatus.READY if signal is not None else ReadinessItemStatus.NOT_STARTED,
        detail="Validated trade signal is available." if signal is not None else "No manual decision recorded.",
    )


def _risk_item(signal: TradeSignal | None, review: RiskReview | None) -> ResearchReadinessItem:
    if signal is None:
        return ResearchReadinessItem(
            key="risk_review",
            label="Risk review",
            status=ReadinessItemStatus.NOT_STARTED,
            detail="Risk review starts after a manual decision is recorded.",
        )
    return ResearchReadinessItem(
        key="risk_review",
        label="Risk review",
        status=ReadinessItemStatus.READY if review is not None else ReadinessItemStatus.ATTENTION,
        detail="Deterministic risk review is available." if review is not None else "Manual decision has no risk review yet.",
    )


def _backtest_item(signal: TradeSignal | None, result: BacktestResult | None) -> ResearchReadinessItem:
    if signal is None:
        return ResearchReadinessItem(
            key="backtest",
            label="Backtest",
            status=ReadinessItemStatus.NOT_STARTED,
            detail="Backtest starts after a manual decision is recorded.",
        )
    return ResearchReadinessItem(
        key="backtest",
        label="Backtest",
        status=ReadinessItemStatus.READY if result is not None else ReadinessItemStatus.ATTENTION,
        detail="Historical signal backtest is available." if result is not None else "Manual decision has no backtest yet.",
    )
