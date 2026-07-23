"""Capital allocation for portfolio backtests (roadmap P3 / track T4).

The shared broker already enforces a portfolio-WIDE gross-exposure cap and a
position count cap. An allocator adds a PER-SYMBOL budget on top: it stops one
symbol from consuming the whole book just because it fired first, which is the
allocation discipline the trader research repeatedly ties to survival
(docs/research/03_institutional_best_practices.md — risk is budgeted per bet,
not first-come-first-served).

The engine consults ``max_notional(symbol, equity, existing_symbol_notional)``
when sizing an entry and trims the order so the symbol's gross notional stays
within its budget (0 → the symbol is full, the entry is vetoed). Allocators
are pure and stateless; ``None`` on the engine keeps sizing unbudgeted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class CapitalAllocator(Protocol):
    def max_notional(self, symbol: str, equity: float,
                     existing_symbol_notional: float) -> float:
        """The additional gross notional ``symbol`` may take on now, given its
        already-open notional. Return 0.0 to veto a fresh add."""
        ...


@dataclass
class EqualWeightAllocator:
    """Cap each symbol at an equal share of equity (``equity / n_symbols``),
    or at ``max_weight_pct`` of equity when that is tighter. Equal-weight is
    the honest default when no view on relative sizing is supplied."""

    n_symbols: int
    max_weight_pct: float | None = None

    def __post_init__(self) -> None:
        if self.n_symbols < 1:
            raise ValueError("n_symbols must be >= 1")
        if self.max_weight_pct is not None and not 0 < self.max_weight_pct <= 100:
            raise ValueError("max_weight_pct must be in (0, 100]")

    def max_notional(self, symbol: str, equity: float,
                     existing_symbol_notional: float) -> float:
        weight = 1.0 / self.n_symbols
        if self.max_weight_pct is not None:
            weight = min(weight, self.max_weight_pct / 100.0)
        return max(0.0, weight * equity - existing_symbol_notional)


@dataclass
class WeightedAllocator:
    """Per-symbol target weights (need not sum to 1; each is an independent
    cap as a fraction of equity). A symbol absent from ``weights`` is uncapped
    by the allocator (the broker's portfolio gross cap still binds)."""

    weights: dict[str, float]

    def __post_init__(self) -> None:
        for symbol, w in self.weights.items():
            if not 0 < w <= 1:
                raise ValueError(f"weight for {symbol} must be in (0, 1]")

    def max_notional(self, symbol: str, equity: float,
                     existing_symbol_notional: float) -> float:
        weight = self.weights.get(symbol)
        if weight is None:
            return float("inf")  # uncapped here; broker gross cap still applies
        return max(0.0, weight * equity - existing_symbol_notional)


__all__ = ["CapitalAllocator", "EqualWeightAllocator", "WeightedAllocator"]
