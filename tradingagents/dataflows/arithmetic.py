"""Deterministic arithmetic validator (P0-B).

Percentage moves, distances from reference levels and same-session
alignment are computed in code, never trusted from an agent's prose. The
2026-11-08 BRK-B report stated a -11.3% distance from the 52-week high,
+4.5% over SMA200 and +12.1% off the low at a 570.89 close; the correct
values against 586.30 / 497.723 / 464.01 are -2.63% / +14.70% / +23.03%.
A stated percentage that contradicts the data is `ARITHMETIC_MISMATCH`,
never a certified fact.

Two metrics the report conflated are kept distinct: the intraday
open→close move and the close→close move measure different things.

Every function is pure and ticker-agnostic: the same formula serves a USD
mega-cap, a Milan-listed utility and a crypto pair. A missing or zero
reference yields ``None`` rather than an invented number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Reason codes, stable for the audit trail and the Execution Gate.
ARITHMETIC_MISMATCH = "ARITHMETIC_MISMATCH"
UNIT_MISMATCH = "UNIT_MISMATCH"
PRICE_TIMESTAMP_MISMATCH = "PRICE_TIMESTAMP_MISMATCH"
OK = "OK"

# Tolerance for a stated percentage, in percentage points. A report may
# round to one decimal; beyond this the figure is arithmetic, not rounding.
DEFAULT_PCT_TOLERANCE = 0.05


def _finite(value: float | None) -> bool:
    return value is not None and isinstance(value, (int, float)) \
        and math.isfinite(value)


def percent_distance(current: float | None, reference: float | None) -> float | None:
    """``(current / reference - 1) * 100``, or None when not computable.

    The sign tells the direction: a close below a high is negative, above a
    moving average positive. A zero or missing reference yields None — a
    percentage against nothing is not a fact.
    """
    if not (_finite(current) and _finite(reference)) or reference == 0:
        return None
    return (current / reference - 1.0) * 100.0


def open_to_close_return(open_price: float | None, close_price: float | None) -> float | None:
    """The session's intraday move: open to close, in percent."""
    return percent_distance(close_price, open_price)


def close_to_close_return(previous_close: float | None,
                          close_price: float | None) -> float | None:
    """The session's close-over-close move, in percent — a different metric."""
    return percent_distance(close_price, previous_close)


@dataclass(frozen=True)
class ArithmeticVerdict:
    """Whether a stated percentage agrees with the computed one."""

    status: str
    reason_code: str
    label: str
    stated_pct: float | None
    computed_pct: float | None
    tolerance: float
    blocks_decision: bool
    message: str

    def summary(self) -> dict:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "label": self.label,
            "stated_pct": self.stated_pct,
            "computed_pct": self.computed_pct,
            "tolerance": self.tolerance,
            "blocks_decision": self.blocks_decision,
            "message": self.message,
        }


def check_stated_percentage(
    stated_pct: float | None,
    reference: float | None,
    current: float | None,
    *,
    label: str = "percentage",
    tolerance: float = DEFAULT_PCT_TOLERANCE,
) -> ArithmeticVerdict:
    """Compare a percentage the report states against the computed one.

    A figure beyond ``tolerance`` percentage points from the arithmetic is
    ``ARITHMETIC_MISMATCH`` and blocks: a report may round, it may not
    invent. When either side is not computable the verdict is
    ``NOT_CHECKABLE`` and does not block on arithmetic grounds — the
    missing data is a separate problem the freshness gate owns.
    """
    computed = percent_distance(current, reference)
    if stated_pct is None or computed is None:
        return ArithmeticVerdict(
            status="NOT_CHECKABLE", reason_code=OK, label=label,
            stated_pct=stated_pct, computed_pct=computed,
            tolerance=tolerance, blocks_decision=False,
            message=(
                f"{label}: not checkable (stated {stated_pct!r}, computed "
                f"{computed!r}); the inputs are missing, not wrong"
            ),
        )
    delta = abs(stated_pct - computed)
    if delta > tolerance:
        return ArithmeticVerdict(
            status="MISMATCH", reason_code=ARITHMETIC_MISMATCH, label=label,
            stated_pct=stated_pct, computed_pct=computed,
            tolerance=tolerance, blocks_decision=True,
            message=(
                f"{label}: stated {stated_pct:+.2f}% but the data gives "
                f"{computed:+.2f}% (off by {delta:.2f} pp > {tolerance} pp)"
            ),
        )
    return ArithmeticVerdict(
        status="PASS", reason_code=OK, label=label,
        stated_pct=stated_pct, computed_pct=computed,
        tolerance=tolerance, blocks_decision=False,
        message=f"{label}: stated {stated_pct:+.2f}% matches {computed:+.2f}%",
    )


def check_price_timestamp_alignment(
    price_as_of: str | None,
    indicator_as_of: str | None,
    *,
    indicator: str = "indicator",
) -> ArithmeticVerdict:
    """Whether a price and an indicator come from the same session.

    An indicator computed from a different session than the price mixes two
    snapshots: a distance from "SMA200" is meaningless if the two dates
    differ. A mismatch blocks — a fabricated reconciliation would be worse
    than an honest gap.
    """
    if not price_as_of or not indicator_as_of:
        return ArithmeticVerdict(
            status="NOT_CHECKABLE", reason_code=OK, label=indicator,
            stated_pct=None, computed_pct=None, tolerance=0.0,
            blocks_decision=False,
            message="price or indicator has no timestamp; alignment unverifiable",
        )
    if price_as_of != indicator_as_of:
        return ArithmeticVerdict(
            status="MISMATCH", reason_code=PRICE_TIMESTAMP_MISMATCH,
            label=indicator, stated_pct=None, computed_pct=None,
            tolerance=0.0, blocks_decision=True,
            message=(
                f"{indicator} is from {indicator_as_of} but the price is "
                f"from {price_as_of}: two snapshots, not one"
            ),
        )
    return ArithmeticVerdict(
        status="PASS", reason_code=OK, label=indicator,
        stated_pct=None, computed_pct=None, tolerance=0.0,
        blocks_decision=False,
        message=f"{indicator} and price share the {price_as_of} snapshot",
    )


def check_unit_compatibility(price_unit: str | None,
                             metric_unit: str | None) -> ArithmeticVerdict:
    """Whether two figures are in the same unit before a ratio is taken.

    A ratio across incompatible units (a price in GBp against a book value
    in GBP) is wrong by the unit factor; the caller must convert first.
    """
    if not price_unit or not metric_unit:
        return ArithmeticVerdict(
            status="NOT_CHECKABLE", reason_code=OK, label="unit",
            stated_pct=None, computed_pct=None, tolerance=0.0,
            blocks_decision=False,
            message="one side carries no unit; compatibility unverifiable",
        )
    if price_unit.strip() != metric_unit.strip():
        return ArithmeticVerdict(
            status="MISMATCH", reason_code=UNIT_MISMATCH, label="unit",
            stated_pct=None, computed_pct=None, tolerance=0.0,
            blocks_decision=True,
            message=(
                f"price in {price_unit} vs metric in {metric_unit}: convert "
                "before any ratio"
            ),
        )
    return ArithmeticVerdict(
        status="PASS", reason_code=OK, label="unit", stated_pct=None,
        computed_pct=None, tolerance=0.0, blocks_decision=False,
        message=f"both sides in {price_unit}",
    )
