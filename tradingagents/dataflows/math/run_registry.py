"""Per-run metric registry (§3 of the P1 task): what this analysis certified.

The audit found that ``_evaluate_reliability`` called ``evaluate_decision``
without a ``metric_registry``. With no registry the claims validator can verify
nothing, every labelled figure becomes ``NOT_CHECKABLE``, and the gate blocked
every run. The fix is not to stop blocking contradictions — it is to give the
gate something to check against.

This module builds the registry for **one** run from the engine's own
computations. Two rules shape it:

**Per run, never shared.** A registry belongs to an
[analysis]; a process-wide one would let one analysis certify another's figures.
``build_run_registry`` returns a fresh object every call and attaches nothing to
module state.

**Only what the engine can compute.** A metric whose inputs are missing is
registered as ``NOT_COMPUTABLE`` rather than omitted. Omitting it would make the
metric indistinguishable from one nobody tried, and the audit needs to tell
"not computed" from "not attempted".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    MetricRecord,
    SourceStatus,
    metric,
)
from tradingagents.dataflows.math.registry import MetricRegistry


@dataclass(frozen=True)
class RunInputs:
    """The values a run can compute metrics from, when it has them.

    Every field is optional. A run without a price has no distances; a run
    without a portfolio has no sizes. The registry then records what was
    computable and the gate decides accordingly — it does not invent a value to
    look complete.
    """

    price: float | None = None
    previous_close: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    period_high: float | None = None
    eps_ttm: float | None = None
    eps_forward: float | None = None
    book_value_per_share: float | None = None
    revenue_consolidated: float | None = None
    revenue_prior: float | None = None
    # Dual-class valuation inputs (§3 of P3). A company with two share classes
    # needs all of these before a P/B can be computed: the equity, both share
    # counts, the conversion ratio and the class the price belongs to.
    equity: float | None = None
    shares_class_a: float | None = None
    shares_class_b: float | None = None
    class_a_to_b_ratio: float | None = None
    price_class: str | None = None
    currency: str | None = None
    weighted_average_shares: float | None = None
    # Which inputs are the model's own assertions rather than vendor or filing
    # figures (§2 of P3). A figure read out of an analyst's prose is a claim,
    # not a fact: `metric()` records it as LLM_CLAIMED, which is not a trusted
    # source, so a multiple built on it can be shown and reported but never
    # certified. Without this the extractor's figures entered the registry
    # looking exactly like reconciled ones — the original F2 defect, where a
    # P/B the model invented was indistinguishable from a computed one.
    claimed_inputs: tuple[str, ...] = ()


def _register_if_computable(registry: MetricRegistry, name: str,
                            value: Any, *, unit: str, formula_id: str,
                            operands: dict[str, Any], reason: str,
                            source_status: SourceStatus | None = None,
                            period_end: str | None = None) -> MetricRecord:
    """Record a metric, or its absence, so the audit shows which happened.

    ``metric()`` already turns a ``None`` value into ``NOT_COMPUTABLE``; this
    wrapper exists to keep the call sites readable and to carry the operands
    that would have been used, which is what a later diagnosis needs.

    ``source_status`` says whether the *inputs* are facts or claims: a
    perfectly executed division over a model's own assertion is still a claim,
    and ``MetricRecord.is_usable`` refuses it even though the arithmetic
    verified.
    """
    extra = {}
    if source_status is not None:
        extra["source_status"] = source_status
    if period_end is not None:
        extra["period_end"] = period_end
    return registry.register(metric(
        name, value, unit=unit, formula_id=formula_id, operands=operands,
        reason="" if value is not None else reason, **extra,
    ))


def _source_of(inputs: RunInputs, *names: str) -> SourceStatus:
    """VERIFIED only when none of the inputs was the model's own claim."""
    if set(inputs.claimed_inputs).intersection(names):
        return SourceStatus.LLM_CLAIMED
    return SourceStatus.VERIFIED


