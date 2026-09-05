"""Explainable attention radar for the curated A-share game universe."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .artifact_store import JsonArtifactStore
from .game_approvals import JsonGameApprovalStore
from .game_universe import (
    GameCatalystStatus,
    build_game_research_snapshot,
    list_game_universe_symbols,
)


class GameOpportunityLevel(str, Enum):
    HIGH_ATTENTION = "high_attention"
    WATCH = "watch"
    LOW_SIGNAL = "low_signal"
    INSUFFICIENT_DATA = "insufficient_data"


class GameOpportunityFactorStatus(str, Enum):
    SUPPORTIVE = "supportive"
    MIXED = "mixed"
    WEAK = "weak"
    MISSING = "missing"


class GameOpportunityFactor(BaseModel):
    """One independently explainable radar factor."""

    model_config = ConfigDict(frozen=True)

    factor_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    available: bool
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    status: GameOpportunityFactorStatus
    detail: str = Field(min_length=1)
    observed_as_of: date | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)


class GameOpportunitySnapshot(BaseModel):
    """A screening aid, explicitly separate from a trade recommendation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    company_name: str | None = None
    as_of_date: date
    available: bool
    level: GameOpportunityLevel
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    factors: list[GameOpportunityFactor] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = "Attention score only; it is not a buy, sell, or valuation recommendation."


def build_game_opportunity_snapshot(
    store: JsonArtifactStore,
    symbol: str,
    *,
    as_of_date: date | None = None,
) -> GameOpportunitySnapshot:
    """Combine approvals, product events, fundamentals, and price confirmation."""

    normalized_symbol = symbol.strip().upper()
    reference_date = as_of_date or date.today()
    research = build_game_research_snapshot(normalized_symbol, as_of_date=reference_date)
    if not research.available:
        return GameOpportunitySnapshot(
            symbol=normalized_symbol,
            as_of_date=reference_date,
            available=False,
            level=GameOpportunityLevel.INSUFFICIENT_DATA,
            score=0,
            max_score=12,
            warnings=["No curated game-company profile is available."],
        )

    factors = [
        _approval_factor(store, normalized_symbol, reference_date),
        _catalyst_factor(research, reference_date),
        _financial_factor(store, normalized_symbol, reference_date),
        _market_factor(store, normalized_symbol, reference_date),
    ]
    missing = [factor.label for factor in factors if not factor.available]
    score = sum(factor.score for factor in factors)
    essential_available = all(
        factor.available for factor in factors if factor.factor_id in {"financial", "market"}
    )
    if not essential_available:
        level = GameOpportunityLevel.INSUFFICIENT_DATA
    elif score >= 8:
        level = GameOpportunityLevel.HIGH_ATTENTION
    elif score >= 5:
        level = GameOpportunityLevel.WATCH
    else:
        level = GameOpportunityLevel.LOW_SIGNAL
    warnings = [f"Missing factor data: {', '.join(missing)}."] if missing else []
    return GameOpportunitySnapshot(
        symbol=normalized_symbol,
        company_name=research.company_name,
        as_of_date=reference_date,
        available=True,
        level=level,
        score=score,
        max_score=sum(factor.max_score for factor in factors),
        factors=factors,
        warnings=warnings,
    )


def build_game_opportunity_board(
    store: JsonArtifactStore,
    *,
    as_of_date: date | None = None,
) -> list[GameOpportunitySnapshot]:
    """Return the covered universe ordered by attention score, then symbol."""

    snapshots = [
        build_game_opportunity_snapshot(store, symbol, as_of_date=as_of_date)
        for symbol in list_game_universe_symbols()
    ]
    return sorted(snapshots, key=lambda item: (-item.score, item.symbol))


def _approval_factor(
    store: JsonArtifactStore,
    symbol: str,
    reference_date: date,
) -> GameOpportunityFactor:
    approval_store = JsonGameApprovalStore(store.root)
    if not approval_store.path.exists():
        return _missing_factor("approvals", "Official approvals", 3)
    digest = approval_store.digest(symbol, as_of_date=reference_date)
    recent = [
        item
        for item in digest.approvals
        if item.approval.approval_date >= reference_date - timedelta(days=365)
    ]
    latest = digest.latest_approval_date
    days_since = (reference_date - latest).days if latest is not None else None
    recency_score = 2 if days_since is not None and days_since <= 90 else 0
    if days_since is not None and 90 < days_since <= 180:
        recency_score = 1
    score = min(3, recency_score + (1 if len(recent) >= 2 else 0))
    return GameOpportunityFactor(
        factor_id="approvals",
        label="Official approvals",
        available=True,
        score=score,
        max_score=3,
        status=_factor_status(score, 3),
        detail=(
            f"{len(recent)} exact company-linked approval(s) in the last 365 days; "
            f"latest {latest.isoformat()}."
            if latest is not None
            else "No exact company-linked approval is present in the local cache."
        ),
        observed_as_of=latest,
        metrics={"approvals_365d": len(recent), "days_since_latest": days_since},
        source_urls=sorted({item.approval.source_url for item in recent}),
    )


