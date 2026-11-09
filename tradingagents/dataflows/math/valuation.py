"""Valuation metrics (§2B) — earnings, returns and the P/B refusal.

``dataflows.valuation`` owns the *reconciliation* of BVPS, market cap and
P/B from possibly-conflicting inputs: currency guards, share-class guards,
derived-vs-reported drift. This module owns the *metrics* computed on top of
a reconciled valuation, and the check that refuses a P/B a report asserted
without it agreeing with price and book value.

The distinction matters. ``reconcile_valuation`` answers "what is the P/B
from these inputs?"; ``check_stated_multiple`` answers "the report said
1.35x — is that consistent with the data?". The second is what catches the
2026-11-09 regression: price 570.89 and BVPS 385.70 give 1.4801, so a
stated 1.35x is not a rounding difference, it is a different number.

Every metric here is returned as a ``MetricRecord`` carrying its formula,
operands and units, so the report can show what was verified. Missing
inputs never become zero: they produce ``NOT_COMPUTABLE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    MetricRecord,
    metric,
)
from tradingagents.dataflows.math.precision import (
    PERCENT_QUANTUM,
    RATIO_QUANTUM,
    Unit,
    as_decimal,
    cagr,
    convert_unit,
    divide,
    pct_change,
    quantize,
    safe_ratio,
)

# A stated multiple may differ from the computed one by this much and still
# be called rounding. 1.35 vs 1.4801 is 9.64% away — far beyond it.
MULTIPLE_TOLERANCE = Decimal("0.02")


def market_cap(price: Any, shares: Any, *, currency: str | None = None,
               period_end: str | None = None) -> MetricRecord:
    """``price * shares_outstanding``, in base currency units.

    Market cap and the equity it is compared against must share a currency
    and a share count basis; that reconciliation is the caller's job
    (``reconcile_valuation``), and this function records the computation.
    """
    price_d, shares_d = as_decimal(price), as_decimal(shares)
    value = price_d * shares_d if price_d is not None and shares_d is not None else None
    return metric(
        "market_cap", value, unit=currency or "base", formula_id="price_times_shares",
        operands={"price": price, "shares": shares}, period_end=period_end,
        reason="" if value is not None else "price or share count unavailable",
    )


def earnings_per_share(net_income: Any, shares: Any, *,
                       adjusted: bool = False,
                       period_end: str | None = None) -> MetricRecord:
    """EPS = net income available to common / shares outstanding.

    ``adjusted`` marks a non-GAAP figure. It is recorded in the unit string
    and the formula id because a GAAP EPS and an adjusted EPS are different
    metrics that must never be compared to each other or used
    interchangeably in a P/E (§4: "metriche GAAP, operative e adjusted non
    possono essere intercambiate").
    """
    value = divide(net_income, shares)
    basis = "adjusted" if adjusted else "gaap"
    return metric(
        "eps_adjusted" if adjusted else "eps_gaap", value, unit=f"{basis}_per_share",
        formula_id=f"net_income_div_shares_{basis}",
        operands={"net_income": net_income, "shares": shares},
        period_end=period_end,
        reason="" if value is not None else "net income or share count unavailable",
    )


def price_to_earnings(price: Any, eps: Any, *, basis: str = "gaap",
                      forward: bool = False,
                      period_end: str | None = None) -> MetricRecord:
    """P/E from a price and an EPS of a **stated** basis.

    ``basis`` and ``forward`` end up in the formula id so the audit can prove
    a trailing GAAP P/E was not silently compared with a forward adjusted
    one. That mix-up is invisible in the output number and changes it a lot.
    """
    value = safe_ratio(price, eps)
    label = f"{'forward' if forward else 'trailing'}_{basis}"
    return metric(
        "pe_forward" if forward else "pe_trailing", value, unit="multiple",
        formula_id=f"price_div_eps_{label}",
        operands={"price": price, "eps": eps, "basis": basis},
        period_end=period_end,
        reason="" if value is not None else "price or EPS unavailable or EPS zero",
    )


def earnings_yield(eps: Any, price: Any, *, period_end: str | None = None) -> MetricRecord:
    """Earnings yield in percent: ``eps / price * 100`` (the inverse of P/E)."""
    ratio = divide(eps, price)
    value = quantize(ratio * Decimal(100), PERCENT_QUANTUM) if ratio is not None else None
    return metric(
        "earnings_yield", value, unit="percent", formula_id="eps_div_price_pct",
        operands={"eps": eps, "price": price}, period_end=period_end,
        reason="" if value is not None else "EPS or price unavailable",
    )


def book_value_per_share(equity: Any, shares: Any, *, share_class: str | None = None,
                         period_end: str | None = None,
                         equity_unit: Unit | str = Unit.BASE) -> MetricRecord:
    """BVPS = equity attributable to common / share count, in base units.

    ``equity_unit`` is converted to base units first, so a figure reported
    in millions cannot be divided by a share count and produce a per-share
    value three orders of magnitude too large.
    """
    equity_base = convert_unit(equity, equity_unit, Unit.BASE)
    value = divide(equity_base, shares)
    name = f"book_value_per_share_{share_class}" if share_class else "book_value_per_share"
    return metric(
        name, value, unit="base_per_share", formula_id="equity_div_shares",
        operands={"equity": equity, "equity_unit": str(equity_unit),
                  "shares": shares},
        period_end=period_end,
        reason="" if value is not None else "equity or share count unavailable",
    )


def price_to_book(price: Any, bvps: Any, *, share_class: str | None = None,
                  period_end: str | None = None,
                  bvps_period_end: str | None = None) -> MetricRecord:
    """P/B = ``price / book value per share``, same class on both sides.

    A stale book value is refused rather than used: if the caller states the
    period of the BVPS and it differs from the price's period, the multiple
    mixes two dates and is reported as ``REFUSED`` with that reason (§12
    test 10: "P/B con periodo contabile obsoleto").
    """
    value = safe_ratio(price, bvps)
    stale = (period_end is not None and bvps_period_end is not None
             and bvps_period_end != period_end)
    name = f"price_to_book_{share_class}" if share_class else "price_to_book"
    if stale:
        return metric(
            name, value, unit="multiple", formula_id="price_div_bvps",
            operands={"price": price, "bvps": bvps}, period_end=period_end,
            calculation_status=CalculationStatus.REFUSED,
            reason=(f"book value is for {bvps_period_end} but the price is for "
                    f"{period_end}: the multiple mixes two periods"),
        )
    return metric(
        name, value, unit="multiple", formula_id="price_div_bvps",
        operands={"price": price, "bvps": bvps}, period_end=period_end,
        reason="" if value is not None else "price or book value unavailable",
    )


def debt_to_equity(total_debt: Any, equity: Any, *,
                   period_end: str | None = None) -> MetricRecord:
    """D/E as a ratio (0.17x), not a percentage."""
    value = safe_ratio(total_debt, equity)
    return metric(
        "debt_to_equity", value, unit="multiple", formula_id="total_debt_div_equity",
        operands={"total_debt": total_debt, "equity": equity}, period_end=period_end,
        reason="" if value is not None else "debt or equity unavailable",
    )


def return_on_equity(net_income: Any, equity: Any, *,
                     period_end: str | None = None) -> MetricRecord:
    """ROE in percent: ``net income / equity * 100``."""
    ratio = divide(net_income, equity)
    value = quantize(ratio * Decimal(100), PERCENT_QUANTUM) if ratio is not None else None
    return metric(
        "return_on_equity", value, unit="percent",
        formula_id="net_income_div_equity_pct",
        operands={"net_income": net_income, "equity": equity}, period_end=period_end,
        reason="" if value is not None else "net income or equity unavailable",
    )


def return_on_assets(net_income: Any, total_assets: Any, *,
                     period_end: str | None = None) -> MetricRecord:
    """ROA in percent: ``net income / total assets * 100``."""
    ratio = divide(net_income, total_assets)
    value = quantize(ratio * Decimal(100), PERCENT_QUANTUM) if ratio is not None else None
    return metric(
        "return_on_assets", value, unit="percent",
        formula_id="net_income_div_assets_pct",
        operands={"net_income": net_income, "total_assets": total_assets},
        period_end=period_end,
        reason="" if value is not None else "net income or assets unavailable",
    )


def equity_to_assets(equity: Any, total_assets: Any, *,
                     period_end: str | None = None) -> MetricRecord:
    """Equity/assets in percent — a solvency ratio, not a multiple."""
    ratio = divide(equity, total_assets)
    value = quantize(ratio * Decimal(100), PERCENT_QUANTUM) if ratio is not None else None
    return metric(
        "equity_to_assets", value, unit="percent",
        formula_id="equity_div_assets_pct",
        operands={"equity": equity, "total_assets": total_assets},
        period_end=period_end,
        reason="" if value is not None else "equity or assets unavailable",
    )


def growth_rate(begin_value: Any, end_value: Any,
                period_end: str | None = None) -> MetricRecord:
    """Period-over-period growth in percent (YoY/QoQ by the caller's periods).

    The caller passes values from *equivalent* periods; comparing a full
    year to a quarter is a different metric and the period labels in the
    record are what make that auditable.
    """
    value = pct_change(end_value, begin_value)
    return metric(
        "growth_rate", value, unit="percent", formula_id="pct_change",
        operands={"begin": begin_value, "end": end_value}, period_end=period_end,
        reason="" if value is not None else "begin or end value unavailable",
    )


def compound_annual_growth_rate(begin_value: Any, end_value: Any, years: Any,
                                period_end: str | None = None) -> MetricRecord:
    """CAGR in percent, over an explicitly supplied duration (§2A, §4).

    The duration is an operand, not an inference: assuming the span from two
    period labels has gone wrong often enough that an explicit ``years`` is
    the only honest input.
    """
    value = cagr(begin_value, end_value, years)
    return metric(
        "cagr", value, unit="percent", formula_id="cagr",
        operands={"begin": begin_value, "end": end_value, "years": years},
        period_end=period_end,
        reason="" if value is not None else "non-positive endpoint or duration",
    )


@dataclass(frozen=True)
class MultipleCheck:
    """Whether a multiple a report stated agrees with price and denominator.

    Carries the record so the audit shows the computed value next to the
    claimed one, and ``blocks`` says plainly whether a decision may proceed.
    """

    record: MetricRecord
    claimed: Decimal | None
    computed: Decimal | None
    difference: Decimal | None

    @property
    def blocks(self) -> bool:
        """A contradicted multiple is not a warning; it blocks (§11)."""
        return self.record.calculation_status in (
            CalculationStatus.MISMATCH,
            CalculationStatus.REFUSED,
        )

    def summary(self) -> dict:
        payload = self.record.summary()
        payload["verified"] = not self.blocks
        return payload


def check_stated_multiple(name: str, claimed: Any, numerator: Any,
                          denominator: Any, *, formula_id: str,
                          tolerance: Decimal = MULTIPLE_TOLERANCE,
                          period_end: str | None = None,
                          affected_decisions: tuple[str, ...] = ()) -> MultipleCheck:
    """Compare a multiple the report asserted against the computed one.

    This is the §5/§6 regression check, generalized: the report says
    "P/B 1.35x" while price 570.89 and BVPS 385.70 give 1.4801, a 9.64%
    difference. Beyond ``tolerance`` the record is ``MISMATCH`` and the
    audit keeps both numbers, so the report can say the claim was wrong
    rather than silently correct it.

    A claim with nothing to check against is ``UNSUPPORTED``, not verified:
    an unverifiable assertion must not authorize an order (§9).
    """
    claimed_d = as_decimal(claimed)
    computed = safe_ratio(numerator, denominator)
    if computed is None:
        return MultipleCheck(
            record=metric(
                name, None, unit="multiple", formula_id=formula_id,
                operands={"numerator": numerator, "denominator": denominator},
                period_end=period_end, llm_claimed_value=claimed_d,
                calculation_status=CalculationStatus.UNSUPPORTED,
                reason=("the claim cannot be checked: numerator or denominator "
                        "is unavailable"),
                affected_decisions=affected_decisions,
            ),
            claimed=claimed_d, computed=None, difference=None,
        )
    difference = None if claimed_d is None else computed - claimed_d
    within = (difference is not None and abs(difference) <= tolerance)
    return MultipleCheck(
        record=metric(
            name, computed, unit="multiple", formula_id=formula_id,
            operands={"numerator": numerator, "denominator": denominator},
            period_end=period_end, llm_claimed_value=claimed_d,
            tolerance=tolerance,
            calculation_status=(CalculationStatus.VERIFIED if within
                                else CalculationStatus.MISMATCH),
            reason=("" if within else
                    f"the stated {claimed_d} contradicts the computed "
                    f"{quantize(computed, RATIO_QUANTUM)} "
                    f"(difference {quantize(difference, RATIO_QUANTUM) if difference is not None else 'n/a'}, "
                    f"tolerance {tolerance})"),
            affected_decisions=affected_decisions,
        ),
        claimed=claimed_d, computed=computed, difference=difference,
    )


def dual_class_book_value_per_share(equity: Any, shares_class_a: Any,
                                    shares_class_b: Any, *,
                                    class_a_to_b_ratio: Any = 1500,
                                    period_end: str | None = None) -> MetricRecord:
    """BVPS for a two-class company, in Class-B-equivalent shares (§5).

    ``B_equivalent = shares_B + shares_A * ratio`` and
    ``BVPS_B = equity / B_equivalent``.

    The ratio is a required, verified input — 1:1500 is Berkshire's charter
    term, not a constant that applies to other issuers, so it is a parameter
    with a stated default rather than a hardcoded assumption. Comparing a
    Class-B price against a book value built on a raw share count is the
    DEF-006 hazard: it is wrong by roughly the conversion factor.
    """
    ratio = as_decimal(class_a_to_b_ratio)
    shares_a, shares_b = as_decimal(shares_class_a), as_decimal(shares_class_b)
    equity_base = convert_unit(equity, Unit.BASE, Unit.BASE)
    if ratio is None or ratio <= 0 or shares_a is None or shares_b is None \
            or equity_base is None:
        return metric(
            "book_value_per_share_B", None, unit="base_per_share",
            formula_id="equity_div_class_b_equivalent_shares",
            operands={"equity": equity, "shares_a": shares_class_a,
                      "shares_b": shares_class_b, "ratio": class_a_to_b_ratio},
            period_end=period_end,
            reason="equity, both share counts or the conversion ratio unavailable",
        )
    b_equivalent = shares_b + shares_a * ratio
    value = divide(equity_base, b_equivalent)
    return metric(
        "book_value_per_share_B", value, unit="base_per_share",
        formula_id="equity_div_class_b_equivalent_shares",
        operands={"equity": equity, "shares_a": shares_class_a,
                  "shares_b": shares_class_b, "ratio": class_a_to_b_ratio,
                  "class_b_equivalent": str(b_equivalent)},
        period_end=period_end,
        reason="" if value is not None else "class-B equivalent share count is zero",
    )