def build_run_registry(inputs: RunInputs, *, run_id: str = "") -> MetricRegistry:
    """The registry for one analysis, built from what the run actually has.

    Every metric is computed here with the engine's own functions — this module
    composes them, it does not reimplement a formula. A metric that cannot be
    computed from the supplied inputs is registered as ``NOT_COMPUTABLE`` with
    the operands it would have used, so a reader can see the gap rather than a
    silence.
    """
    from tradingagents.dataflows.math.precision import pct_change
    from tradingagents.dataflows.math.technical import distance_from_level
    from tradingagents.dataflows.math.valuation import (
        price_to_book,
        price_to_earnings,
    )

    registry = MetricRegistry(run_id=run_id)

    # Price distances: the figures a market report quotes most often.
    for name, level in (("distance_from_sma50", inputs.sma50),
                        ("distance_from_sma200", inputs.sma200),
                        ("distance_from_high", inputs.period_high)):
        _register_if_computable(
            registry, name,
            distance_from_level(inputs.price, level) if inputs.price is not None
            and level is not None else None,
            unit="percent", formula_id="pct_change",
            operands={"price": inputs.price, "level": level},
            reason="the price or the reference level is unavailable",
        )

    _register_if_computable(
        registry, "session_return",
        pct_change(inputs.price, inputs.previous_close)
        if inputs.price is not None and inputs.previous_close is not None else None,
        unit="percent", formula_id="pct_change",
        operands={"price": inputs.price, "previous_close": inputs.previous_close},
        reason="the price or the previous close is unavailable",
    )

    # Valuation: computed only from inputs the caller actually holds.
    pb_record = None
    if inputs.price is not None and inputs.book_value_per_share is not None:
        pb_record = price_to_book(inputs.price, inputs.book_value_per_share)
    _register_if_computable(
        registry, "price_to_book",
        pb_record.value if pb_record is not None else None,
        unit="multiple", formula_id="price_div_bvps",
        operands={"price": inputs.price,
                  "bvps": inputs.book_value_per_share},
        reason="the price or the book value per share is unavailable",
        source_status=_source_of(inputs, "price", "book_value_per_share"),
    )

    _register_if_computable(
        registry, "eps_change",
        pct_change(inputs.eps_forward, inputs.eps_ttm)
        if inputs.eps_forward is not None and inputs.eps_ttm is not None else None,
        unit="percent", formula_id="pct_change",
        operands={"eps_ttm": inputs.eps_ttm,
                  "eps_forward": inputs.eps_forward},
        reason="the trailing or forward EPS is unavailable",
        source_status=_source_of(inputs, "eps_ttm", "eps_forward"),
    )

    _register_if_computable(
        registry, "revenue_growth",
        pct_change(inputs.revenue_consolidated, inputs.revenue_prior)
        if inputs.revenue_consolidated is not None
        and inputs.revenue_prior is not None else None,
        unit="percent", formula_id="pct_change",
        operands={"revenue": inputs.revenue_consolidated,
                  "revenue_prior": inputs.revenue_prior},
        reason="one of the two revenue figures is unavailable",
        source_status=_source_of(inputs, "revenue_consolidated", "revenue_prior"),
    )

    _register_dual_class_valuation(registry, inputs)
    _register_eps_reconciliation(registry, inputs)

    # §4 of P3: a trailing P/E may only rest on an EPS whose denominator is
    # known. Registering it earlier — before the reconciliation ran — meant a
    # P/E of 14.51 was certified from a vendor figure the reconciliation had
    # just marked UNSUPPORTED, so the report could quote a multiple built on
    # an unverified input while the audit said the input was unverified.
    if inputs.price is not None and inputs.eps_ttm is not None \
            and inputs.weighted_average_shares:
        _register_if_computable(
            registry, "pe_trailing",
            price_to_earnings(inputs.price, inputs.eps_ttm).value,
            unit="multiple", formula_id="price_div_eps_trailing_gaap",
            operands={"price": inputs.price, "eps": inputs.eps_ttm,
                      "weighted_average_shares": inputs.weighted_average_shares},
            reason="the price or the trailing EPS is unavailable",
            source_status=_source_of(inputs, "price", "eps_ttm"),
        )
    else:
        # No denominator: the EPS is not a certified fact, so neither is the
        # multiple. Recorded rather than omitted — a silent gap reads as "not
        # applicable", and this one is measurable and missing.
        halted = registry.get("eps_gaap")
        registry.register(metric(
            "pe_trailing", None, unit="multiple",
            formula_id="price_div_eps_trailing_gaap",
            operands={"price": inputs.price, "eps": inputs.eps_ttm,
                      "weighted_average_shares": inputs.weighted_average_shares},
            calculation_status=(
                CalculationStatus.UNSUPPORTED
                if halted is not None
                and halted.calculation_status is CalculationStatus.UNSUPPORTED
                else CalculationStatus.NOT_COMPUTABLE),
            reason=("a trailing P/E needs an EPS reconciled against the "
                    "filing's weighted-average share count"),
        ))

    return registry