def _catalyst_factor(research, reference_date: date) -> GameOpportunityFactor:
    upcoming = [item for item in research.catalysts if item.status is GameCatalystStatus.UPCOMING]
    open_ended = [
        item
        for item in research.catalysts
        if item.status in {GameCatalystStatus.ONGOING, GameCatalystStatus.UNDATED}
    ]
    score = min(3, (2 if upcoming else 0) + (1 if open_ended else 0))
    evidence = {item.evidence_id: item for item in research.evidence}
    evidence_ids = {
        evidence_id
        for item in [*upcoming, *open_ended]
        for evidence_id in item.catalyst.evidence_ids
    }
    return GameOpportunityFactor(
        factor_id="catalysts",
        label="Product catalysts",
        available=True,
        score=score,
        max_score=3,
        status=_factor_status(score, 3),
        detail=f"{len(upcoming)} upcoming and {len(open_ended)} ongoing/undated catalyst(s).",
        observed_as_of=reference_date,
        metrics={"upcoming": len(upcoming), "ongoing_or_undated": len(open_ended)},
        source_urls=sorted(
            evidence[item].source_url for item in evidence_ids if item in evidence
        ),
    )


def _financial_factor(
    store: JsonArtifactStore,
    symbol: str,
    reference_date: date,
) -> GameOpportunityFactor:
    reports = [
        item
        for item in store.load_fundamentals(symbol, as_of_date=reference_date)
        if (item.fiscal_period or "").startswith("financial_report_")
    ]
    if not reports:
        return _missing_factor("financial", "Financial delivery", 3)
    latest = max(reports, key=lambda item: (item.period_end, item.provenance.as_of_date))
    profit_yoy = _number(latest.metrics.get("net_profit_yoy_pct"))
    cashflow = _number(latest.metrics.get("reported_operating_cashflow"))
    profit_score = 2 if profit_yoy is not None and profit_yoy > 20 else 0
    if profit_yoy is not None and 0 < profit_yoy <= 20:
        profit_score = 1
    score = min(3, profit_score + (1 if cashflow is not None and cashflow > 0 else 0))
    available = profit_yoy is not None or cashflow is not None
    return GameOpportunityFactor(
        factor_id="financial",
        label="Financial delivery",
        available=available,
        score=score,
        max_score=3,
        status=(_factor_status(score, 3) if available else GameOpportunityFactorStatus.MISSING),
        detail=(
            f"Latest report {latest.period_end.isoformat()}: net profit YoY "
            f"{_format_pct(profit_yoy)}, operating cash flow {_format_amount(cashflow)}."
        ),
        observed_as_of=latest.provenance.as_of_date,
        metrics={"net_profit_yoy_pct": profit_yoy, "operating_cashflow": cashflow},
        source_urls=[latest.provenance.source_url] if latest.provenance.source_url else [],
    )


def _market_factor(
    store: JsonArtifactStore,
    symbol: str,
    reference_date: date,
) -> GameOpportunityFactor:
    bars = sorted(
        store.load_price_bars(
            symbol,
            date.min,
            reference_date,
            as_of_date=reference_date,
        ),
        key=lambda item: item.date,
    )
    if len(bars) < 21:
        return _missing_factor("market", "Market confirmation", 3)
    momentum_20d = bars[-1].close / bars[-21].close - 1 if bars[-21].close else None
    momentum_60d = (
        bars[-1].close / bars[-61].close - 1
        if len(bars) >= 61 and bars[-61].close
        else None
    )
    short_score = 2 if momentum_20d is not None and momentum_20d > 0.05 else 0
    if momentum_20d is not None and 0 < momentum_20d <= 0.05:
        short_score = 1
    score = min(3, short_score + (1 if momentum_60d is not None and momentum_60d > 0 else 0))
    return GameOpportunityFactor(
        factor_id="market",
        label="Market confirmation",
        available=True,
        score=score,
        max_score=3,
        status=_factor_status(score, 3),
        detail=(
            f"20-session return {_format_return(momentum_20d)}; "
            f"60-session return {_format_return(momentum_60d)}."
        ),
        observed_as_of=bars[-1].date,
        metrics={"return_20d": momentum_20d, "return_60d": momentum_60d},
        source_urls=sorted(
            {item.provenance.source_url for item in (bars[-1], bars[-21]) if item.provenance.source_url}
        ),
    )


def _missing_factor(factor_id: str, label: str, max_score: int) -> GameOpportunityFactor:
    return GameOpportunityFactor(
        factor_id=factor_id,
        label=label,
        available=False,
        score=0,
        max_score=max_score,
        status=GameOpportunityFactorStatus.MISSING,
        detail="Required local data is not available.",
    )


def _factor_status(score: int, max_score: int) -> GameOpportunityFactorStatus:
    if score == 0:
        return GameOpportunityFactorStatus.WEAK
    if score == max_score:
        return GameOpportunityFactorStatus.SUPPORTIVE
    return GameOpportunityFactorStatus.MIXED


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _format_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f}%"


def _format_amount(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.0f}"


def _format_return(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"
