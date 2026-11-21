"""Harmonic pattern scanner (HPC-style options, published harmonic ratios)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.strategy_indicators import harmonic_scanner as hs
from tradingagents.dataflows.strategy_indicators.calc import Pivot


def _path(points: list[float], bars: int = 15) -> np.ndarray:
    """Straight legs of ``bars`` bars between the given swing prices."""
    out = [points[0]]
    for a, b in zip(points[:-1], points[1:], strict=True):
        out += list(np.linspace(a, b, bars + 1)[1:])
    return np.array(out, float)


def _frame(closes: np.ndarray) -> pd.DataFrame:
    c = np.asarray(closes, float)
    return pd.DataFrame({"Date": pd.bdate_range("2024-01-01", periods=len(c)), "Open": c,
                         "High": c * 1.003, "Low": c * 0.997, "Close": c, "Volume": 1000.0})


# X=100, A=200, B=138.2 (0.618 XA), C=176.4 (0.618 AB), D=121.4 (0.786 XA).
GARTLEY = [130, 100, 200, 138.2, 176.4]
D_GARTLEY = 121.4


def _scan(points: list[float], settings: hs.ScanSettings | None = None):
    df = _frame(_path(points))
    return df, hs.compute_harmonic_scanner(df, df["Date"].iloc[0], settings)


def _table(result, prefix: str) -> pd.DataFrame:
    return next(t for title, t in result.tables if title.startswith(prefix))


@pytest.mark.unit
def test_a_completed_gartley_is_confirmed_with_its_zone_targets_and_outcome():
    _, r = _scan([*GARTLEY, D_GARTLEY, 175])
    done = _table(r, "Patterns completed")
    row = done[done["Pattern"] == "Gartley"].iloc[0]
    assert row["Bias"] == "bullish" and row["Status"] == "confirmed"
    assert row["PRZ low"] <= row["D"] <= row["PRZ high"]
    assert row["Stop"] == pytest.approx(row["X"])                     # Gartley: invalid past X
    assert row["T1"] == pytest.approx(row["D"] + 0.382 * (row["A"] - row["D"]))
    assert row["T2"] == pytest.approx(row["D"] + 0.618 * (row["A"] - row["D"]))
    assert row["Outcome"] == "T2 hit"                                 # the rally reached 175
    assert row["Confirmed on"] > row["D date"]                        # known only after the reversal


@pytest.mark.unit
def test_a_bearish_gartley_mirrors_the_bullish_one():
    _, r = _scan([300 - p for p in [*GARTLEY, D_GARTLEY, 175]])
    done = _table(r, "Patterns completed")
    row = done[done["Pattern"] == "Gartley"].iloc[0]
    assert row["Bias"] == "bearish" and row["Stop"] == pytest.approx(row["X"])
    assert row["T1"] < row["D"]


@pytest.mark.unit
def test_a_d_leg_inside_the_zone_is_pending():
    _, r = _scan([*GARTLEY, 122])
    assert r.headline.startswith("Pending bullish Gartley")
    forming = _table(r, "Pending and potential")
    row = forming[forming["Pattern"] == "Gartley"].iloc[0]
    assert row["Status"] == "pending (in PRZ)" and row["Distance to PRZ"] == "inside"


@pytest.mark.unit
def test_a_d_leg_short_of_the_zone_is_potential_with_the_zone_ahead():
    _, r = _scan([*GARTLEY, 160])
    forming = _table(r, "Pending and potential")
    row = forming[forming["Pattern"] == "Gartley"].iloc[0]
    assert row["Status"] == "potential"
    # 0.756..0.816 of XA below A, overlapping BC's 1.13..1.618 projection below C.
    assert row["PRZ low"] == pytest.approx(row["A"] - 0.816 * (row["A"] - row["X"]))
    assert row["PRZ high"] == pytest.approx(row["A"] - 0.756 * (row["A"] - row["X"]))
    assert row["Distance to PRZ"].startswith("-")


@pytest.mark.unit
def test_a_d_leg_through_the_zone_drops_the_pattern():
    _, r = _scan([*GARTLEY, 110])
    forming = [t for title, t in r.tables if title.startswith("Pending and potential")]
    assert not forming or "Gartley" not in set(forming[0]["Pattern"])


@pytest.mark.unit
def test_strict_abcd_requires_cd_to_match_ab_in_atrs():
    # AB = 50, BC = 30 (0.6 AB), CD = 75 (2.5 BC): an AB=CD by ratios, not by length.
    points = [180, 200, 150, 180, 105, 150]
    _, strict = _scan(points, hs.ScanSettings(patterns=("AB=CD",)))
    _, loose = _scan(points, hs.ScanSettings(patterns=("AB=CD",), strict_abcd=False))
    assert not any(t.startswith("Patterns completed") for t, _ in strict.tables)
    assert "AB=CD" in set(_table(loose, "Patterns completed")["Pattern"])


@pytest.mark.unit
def test_bias_and_pattern_filters_are_honoured():
    _, r = _scan([*GARTLEY, D_GARTLEY, 175], hs.ScanSettings(show_bullish=False))
    assert all("bullish" not in set(t.get("Bias", pd.Series(dtype=str))) for _, t in r.tables)
    _, r = _scan([*GARTLEY, D_GARTLEY, 175], hs.ScanSettings(patterns=("Bat",)))
    assert "Gartley" not in r.headline


@pytest.mark.unit
def test_overlapping_patterns_keep_the_better_one():
    def row(q, points, span, bullish=True):
        return {"Quality": q, "D date": pd.Timestamp("2024-01-01"), "_points": frozenset(points),
                "_span": span, "_bullish": bullish}

    best = row(90, {1, 2, 3, 4, 5}, (1, 5))
    shares_three = row(80, {3, 4, 5, 6, 7}, (3, 7))
    inside = row(70, {10, 11, 12, 13}, (10, 13))
    outer = row(85, {9, 14, 15, 16, 17}, (9, 17))
    kept = hs._filter_overlaps([best, shares_three, inside, outer], hs.ScanSettings())
    assert best in kept and outer in kept
    assert shares_three not in kept and inside not in kept
    kept = hs._filter_overlaps([best, shares_three], hs.ScanSettings(max_points_shared=3))
    assert shares_three in kept


@pytest.mark.unit
def test_a_bar_touching_stop_and_target_counts_as_stopped():
    df = _frame(np.array([100.0, 90.0, 95.0]))
    df.loc[2, ["High", "Low"]] = [120.0, 80.0]
    d = Pivot(1, df["Date"].iloc[1], 90.0, "L", True)
    assert hs._outcome(df, d, stop=85.0, targets={"T1": 100.0, "T2": 110.0}) == "stopped"


@pytest.mark.unit
def test_published_ratios_score_full_quality():
    spec = hs.PATTERNS["Gartley"]
    assert hs.quality(spec, {"XB": 0.618, "AC": 0.634, "XD": 0.786, "BD": 1.374}) == pytest.approx(100)
    assert hs.quality(spec, {"XB": 0.648, "AC": 0.886, "XD": 0.816, "BD": 1.618}) < 10


@pytest.mark.unit
def test_nothing_after_the_last_bar_is_read():
    # Cut while the C-D leg is still falling: the full history's confirmed
    # Gartley must show up only as a potential one, with no outcome.
    df = _frame(_path([*GARTLEY, D_GARTLEY, 175]))
    cut = df.iloc[: len(df) - 20].reset_index(drop=True)
    r = hs.compute_harmonic_scanner(cut, cut["Date"].iloc[0])
    assert not any(title.startswith("Patterns completed") for title, _ in r.tables)
    forming = _table(r, "Pending and potential")
    assert forming[forming["Pattern"] == "Gartley"].iloc[0]["Status"] == "potential"