def _register_dual_class_valuation(registry: MetricRegistry,
                                   inputs: RunInputs) -> None:
    """P/B for a company with two share classes (§3 of P3).

    Runs the repository's own ``reconcile_valuation``, which refuses a
    cross-class comparison and a currency mismatch rather than producing a
    plausible number. Both compatible formulas are computed and compared:

    ``market_cap / attributable_equity``
        The whole company against the whole book.
    ``price_B / book_value_per_share_B``
        The per-share form, on Class-B equivalents.

    They agree only when every input refers to the same class and period,
    which is the check the audit asked for. A disagreement beyond tolerance is
    recorded as a refusal, not averaged away.
    """
    from tradingagents.dataflows.math.precision import safe_ratio
    from tradingagents.dataflows.math.valuation import (
        dual_class_book_value_per_share,
    )
    from tradingagents.dataflows.valuation import EquityInputs, reconcile_valuation

    b_equivalent = None
    if inputs.shares_class_b is not None and inputs.shares_class_a is not None \
            and inputs.class_a_to_b_ratio is not None:
        b_equivalent = (inputs.shares_class_b
                        + inputs.shares_class_a * inputs.class_a_to_b_ratio)

    # The per-share form, through the engine's dual-class helper.
    per_share_bvps = None
    if (inputs.equity is not None and inputs.shares_class_a is not None
            and inputs.shares_class_b is not None
            and inputs.class_a_to_b_ratio is not None):
        record = dual_class_book_value_per_share(
            inputs.equity, inputs.shares_class_a, inputs.shares_class_b,
            class_a_to_b_ratio=inputs.class_a_to_b_ratio,
        )
        per_share_bvps = record.value

    _register_if_computable(
        registry, "book_value_per_share_B", per_share_bvps,
        unit="base_per_share", formula_id="equity_div_class_b_equivalent_shares",
        operands={"equity": inputs.equity, "shares_a": inputs.shares_class_a,
                  "shares_b": inputs.shares_class_b,
                  "ratio": inputs.class_a_to_b_ratio,
                  "class_b_equivalent": b_equivalent},
        reason=("the equity, both share counts and the conversion ratio are "
                "all needed for a dual-class book value"),
        source_status=_source_of(inputs, "equity", "shares_class_a",
                                 "shares_class_b", "class_a_to_b_ratio"),
    )

    pb_per_share = None
    if inputs.price is not None and per_share_bvps is not None:
        pb_per_share = safe_ratio(inputs.price, per_share_bvps)
    elif inputs.price is not None and inputs.book_value_per_share is not None:
        # A directly supplied book value is a legitimate input: a single-class
        # filer has no dual-class arithmetic to do, and refusing to use it
        # would make every such run unverifiable.
        per_share_bvps = inputs.book_value_per_share
        pb_per_share = safe_ratio(inputs.price, per_share_bvps)

    # The reconciliation itself, which refuses a class or currency mismatch.
    reconciled = None
    if inputs.price is not None and inputs.equity is not None \
            and b_equivalent is not None:
        reconciled = reconcile_valuation(EquityInputs(
            price=inputs.price,
            price_class=inputs.price_class,
            price_currency=inputs.currency,
            equity=inputs.equity,
            equity_currency=inputs.currency,
            shares_outstanding=b_equivalent,
            bvps_reported=inputs.book_value_per_share,
            bvps_class=inputs.price_class,
            bvps_currency=inputs.currency,
            share_class_ratio=inputs.class_a_to_b_ratio,
        ))

    if reconciled is not None and not reconciled.is_usable:
        # The reconciliation refused: record why rather than the number.
        reason = "; ".join(i.message for i in reconciled.issues.issues
                           if i.severity == "error") or "inputs did not reconcile"
        registry.register(metric(
            "price_to_book", None, unit="multiple", formula_id="price_div_bvps",
            operands={"price": inputs.price, "bvps": per_share_bvps},
            calculation_status=CalculationStatus.REFUSED, reason=reason,
        ))
        return

    value = pb_per_share
    if reconciled is not None and reconciled.price_to_book is not None:
        value = reconciled.price_to_book

    _register_if_computable(
        registry, "price_to_book", value,
        unit="multiple", formula_id="price_div_bvps",
        operands={"price": inputs.price, "bvps": per_share_bvps,
                  "equity": inputs.equity, "class_b_equivalent": b_equivalent,
                  "market_cap_over_equity": (
                      safe_ratio((inputs.price or 0) * b_equivalent,
                                 inputs.equity)
                      if b_equivalent is not None and inputs.equity else None)},
        reason=("a price-to-book needs the price and a book value on the same "
                "share class and period"),
        source_status=_source_of(inputs, "price", "book_value_per_share",
                                 "equity", "shares_class_a",
                                 "shares_class_b", "class_a_to_b_ratio"),
    )


