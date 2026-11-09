"""Exact decimal arithmetic for money, percentages and ratios (§3).

The requirement this module exists to satisfy: monetary calculations use
``decimal.Decimal``, precision and rounding are explicit, and no implicit
``float`` conversion happens for money. ``float`` is a binary fraction and
``0.1 + 0.2 != 0.3``; a P/B of 1.4801 that silently becomes 1.4800999999
is the kind of drift that makes an audit unreproducible.

Three rules are enforced here rather than left to callers:

1. **A quantum per domain.** Money, percentages and ratios each have one
   rounding rule and one number of places, defined once.
2. **No float for money.** ``as_decimal`` accepts ``int``, ``str``,
   ``Decimal`` and ``float`` — but a ``float`` is converted through its
   shortest repr (``Decimal("570.89")``, not ``Decimal(570.89)``), so the
   value that enters is the value the provider printed.
3. **Nothing is invented.** A missing value, a non-finite value or a
   division by zero yields ``None`` rather than a substitute number.

Point vs relative percentage is kept explicit, because confusing the two is
a real defect: "+0.5 percentage points" and "+0.5%" are different claims.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

# One rounding rule for the whole engine. Financial reporting rounds halves
# away from zero; Python's default ``ROUND_HALF_EVEN`` would round 0.125 to
# 0.12 and disagree with every broker statement.
DEFAULT_ROUNDING = ROUND_HALF_UP

# Display quanta. These are *presentation* precisions and are applied only
# where the domain says so — never to intermediate values.
MONEY_QUANTUM = Decimal("0.01")      # currency amounts
PERCENT_QUANTUM = Decimal("0.0001")  # percentages, 4 dp
RATIO_QUANTUM = Decimal("0.0001")    # multiples, 4 dp
UNIT_PRICE_QUANTUM = Decimal("0.0001")  # per-share prices (sub-cent instruments)


class Unit(StrEnum):
    """A money unit of measure, with its factor to base currency units.

    Providers disagree about scale: EDGAR reports some figures in millions,
    Yahoo in base units, an Italian filing in thousands. Storing the unit
    next to the amount is what lets ``convert_unit`` be unambiguous — the
    alternative, a bare number whose scale lives in a docstring, is how a
    1,000x error reaches a report.
    """

    BASE = "base"
    THOUSAND = "thousand"
    MILLION = "million"
    BILLION = "billion"

    @property
    def factor(self) -> Decimal:
        return {
            Unit.BASE: Decimal(1),
            Unit.THOUSAND: Decimal(1000),
            Unit.MILLION: Decimal(1_000_000),
            Unit.BILLION: Decimal(1_000_000_000),
        }[self]

    @classmethod
    def parse(cls, raw: str | None) -> Unit | None:
        """Read a unit label in the spellings vendors actually use.

        ``"USD_million"``, ``"millions"``, ``"mn"`` and ``"in millions"``
        all mean the same thing; an unknown label returns ``None`` so the
        caller refuses rather than assuming base units.
        """
        if not raw:
            return None
        text = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
        tokens = set(text.replace("usd_", "").replace("eur_", "")
                     .replace("gbp_", "").split("_"))
        if tokens & {"billion", "billions", "bn", "b"}:
            return Unit.BILLION
        if tokens & {"million", "millions", "mn", "m"}:
            return Unit.MILLION
        if tokens & {"thousand", "thousands", "k"}:
            return Unit.THOUSAND
        if tokens & {"base", "units", "unit", ""}:
            return Unit.BASE
        return None


def as_decimal(value: Any) -> Decimal | None:
    """Convert a provider value to ``Decimal`` without inventing precision.

    ``float`` goes through ``repr`` (its shortest round-trip form), so the
    decimal sees ``570.89`` and not ``570.89000000000004``. A bool is
    rejected: ``True`` is not a price. Non-finite input yields ``None``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            parsed = Decimal(text)
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None
    return None


