"""RL state space: discretized deterministic features (Constraint 2).

The policy sees exactly what the quant engine computes — regime, trend,
volatility, and stretch buckets — never raw LLM output. Coarse buckets on
purpose: a tabular policy over a small state space stays inspectable and
needs no function approximation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tradingagents.contracts import OHLCVBar
from tradingagents.pro.analytics import (
    classify_regime,
    close_zscore,
    realized_volatility,
    trend_slope,
)

MIN_BARS = 60  # z-score window (50) plus slack

_TREND_EDGES = (-0.08, -0.02, 0.02, 0.08)  # %/bar; mirrors regime thresholds
_VOL_EDGES = (0.10, 0.30)  # annualized; low / normal / high
_Z_EDGES = (-1.5, -0.5, 0.5, 1.5)


def _bucket(value: float, edges: Sequence[float]) -> int:
    """Index of the interval containing value: 0..len(edges)."""
    for i, edge in enumerate(edges):
        if value < edge:
            return i
    return len(edges)


@dataclass(frozen=True)
class RLState:
    regime: str
    trend_bucket: int  # 0..4 (strong down .. strong up)
    vol_bucket: int  # 0..2 (low / normal / high)
    zscore_bucket: int  # 0..4 (deep discount .. deep stretch)

    def key(self) -> str:
        return f"{self.regime}|t{self.trend_bucket}|v{self.vol_bucket}|z{self.zscore_bucket}"


def state_from_bars(bars: Sequence[OHLCVBar]) -> RLState:
    """Deterministic state for the trailing window; needs >= MIN_BARS bars."""
    if len(bars) < MIN_BARS:
        raise ValueError(f"need >= {MIN_BARS} bars for an RL state, got {len(bars)}")
    slope_pct, _ = trend_slope(bars)
    vol = realized_volatility(bars)
    z = close_zscore(bars, window=50)
    return RLState(
        regime=classify_regime(bars).value,
        trend_bucket=_bucket(slope_pct, _TREND_EDGES),
        vol_bucket=_bucket(vol, _VOL_EDGES),
        zscore_bucket=_bucket(z, _Z_EDGES),
    )
