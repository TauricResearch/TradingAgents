"""Auditable conviction arithmetic for the three-way risk debate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskRole = Literal["aggressive", "conservative", "neutral"]


@dataclass(frozen=True)
class ConvictionSignal:
    """A public risk-view summary, never hidden model reasoning.

    ``conviction=None`` is an explicit abstention.  It is intentionally not
    coerced to zero because "insufficient evidence" is a different fact from
    a genuinely neutral view.
    """

    role: RiskRole
    conviction: float | None
    confidence: float
    evidence_summary: str = ""

    def __post_init__(self) -> None:
        if self.conviction is not None and not -1.0 <= self.conviction <= 1.0:
            raise ValueError("conviction must be in [-1, 1] or None for abstain")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True)
class ConvictionAggregate:
    conviction: float | None
    participating_roles: tuple[RiskRole, ...]
    abstained_roles: tuple[RiskRole, ...]
    disagreement: Literal["none", "tight", "wide", "mixed"]


def aggregate_risk_convictions(
    signals: tuple[ConvictionSignal, ...] | list[ConvictionSignal],
) -> ConvictionAggregate:
    """Aggregate only supplied risk views, retaining disagreement explicitly."""
    expected = {"aggressive", "conservative", "neutral"}
    seen: set[str] = set()
    participating: list[ConvictionSignal] = []
    abstained: list[RiskRole] = []
    for signal in signals:
        if signal.role in seen:
            raise ValueError(f"duplicate risk role: {signal.role}")
        seen.add(signal.role)
        if signal.conviction is None:
            abstained.append(signal.role)
        else:
            participating.append(signal)
    if not seen <= expected:
        raise ValueError("unknown risk role")
    if not participating:
        return ConvictionAggregate(None, (), tuple(abstained), "none")

    total = sum(signal.confidence for signal in participating)
    weights = [signal.confidence for signal in participating]
    if total == 0:
        total = float(len(participating))
        weights = [1.0] * len(participating)
    conviction = sum(
        (signal.conviction or 0.0) * weight
        for signal, weight in zip(participating, weights, strict=True)
    ) / total
    values = [signal.conviction or 0.0 for signal in participating]
    has_positive = any(value > 0 for value in values)
    has_negative = any(value < 0 for value in values)
    spread = max(values) - min(values)
    if has_positive and has_negative:
        disagreement: Literal["none", "tight", "wide", "mixed"] = "mixed"
    elif spread >= 0.75:
        disagreement = "wide"
    elif spread > 0:
        disagreement = "tight"
    else:
        disagreement = "none"
    return ConvictionAggregate(
        conviction=round(conviction, 4),
        participating_roles=tuple(signal.role for signal in participating),
        abstained_roles=tuple(abstained),
        disagreement=disagreement,
    )
