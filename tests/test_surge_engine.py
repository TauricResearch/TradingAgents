"""Synthetic fixtures verify mechanics, not profitability or official Surge rules."""

from dataclasses import asdict

import pandas as pd
import pytest

from tradingagents.surge.engine import DetectorConfig, detect_zones, zone_boundaries, zone_scorecard


def pattern_bars(pattern="RBR"):
    rows = [[100, 100.5, 99.5, 100, 100]] * 20
    rows += [[98, 100.2, 97.8, 100, 150] if pattern[0] == "R" else [102, 102.2, 99.8, 100, 150]]
    rows += [[100, 100.3, 99.7, 100.1, 70]]
    rows += [
        [100.1, 102.5, 100, 102.3, 200] if pattern[-1] == "R" else [100.1, 100.2, 97.5, 97.7, 200]
    ]
    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close", "volume"],
        index=pd.date_range("2025-01-01", periods=len(rows), tz="UTC"),
    )


@pytest.mark.parametrize("pattern", ["RBR", "DBR", "RBD", "DBD"])
def test_four_patterns_and_card_bounds(pattern):
    bars = pattern_bars(pattern)
    zones = detect_zones(bars, "SPY.US")
    assert len(zones) == 1
    zone = zones[0]
    assert zone.pattern == pattern
    assert zone.base_candles == 1
    assert zone.confirmed_at == bars.index[-1].isoformat()
    assert zone.official_score is None
    assert "Partial" in zone.score_explanation
    assert zone.rule_version == "surge-card-20260501-boundaries-v1"
    assert zone.detection_version.startswith("experimental")
    score = zone_scorecard(zone)
    assert (score.earned, score.available, score.total) == (1, 1, None)
    assert score.entry_guidance is None
    if pattern[-1] == "R":
        assert zone.side == "Demand"
        assert (zone.proximal, zone.distal) == (100.1, 99.7)
    else:
        assert zone.side == "Supply"
        assert (zone.proximal, zone.distal) == (100, 100.3)
    assert zone.width == pytest.approx(abs(zone.proximal - zone.distal))


@pytest.mark.parametrize(
    "pattern,expected",
    [
        ("DBR", (101, 80)),
        ("RBR", (101, 90)),
        ("RBD", (100, 120)),
        ("DBD", (100, 110)),
    ],
)
def test_card_distal_includes_pattern_specific_legs(pattern, expected):
    # The rule helper supports full multi-candle leg spans independently of detection.
    incoming = pd.DataFrame(
        {"open": [95, 100], "close": [100, 102], "high": [120, 115], "low": [80, 85]}
    )
    base = pd.DataFrame({"open": [100], "close": [101], "high": [103], "low": [98]})
    outgoing = pd.DataFrame(
        {"open": [101, 102], "close": [102, 103], "high": [105, 110], "low": [95, 90]}
    )
    assert zone_boundaries(pattern, incoming, base, outgoing) == expected


def test_prefix_and_cutoff_invariance():
    bars = pattern_bars()
    for i in range(1, len(bars) + 1):
        prefix = detect_zones(bars.iloc[:i], "SPY.US")
        cutoff = detect_zones(bars, "SPY.US", as_of=bars.index[i - 1])
        assert prefix == cutoff
        assert all(pd.Timestamp(zone.confirmed_at) <= bars.index[i - 1] for zone in prefix)
    assert not detect_zones(bars.iloc[:-1], "SPY.US")
    future = bars.iloc[-1:].copy()
    future.index = future.index + pd.Timedelta(days=1)
    future[["open", "high", "low", "close"]] *= 9
    assert detect_zones(pd.concat([bars, future]), "SPY.US")[:1] == detect_zones(bars, "SPY.US")


@pytest.mark.parametrize("column", ["gap_before", "adjustment_break"])
def test_data_discontinuity_excludes_patterns(column):
    bars = pattern_bars()
    bars[column] = False
    bars.loc[bars.index[-2], column] = True
    assert not detect_zones(bars, "SPY.US")


def test_base_isolation_and_threshold_configuration():
    bars = pattern_bars()
    bars.loc[bars.index[-2], "close"] = 100.29
    bars.loc[bars.index[-2], "open"] = 99.71
    assert not detect_zones(bars, "SPY.US")
    assert detect_zones(bars, "SPY.US", DetectorConfig(max_base_body_fraction=1))
    assert not detect_zones(pattern_bars(), "SPY.US", DetectorConfig(min_impulse_body_atr=100))


def test_bos_fvg_volume_and_serialization():
    zone = detect_zones(pattern_bars(), "SPY.US")[0]
    assert zone.bos is True
    assert zone.fvg is False
    assert zone.relative_volume > 1
    assert asdict(zone)["status"] == "confirmed; lifecycle not evaluated"
    bars = pattern_bars()
    bars["volume"] = 0
    assert detect_zones(bars, "SPY.US")[0].relative_volume is None


def test_multiple_base_candles_and_maximum_count():
    original = pattern_bars()
    bars = pd.concat([original.iloc[:-1], original.iloc[-2:-1], original.iloc[-1:]])
    bars.index = pd.date_range("2025-01-01", periods=len(bars), tz="UTC")
    zone = detect_zones(bars, "SPY.US")[0]
    assert zone.base_candles == 2
    assert not detect_zones(bars, "SPY.US", DetectorConfig(max_base_candles=1))


def test_fvg_uses_only_available_third_candle():
    bars = pattern_bars()
    bars.loc[bars.index[-1], ["open", "low", "high", "close"]] = [100.5, 100.4, 103, 102.8]
    assert detect_zones(bars, "SPY.US")[0].fvg is True


@pytest.mark.parametrize("change", ["unsorted", "duplicate", "naive", "nan", "bad_high"])
def test_reject_invalid_bars(change):
    bars = pattern_bars()
    if change == "unsorted":
        bars = bars.iloc[::-1]
    elif change == "duplicate":
        bars = pd.concat([bars, bars.iloc[-1:]])
    elif change == "naive":
        bars.index = bars.index.tz_localize(None)
    elif change == "nan":
        bars.iloc[-1, 0] = float("nan")
    else:
        bars.iloc[-1, 1] = 1
    with pytest.raises(ValueError):
        detect_zones(bars, "SPY.US")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"atr_period": 0},
        {"atr_period": 2.5},
        {"max_base_body_fraction": 2},
        {"min_impulse_body_atr": float("nan")},
    ],
)
def test_config_validation(kwargs):
    with pytest.raises(ValueError):
        DetectorConfig(**kwargs)
