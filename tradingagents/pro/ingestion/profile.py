"""Volume profile: volume distributed across price bins (review P2.4).

Deterministic math the UI renders and never computes (Constraint 2).
Without tick data, each bar's volume spreads uniformly over the price
bins its high–low range covers — the standard OHLCV approximation. The
value area is the classic 70% construction: start at the point of
control, expand toward whichever adjacent bin holds more volume.
"""

from __future__ import annotations

from collections.abc import Sequence

from tradingagents.contracts import OHLCVBar

DEFAULT_BINS = 24
VALUE_AREA_FRACTION = 0.70


def volume_profile(
    bars: Sequence[OHLCVBar], bins: int = DEFAULT_BINS
) -> dict:
    """Profile over the given bars.

    Returns ``{levels: [{price, volume}], poc, value_area_low,
    value_area_high, total_volume}`` — ``price`` is each bin's midpoint,
    ``poc`` the highest-volume bin's midpoint. Empty/degenerate input
    (no volume, flat range) returns empty levels rather than inventing
    a distribution.
    """
    if not (2 <= bins <= 200):
        raise ValueError("bins must be in [2, 200]")
    if not bars:
        return {"levels": [], "poc": None, "value_area_low": None,
                "value_area_high": None, "total_volume": 0.0}
    low = min(b.low for b in bars)
    high = max(b.high for b in bars)
    span = high - low
    total = sum(b.volume or 0.0 for b in bars)
    if span <= 0 or total <= 0:
        return {"levels": [], "poc": None, "value_area_low": None,
                "value_area_high": None, "total_volume": total}

    step = span / bins
    volumes = [0.0] * bins

    def bin_of(price: float) -> int:
        return min(bins - 1, max(0, int((price - low) / step)))

    for bar in bars:
        volume = bar.volume or 0.0
        if volume <= 0:
            continue
        first = bin_of(bar.low)
        last = bin_of(bar.high)
        share = volume / (last - first + 1)
        for i in range(first, last + 1):
            volumes[i] += share

    poc_index = max(range(bins), key=lambda i: volumes[i])
    # classic value area: greedily absorb the fatter neighbour until 70%
    captured = volumes[poc_index]
    lo_i = hi_i = poc_index
    target = total * VALUE_AREA_FRACTION
    while captured < target and (lo_i > 0 or hi_i < bins - 1):
        below = volumes[lo_i - 1] if lo_i > 0 else -1.0
        above = volumes[hi_i + 1] if hi_i < bins - 1 else -1.0
        if above >= below:
            hi_i += 1
            captured += volumes[hi_i]
        else:
            lo_i -= 1
            captured += volumes[lo_i]

    mid = lambda i: low + (i + 0.5) * step  # noqa: E731
    return {
        "levels": [{"price": mid(i), "volume": volumes[i]} for i in range(bins)],
        "poc": mid(poc_index),
        "value_area_low": low + lo_i * step,
        "value_area_high": low + (hi_i + 1) * step,
        "total_volume": total,
    }
