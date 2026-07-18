"""Consumer-neutral inputs and successful outputs for shared graph execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from threading import Event
from typing import Any, Literal


ANALYST_WIRE_KEYS = ("market", "social", "news", "fundamentals")


@dataclass(frozen=True)
class AnalysisRequest:
    ticker: str
    analysis_date: str
    asset_type: Literal["stock", "crypto"] = "stock"
    selected_analysts: tuple[str, ...] = ANALYST_WIRE_KEYS
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    effective_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ticker.strip():
            raise ValueError("ticker is required")
        try:
            date.fromisoformat(self.analysis_date)
        except ValueError as exc:
            raise ValueError("analysis_date must use YYYY-MM-DD") from exc
        if not self.selected_analysts:
            raise ValueError("at least one analyst is required")
        unknown = set(self.selected_analysts) - set(ANALYST_WIRE_KEYS)
        if unknown:
            raise ValueError(f"unknown analyst keys: {', '.join(sorted(unknown))}")
        if len(set(self.selected_analysts)) != len(self.selected_analysts):
            raise ValueError("selected_analysts must not contain duplicates")
        if self.max_debate_rounds < 1 or self.max_risk_discuss_rounds < 1:
            raise ValueError("debate and risk rounds must be positive")


@dataclass(frozen=True)
class AnalysisResult:
    final_state: Mapping[str, Any]
    final_signal: str

    def __post_init__(self) -> None:
        if not self.final_signal.strip():
            raise ValueError("successful AnalysisResult requires final_signal")


class AnalysisCancelled(Exception):
    def __init__(self, partial_state: Mapping[str, Any] | None = None):
        self.partial_state = partial_state
        super().__init__("analysis cancelled")


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(
        self,
        partial_state: Mapping[str, Any] | None = None,
    ) -> None:
        if self.is_cancelled:
            raise AnalysisCancelled(partial_state)

