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


def _register_if_computable(registry: MetricRegistry, name: str,
                            value: Any, *, unit: str, formula_id: str,
                            operands: dict[str, Any], reason: str) -> MetricRecord:
    """Record a metric, or its absence, so the audit shows which happened.

    ``metric()`` already turns a ``None`` value into ``NOT_COMPUTABLE``; this
    wrapper exists to keep the call sites readable and to carry the operands
    that would have been used, which is what a later diagnosis needs.
    """
    return registry.register(metric(
        name, value, unit=unit, formula_id=formula_id, operands=operands,
        reason="" if value is not None else reason,
    ))


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
    )

    _register_if_computable(
        registry, "pe_trailing",
        (price_to_earnings(inputs.price, inputs.eps_ttm).value
         if inputs.price is not None and inputs.eps_ttm is not None else None),
        unit="multiple", formula_id="price_div_eps_trailing_gaap",
        operands={"price": inputs.price, "eps": inputs.eps_ttm},
        reason="the price or the trailing EPS is unavailable",
    )

    _register_if_computable(
        registry, "eps_change",
        pct_change(inputs.eps_forward, inputs.eps_ttm)
        if inputs.eps_forward is not None and inputs.eps_ttm is not None else None,
        unit="percent", formula_id="pct_change",
        operands={"eps_ttm": inputs.eps_ttm,
                  "eps_forward": inputs.eps_forward},
        reason="the trailing or forward EPS is unavailable",
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
    )

    return registry


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
