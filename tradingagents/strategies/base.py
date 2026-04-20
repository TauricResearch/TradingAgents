"""Base classes for the quantitative strategy signals framework.

Based on:
    Zura Kakushadze and Juan Andrés Serur,
    "151 Trading Strategies",
    Palgrave Macmillan, 2018.
    SSRN: https://ssrn.com/abstract=3247865
    DOI: 10.1007/978-3-030-02792-6
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from typing_extensions import TypedDict


class StrategySignal(TypedDict):
    """A single deterministic signal produced by a strategy."""

    name: str
    ticker: str
    date: str
    signal_strength: float  # -1.0 (strong bearish) to 1.0 (strong bullish)
    direction: Literal["bullish", "bearish", "neutral"]
    detail: str


# Analyst roles that strategies can target
Role = Literal["market", "fundamentals", "news", "social", "researcher", "risk"]


class BaseStrategy(ABC):
    """Abstract base for all strategy signal generators."""

    # Subclasses must set these
    name: str = ""
    roles: list[Role] = []

    @abstractmethod
    def compute(
        self, ticker: str, date: str, context: dict[str, Any] | None = None
    ) -> StrategySignal | None:
        """Compute a signal for *ticker* on *date*.

        Returns ``None`` when insufficient data is available (graceful fallback).
        *context* is an optional dict carrying pre-fetched market data.
        """