def quantize(value: Decimal | None, quantum: Decimal = RATIO_QUANTUM) -> Decimal | None:
    """Round to ``quantum`` with the engine's explicit rounding rule.

    Applied at the domain's output boundary only — an intermediate value
    stays exact, because rounding early compounds.

    A value with more significant digits than the decimal context can hold
    raises ``InvalidOperation`` from ``quantize``. That is not an error to
    propagate through a report pipeline: an amount that large is outside any
    financial range this engine serves, so it is refused as ``None`` rather
    than crashing the run. Found by the property-based test that asserts no
    ratio helper ever raises.
    """
    if value is None:
        return None
    try:
        return value.quantize(quantum, rounding=DEFAULT_ROUNDING)
    except (InvalidOperation, ValueError):
        return None


def divide(numerator: Any, denominator: Any) -> Decimal | None:
    """``numerator / denominator``, or ``None`` when that is undefined.

    Division by zero is not an error to raise in a report pipeline; it is a
    metric that cannot be computed, and ``None`` says so. A stale or missing
    denominator must not become ``0.0`` and then a plausible-looking ratio.
    """
    num, den = as_decimal(numerator), as_decimal(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def safe_ratio(numerator: Any, denominator: Any,
               quantum: Decimal = RATIO_QUANTUM) -> Decimal | None:
    """A financial multiple (P/E, P/B), rounded once at the output."""
    return quantize(divide(numerator, denominator), quantum)


def pct_change(new_value: Any, reference_value: Any,
               quantum: Decimal | None = PERCENT_QUANTUM) -> Decimal | None:
    """Relative change in percent: ``(new / reference - 1) * 100`` (§6).

    This is the one convention the engine uses for every percentage move.
    Distances from a moving average use the same formula, so a "+9.46% over
    SMA50" and a "-2.63% from the high" are computed by identical code.
    """
    new, ref = as_decimal(new_value), as_decimal(reference_value)
    if new is None or ref is None or ref == 0:
        return None
    change = (new / ref - Decimal(1)) * Decimal(100)
    return change if quantum is None else quantize(change, quantum)


def percentage_points(delta: Any, quantum: Decimal = PERCENT_QUANTUM) -> Decimal | None:
    """An absolute change expressed in percentage points, not relative.

    ``quantize`` alone cannot express this: 4.5% -> 5.0% is +0.5 *points*
    and +11.1 *percent*. Keeping the two functions separate is what stops a
    report from claiming one while computing the other.
    """
    value = as_decimal(delta)
    return None if value is None else quantize(value, quantum)


def convert_unit(value: Any, from_unit: Unit | str | None,
                 to_unit: Unit | str | None,
                 quantum: Decimal | None = None) -> Decimal | None:
    """Rescale a money amount between base / thousand / million / billion.

    ``convert_unit(761368, Unit.MILLION, Unit.BASE)`` is 761,368,000,000.
    An unknown unit returns ``None``: the scale of a number is not something
    to assume, and assuming base units for a figure reported in millions is
    a three-orders-of-magnitude error.
    """
    amount = as_decimal(value)
    source = from_unit if isinstance(from_unit, Unit) else Unit.parse(from_unit)
    target = to_unit if isinstance(to_unit, Unit) else Unit.parse(to_unit)
    if amount is None or source is None or target is None:
        return None
    scaled = amount * source.factor / target.factor
    return scaled if quantum is None else quantize(scaled, quantum)


def cagr(begin_value: Any, end_value: Any, years: Any,
         quantum: Decimal = PERCENT_QUANTUM) -> Decimal | None:
    """Compound annual growth rate, in percent, over ``years`` (§2A).

    ``((end / begin) ** (1 / years) - 1) * 100``. Non-positive endpoints and
    a non-positive duration yield ``None``: a CAGR across a zero-year span is
    not a number, it is a division by zero wearing a percentage sign. A sign
    change between the endpoints cannot be annualized either — going from
    -100 to +50 has no meaningful compound rate — so that returns ``None``.
    """
    begin, end, span = as_decimal(begin_value), as_decimal(end_value), as_decimal(years)
    if begin is None or end is None or span is None:
        return None
    if begin <= 0 or end <= 0 or span <= 0:
        return None
    # ``**`` with a fractional exponent needs float semantics; the exponent is
    # the only place where that is unavoidable, and the result is re-quantized.
    rate = (float(end / begin) ** (1.0 / float(span)) - 1.0) * 100.0
    if not math.isfinite(rate):
        return None
    return quantize(Decimal(repr(rate)), quantum)


def weighted_mean(values: list[Any], weights: list[Any],
                  quantum: Decimal = RATIO_QUANTUM) -> Decimal | None:
    """A weight-weighted mean — e.g. a share-class-weighted average price.

    Lengths must match and weights must sum to a positive amount; anything
    else returns ``None`` rather than silently re-weighting.
    """
    if not values or len(values) != len(weights):
        return None
    total_weight = Decimal(0)
    total = Decimal(0)
    for raw_value, raw_weight in zip(values, weights, strict=True):
        value, weight = as_decimal(raw_value), as_decimal(raw_weight)
        if value is None or weight is None:
            return None
        total += value * weight
        total_weight += weight
    if total_weight == 0:
        return None
    return quantize(total / total_weight, quantum)


def mean(values: list[Any], quantum: Decimal = RATIO_QUANTUM) -> Decimal | None:
    """The arithmetic mean, or ``None`` for an empty series."""
    if not values:
        return None
    decimals = [as_decimal(v) for v in values]
    if any(d is None for d in decimals):
        return None
    total = sum((d for d in decimals if d is not None), Decimal(0))
    return quantize(total / Decimal(len(decimals)), quantum)


def annualize(value: Any, periods_per_year: Any,
              quantum: Decimal = RATIO_QUANTUM) -> Decimal | None:
    """Scale a per-period figure to a year (e.g. a quarterly run-rate)."""
    rate = as_decimal(periods_per_year)
    if rate is None or rate <= 0:
        return None
    return quantize(as_decimal(value) * rate if as_decimal(value) is not None else None,
                    quantum)


class Money:
    """An amount with a currency and a unit of measure, kept together.

    The pairing is the point: a bare ``761368`` is ambiguous between 761
    thousand and 761 billion dollars, and mixing the two produces a report
    that is wrong by a million and looks entirely normal.
    """

    __slots__ = ("amount", "currency", "unit")

    def __init__(self, amount: Any, currency: str | None = None,
                 unit: Unit | str = Unit.BASE) -> None:
        parsed = as_decimal(amount)
        if parsed is None:
            raise ValueError(f"Money needs a finite amount, got {amount!r}")
        parsed_unit = unit if isinstance(unit, Unit) else Unit.parse(unit)
        if parsed_unit is None:
            raise ValueError(f"unknown money unit: {unit!r}")
        self.amount: Decimal = parsed
        self.currency: str | None = currency.upper() if currency else None
        self.unit: Unit = parsed_unit

    def to_base(self) -> Decimal:
        """The amount in base currency units (dollars, euros, ...)."""
        return self.amount * self.unit.factor

    def to(self, unit: Unit | str) -> Money:
        """The same amount expressed in another unit."""
        target = unit if isinstance(unit, Unit) else Unit.parse(unit)
        if target is None:
            raise ValueError(f"unknown money unit: {unit!r}")
        return Money(self.to_base() / target.factor, self.currency, target)

    def compatible(self, other: Money) -> bool:
        """Whether two amounts may be compared or divided.

        Same currency required; the unit is a scale and is converted, so a
        million-USD figure and a base-USD figure *are* compatible once
        normalized. An unlabelled currency is not compatible with a labelled
        one — "unknown" is not "the same as".
        """
        return (self.currency is not None and other.currency is not None
                and self.currency == other.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return (self.compatible(other) and self.to_base() == other.to_base())

    def __repr__(self) -> str:
        return f"Money({self.amount}, {self.currency!r}, {self.unit.value!r})"

    def as_dict(self) -> dict:
        return {"amount": str(self.amount),
                "currency": self.currency,
                "unit": self.unit.value}
