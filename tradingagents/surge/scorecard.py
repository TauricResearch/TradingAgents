"""Reference Card 2 (20260501) scoring of explicit, as-of observations.

This module applies score bands; it does not infer swings, curve partitions,
breakout definitions, revisit paths, or opposing fresh zones from prices.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class ScoreEvidence:
    as_of: str
    side: Literal["Demand", "Supply"]
    base_candles: int | None = None
    move_out_rr: float | None = None
    breakout: bool | None = None
    tested: bool | None = None
    penetration: float | None = None
    trend_alignment: Literal["with", "sideways", "against"] | None = None
    curve_location: Literal["low", "middle", "high"] | None = None
    profit_rr: float | None = None
    opposing_zone_fresh: bool | None = None

    def __post_init__(self):
        if datetime.fromisoformat(self.as_of).tzinfo is None:
            raise ValueError("Score evidence needs an aware as-of timestamp")
        if self.side not in ("Demand", "Supply"):
            raise ValueError("side must be Demand or Supply")
        if self.base_candles is not None and (
            isinstance(self.base_candles, bool)
            or not isinstance(self.base_candles, int)
            or self.base_candles < 1
        ):
            raise ValueError("base_candles must be a positive integer")
        for value in (self.move_out_rr, self.penetration, self.profit_rr):
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value < 0
            ):
                raise ValueError("Ratios must be finite and nonnegative")
        for value in (self.breakout, self.tested, self.opposing_zone_fresh):
            if value is not None and not isinstance(value, bool):
                raise ValueError("Observation flags must be boolean or unknown")
        if self.trend_alignment not in (None, "with", "sideways", "against"):
            raise ValueError("Unknown trend alignment")
        if self.curve_location not in (None, "low", "middle", "high"):
            raise ValueError("Unknown curve location")
        if self.tested is False and self.penetration not in (None, 0):
            raise ValueError("An untested zone cannot have penetration")


@dataclass(frozen=True)
class ComponentScore:
    criterion: str
    points: float | None
    maximum: float
    explanation: str


@dataclass(frozen=True)
class Scorecard:
    as_of: str
    components: tuple[ComponentScore, ...]
    earned: float
    available: float
    total: float | None
    complete: bool
    entry_guidance: str | None
    rule_version: str = "surge-card-20260501-score-bands-v1"


def score_evidence(evidence: ScoreEvidence) -> Scorecard:
    """Unknown components remain null; partial results are never rescaled to /10.

    All observations must be known by as_of. The caller must verify price-derived
    evidence and its provenance; a timestamp alone cannot certify that contract.
    profit_rr must measure reward to a fresh opposing zone against actual planned
    risk, including the stop buffer, not an arbitrary 1R/2R/3R target scenario.
    """
    e = evidence
    scores = []

    def add(name, maximum, points, explanation):
        scores.append(ComponentScore(name, points, maximum, explanation))

    strength = None
    if e.move_out_rr is not None and e.breakout is not None:
        strength = float(int(e.move_out_rr >= 2) + int(e.breakout))
    add(
        "Strength",
        2,
        strength,
        "Move-out of at least 2:1 and breakout: both=2, one=1, neither=0; "
        "both observations required",
    )
    count = e.base_candles
    add(
        "Time",
        1,
        None if count is None else 1 if count <= 3 else 0.5 if count <= 6 else 0,
        "Base candles: 1-3=1, 4-6=0.5, more than 6=0",
    )
    freshness = None
    if e.tested is False:
        freshness = 2
    elif e.tested is True and e.penetration is not None and e.penetration <= 1:
        freshness = 1 if e.penetration <= 0.5 else 0
    add(
        "Freshness",
        2,
        freshness,
        "Untested=2; tested up to 50%=1; over 50% through distal=0; "
        "penetration beyond distal requires a separate lifecycle assessment",
    )
    add(
        "Trend",
        2,
        {"with": 2, "sideways": 1, "against": 0}.get(e.trend_alignment),
        "ITF formation location: with trend=2, sideways=1, against=0; caller verifies controlling swings",
    )
    curve = None
    if e.curve_location is not None:
        favorable = "low" if e.side == "Demand" else "high"
        curve = 1 if e.curve_location == favorable else 0.5 if e.curve_location == "middle" else 0
    add(
        "Curve",
        1,
        curve,
        "HTF location: demand low/supply high=1, middle=0.5, opposite=0; "
        "HTF zones use wick-to-wick bounds",
    )
    profit = None
    if e.profit_rr is not None and e.opposing_zone_fresh is True:
        profit = 2 if e.profit_rr >= 5 else 1 if e.profit_rr >= 3 else 0
    add(
        "Profit Zone",
        2,
        profit,
        "R:R to an opposing fresh zone: at least 5:1=2, at least 3:1=1, "
        "below 3:1=0; arbitrary target scenarios do not qualify",
    )
    earned = float(sum(s.points for s in scores if s.points is not None))
    available = float(sum(s.maximum for s in scores if s.points is not None))
    complete = all(s.points is not None for s in scores)
    guidance = None
    if complete:
        guidance = (
            "Proximal entry"
            if earned >= 8.5
            else "Confirmation entry"
            if earned >= 7
            else "No trade"
        )
    return Scorecard(
        e.as_of, tuple(scores), earned, available, earned if complete else None, complete, guidance
    )
