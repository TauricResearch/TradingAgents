"""Pure validation for frozen global-event collection coverage."""

from __future__ import annotations

import math

from tradingagents.dataflows.media_store import validate_coverage_report
from tradingagents.global_research import FORMAL_GLOBALNEWS_QUERY_SLOTS
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL

_CORE_KEYS = frozenset({
    "complete", "sources", "missing_source_groups", "query_slots",
    "missing_query_slots", "cutoff_utc",
})
_DECORATION_KEYS = frozenset({
    "collector_interval_seconds",
    "cycle_start_grace_seconds",
    "cycle_lower_bound_utc",
})


def _finite_number(value: object, name: str) -> float:
    try:
        number = float(value) if not isinstance(value, bool) else math.nan
    except (OverflowError, TypeError, ValueError):
        number = math.nan
    if not isinstance(value, (int, float)) or not math.isfinite(number):
        raise ValueError(f"global-event receipt {name} must be finite")
    return number


def validate_global_event_receipt_coverage(
    report: object, *, cutoff_utc: float
) -> None:
    """Require the exact receipt proof frozen by the global-event protocol."""
    if not isinstance(report, dict) or set(report) != _CORE_KEYS | _DECORATION_KEYS:
        raise ValueError("global-event receipt coverage is not canonical")
    cutoff = _finite_number(cutoff_utc, "cutoff")
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    cycle = evidence["query_cycle"]
    interval = int(cycle["collector_interval_seconds"])
    grace = int(cycle["cycle_start_grace_seconds"])
    lower_bound = cutoff - interval - grace
    stored_lower_bound = _finite_number(
        report["cycle_lower_bound_utc"], "cycle lower bound"
    )
    if (
        type(report["collector_interval_seconds"]) is not int
        or report["collector_interval_seconds"] != interval
        or type(report["cycle_start_grace_seconds"]) is not int
        or report["cycle_start_grace_seconds"] != grace
        or stored_lower_bound != lower_bound
    ):
        raise ValueError("global-event receipt coverage policy differs from protocol")
    slots = [("globalnews", query_key) for query_key in FORMAL_GLOBALNEWS_QUERY_SLOTS]
    validate_coverage_report(
        {key: report[key] for key in _CORE_KEYS},
        cutoff,
        evidence["required_source_groups"],
        max_age_seconds=float(interval + grace),
        expected_query_slots=slots,
        require_lineage_query_slots=slots,
        min_started_utc=lower_bound,
    )
