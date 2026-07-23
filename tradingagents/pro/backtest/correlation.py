"""Correlation-exposure filter for portfolio backtests (roadmap P3 / track T4).

A basket of highly-correlated bets is one bet in disguise — the research's
recurring blow-up pattern is concentrated correlated exposure that all moves
together in a drawdown (docs/research/03_institutional_best_practices.md). The
guard vetoes a fresh entry when the candidate symbol is too correlated with
any symbol already open, using Pearson correlation over TRAILING returns
(past bars only — look-ahead-safe; the engine builds the aligned series from
each symbol's closes at or before the current step).

Honest by construction: with too little aligned history, or a flat (zero-
variance) series, the guard ALLOWS rather than fabricating a correlation.
Off by default on the engine — it is a deliberate risk control a caller opts
into (auto-enabling it on, say, a BTC/ETH/SOL basket would veto everything).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


def pearson(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson correlation of two equal-length series; 0.0 when undefined
    (length mismatch, < 2 points, or either series is constant)."""
    n = len(a)
    if n < 2 or len(b) != n:
        return 0.0
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    return cov / (va ** 0.5 * vb ** 0.5)


@dataclass
class CorrelationGuard:
    """Veto an entry whose |correlation| with any already-open symbol exceeds
    ``max_correlation`` (over the last ``lookback`` returns)."""

    max_correlation: float = 0.85
    lookback: int = 60

    def __post_init__(self) -> None:
        if not 0 < self.max_correlation <= 1:
            raise ValueError("max_correlation must be in (0, 1]")
        if self.lookback < 2:
            raise ValueError("lookback must be >= 2")

    def allow(self, candidate: str, open_symbols: Iterable[str],
              returns_by_symbol: Mapping[str, Sequence[float]]) -> bool:
        cand = returns_by_symbol.get(candidate)
        if cand is None or len(cand) < 2:
            return True  # insufficient aligned history → don't fabricate a veto
        for other in open_symbols:
            series = returns_by_symbol.get(other)
            if series is None or len(series) != len(cand):
                continue
            if abs(pearson(cand, series)) > self.max_correlation:
                return False
        return True


__all__ = ["CorrelationGuard", "pearson"]
