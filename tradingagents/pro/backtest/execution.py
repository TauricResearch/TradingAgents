"""Execution algorithms (track T2): TWAP + VWAP schedule builders.

An execution algo turns one parent order into a per-bar fill schedule — a list
of quantities released one per subsequent bar. TWAP releases equal slices;
VWAP weights slices by a volume profile. The broker fills the scheduled slice
each bar (reusing the iceberg slice machinery + size-weighted averaging), so a
big order is worked over time instead of hitting one bar's open.

Look-ahead safety: the VWAP volume profile must be built from bars STRICTLY
BEFORE the schedule starts (e.g. a bar-of-day typical-volume curve) — never the
release/fill bar's own volume. These builders are pure over whatever profile
the caller supplies; the caller owns that discipline (the strategy computes it
from ``ctx`` history in ``on_bar``).
"""

from __future__ import annotations

from collections.abc import Sequence

ALGOS = ("twap", "vwap")


def twap_schedule(total: float, n_bars: int) -> list[float]:
    """Equal slices of ``total`` over ``n_bars`` bars (time-weighted)."""
    n = max(1, int(n_bars))
    slice_qty = total / n
    return [slice_qty] * n


def vwap_schedule(total: float, volume_profile: Sequence[float]) -> list[float]:
    """Slices of ``total`` proportional to ``volume_profile`` (volume-weighted).
    A flat/empty/zero profile degrades to TWAP over its length."""
    vols = [max(float(v), 0.0) for v in volume_profile]
    denom = sum(vols)
    if denom <= 0:
        return twap_schedule(total, len(vols) or 1)
    return [total * v / denom for v in vols]


def build_schedule(
    algo: str, total: float, n_bars: int,
    volume_profile: Sequence[float] | None = None,
) -> list[float]:
    """Per-bar release schedule for ``algo`` (``twap`` | ``vwap``). VWAP uses
    ``volume_profile`` (falls back to a flat profile of length ``n_bars``)."""
    if algo == "twap":
        return twap_schedule(total, n_bars)
    if algo == "vwap":
        profile = volume_profile if volume_profile else [1.0] * max(1, int(n_bars))
        return vwap_schedule(total, profile)
    raise ValueError(f"unknown execution algo {algo!r} ({' | '.join(ALGOS)})")


def schedule_for(
    algo: str | None, algo_bars: int, volume_profile: Sequence[float] | None,
    quantity: float,
) -> tuple[float, ...] | None:
    """Convenience for the engine: the per-bar schedule tuple for an intent's
    algo fields, or None when no algo is requested."""
    if not algo:
        return None
    return tuple(build_schedule(algo, quantity, algo_bars, volume_profile))


__all__ = [
    "ALGOS",
    "build_schedule",
    "schedule_for",
    "twap_schedule",
    "vwap_schedule",
]