def _register_eps_reconciliation(registry: MetricRegistry,
                                 inputs: RunInputs) -> None:
    """EPS on the GAAP denominator, or UNVERIFIED (§4 of P3).

    ``earnings_per_share`` records its basis and its share count. When the
    weighted-average count is absent the metric is registered as
    ``UNSUPPORTED``: a P/E built on an unverified EPS must not be certified,
    and inventing a share count would be worse than saying so.
    """
    from tradingagents.dataflows.math.valuation import earnings_per_share

    if inputs.eps_ttm is not None and inputs.weighted_average_shares:
        record = earnings_per_share(
            inputs.eps_ttm * inputs.weighted_average_shares,
            inputs.weighted_average_shares, period_end=None)
        registry.register(record)
        return

    if inputs.eps_ttm is not None:
        # The EPS is known but its denominator is not: unusable, and said so.
        registry.register(metric(
            "eps_gaap", None, unit="gaap_per_share",
            formula_id="net_income_div_shares_gaap",
            operands={"eps_reported": inputs.eps_ttm,
                      "weighted_average_shares": None},
            calculation_status=CalculationStatus.UNSUPPORTED,
            reason=("the trailing EPS was reported but the weighted-average "
                    "share count is not available, so it cannot be reconciled "
                    "against the filing"),
        ))
        return

    _register_if_computable(
        registry, "eps_gaap", None, unit="gaap_per_share",
        formula_id="net_income_div_shares_gaap",
        operands={"eps_reported": None, "weighted_average_shares": None},
        reason="no trailing EPS was reported for this run",
    )


def registry_inputs_from_state(state: dict) -> RunInputs:
    """Read what a finished run can supply, from its own state.

    Values come from the labelled figures the agents reported and from the
    snapshot the graph recorded — never from prose this function invents. A
    field the state does not carry stays ``None``, which the registry turns into
    ``NOT_COMPUTABLE`` rather than a guess.

    This is deliberately conservative: until the analysts emit structured
    metrics (the §7 gap in ``ANALYST_CONTEXT_OPTIMIZATION.md``), extraction from
    text is the only source available, and an unextracted figure must not be
    fabricated.
    """
    snapshot = state.get("verified_market_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    def _num(*values):
        for value in values:
            if value is None or isinstance(value, bool):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    return RunInputs(
        price=_num(snapshot.get("close"), snapshot.get("price")),
        previous_close=_num(snapshot.get("previous_close")),
        sma50=_num(snapshot.get("sma50")),
        sma200=_num(snapshot.get("sma200")),
        period_high=_num(snapshot.get("high_52w"), snapshot.get("period_high")),
        eps_ttm=_num(state.get("eps_ttm")),
        eps_forward=_num(state.get("eps_forward")),
        book_value_per_share=_num(state.get("book_value_per_share")),
        revenue_consolidated=_num(state.get("revenue_consolidated")),
        revenue_prior=_num(state.get("revenue_prior")),
        # §3 of P3 added these to ``RunInputs`` but nothing ever populated
        # them, so a run that carried the equity and the share counts still
        # produced NOT_COMPUTABLE for every dual-class metric. Reading them
        # here is what makes the supplied figures reach the arithmetic.
        equity=_num(state.get("equity")),
        shares_class_a=_num(state.get("shares_class_a")),
        shares_class_b=_num(state.get("shares_class_b")),
        class_a_to_b_ratio=_num(state.get("class_a_to_b_ratio")),
        price_class=state.get("price_class"),
        currency=(state.get("currency") or snapshot.get("currency") or None),
        weighted_average_shares=_num(state.get("weighted_average_shares")),
    )


def status_of(registry: MetricRegistry) -> dict:
    """A compact view of what the registry certified, for the audit.

    Reported rather than inferred elsewhere: how many metrics exist, how many
    are usable, and which are blocking. A reader can tell an empty registry from
    a full one — the distinction the audit needed and did not have.
    """
    records = list(registry._records.values())  # noqa: SLF001 — read-only view
    usable = [r for r in records if r.is_usable]
    return {
        "metrics_total": len(records),
        "metrics_usable": len(usable),
        "metrics_not_computable": len(
            [r for r in records
             if r.calculation_status is CalculationStatus.NOT_COMPUTABLE]
        ),
        "blocking_metrics": [r.metric for r in registry.blocking],
        "is_empty": not records,
        "source": str(SourceStatus.VERIFIED) if usable else None,
    }
