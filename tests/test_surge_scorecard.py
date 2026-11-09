from dataclasses import replace

import pytest

from tradingagents.surge.scorecard import ScoreEvidence, score_evidence

BEST = ScoreEvidence(
    as_of="2026-11-06T21:00:00Z",
    side="Demand",
    base_candles=1,
    move_out_rr=2,
    breakout=True,
    tested=False,
    trend_alignment="with",
    curve_location="low",
    profit_rr=5,
    opposing_zone_fresh=True,
)


def points(evidence, criterion):
    return next(c.points for c in score_evidence(evidence).components if c.criterion == criterion)


@pytest.mark.parametrize("count,expected", [(1, 1), (3, 1), (4, 0.5), (6, 0.5), (7, 0)])
def test_time_bands(count, expected):
    assert points(replace(BEST, base_candles=count), "Time") == expected


@pytest.mark.parametrize(
    "ratio,breakout,expected",
    [
        (2, True, 2),
        (2, False, 1),
        (1.99, True, 1),
        (1.99, False, 0),
        (None, True, None),
        (2, None, None),
    ],
)
def test_strength_needs_move_out_and_breakout(ratio, breakout, expected):
    assert points(replace(BEST, move_out_rr=ratio, breakout=breakout), "Strength") == expected


@pytest.mark.parametrize(
    "penetration,expected", [(0, 1), (0.5, 1), (0.50001, 0), (1, 0), (1.01, None), (None, None)]
)
def test_freshness_bands(penetration, expected):
    assert points(replace(BEST, tested=True, penetration=penetration), "Freshness") == expected
    assert points(BEST, "Freshness") == 2


@pytest.mark.parametrize("alignment,expected", [("with", 2), ("sideways", 1), ("against", 0)])
def test_trend_bands(alignment, expected):
    assert points(replace(BEST, trend_alignment=alignment), "Trend") == expected


@pytest.mark.parametrize(
    "side,location,expected",
    [
        ("Demand", "low", 1),
        ("Demand", "middle", 0.5),
        ("Demand", "high", 0),
        ("Supply", "high", 1),
        ("Supply", "middle", 0.5),
        ("Supply", "low", 0),
    ],
)
def test_directional_curve_bands(side, location, expected):
    assert points(replace(BEST, side=side, curve_location=location), "Curve") == expected


@pytest.mark.parametrize("ratio,expected", [(2.99, 0), (3, 1), (4.99, 1), (5, 2)])
def test_profit_zone_thresholds(ratio, expected):
    assert points(replace(BEST, profit_rr=ratio), "Profit Zone") == expected
    assert points(replace(BEST, opposing_zone_fresh=None), "Profit Zone") is None
    assert points(replace(BEST, opposing_zone_fresh=False), "Profit Zone") is None


@pytest.mark.parametrize(
    "kwargs,total,guidance",
    [
        ({}, 10, "Proximal entry"),
        ({"base_candles": 4, "trend_alignment": "sideways"}, 8.5, "Proximal entry"),
        ({"base_candles": 7, "trend_alignment": "sideways"}, 8, "Confirmation entry"),
        ({"base_candles": 7, "trend_alignment": "against"}, 7, "Confirmation entry"),
        ({"base_candles": 4, "trend_alignment": "against", "profit_rr": 3}, 6.5, "No trade"),
    ],
)
def test_complete_score_and_entry_thresholds(kwargs, total, guidance):
    score = score_evidence(replace(BEST, **kwargs))
    assert score.complete
    assert score.total == total
    assert score.available == 10
    assert score.entry_guidance == guidance


def test_missing_evidence_never_rescaled_or_recommended():
    empty = score_evidence(ScoreEvidence(as_of=BEST.as_of, side="Supply"))
    partial = score_evidence(ScoreEvidence(as_of=BEST.as_of, side="Supply", base_candles=4))
    assert (empty.earned, empty.available, empty.total) == (0, 0, None)
    assert (partial.earned, partial.available, partial.total) == (0.5, 1, None)
    assert not partial.complete
    assert partial.entry_guidance is None
    assert sum(c.points is None for c in partial.components) == 5
    assert partial.as_of == BEST.as_of


@pytest.mark.parametrize(
    "kwargs",
    [
        {"as_of": "2026-11-06"},
        {"side": "invalid"},
        {"base_candles": 0},
        {"base_candles": True},
        {"base_candles": 1.5},
        {"move_out_rr": float("nan")},
        {"penetration": -0.1},
        {"profit_rr": float("inf")},
        {"breakout": 1},
        {"trend_alignment": "up"},
        {"curve_location": "bottom third"},
        {"tested": False, "penetration": 0.5},
    ],
)
def test_reject_inconsistent_evidence(kwargs):
    with pytest.raises(ValueError):
        replace(BEST, **kwargs)
