from __future__ import annotations

from collections import Counter

TRACE_SCHEMA_VERSION = "tradingagents.profile_trace.v1alpha1"
TRACE_KIND = "tradingagents_stage_profile"


def build_trace_summary(node_timings: list[dict], phase_totals: dict[str, float]) -> dict:
    phase_totals_seconds = {key: round(value, 3) for key, value in phase_totals.items()}
    degraded_events = [entry for entry in node_timings if entry.get("research_status") not in (None, "full")]
    node_counter = Counter(node for entry in node_timings for node in entry.get("nodes", []))
    total_elapsed_ms = sum(int(entry.get("elapsed_ms", 0)) for entry in node_timings)
    return {
        "event_count": len(node_timings),
        "total_elapsed_ms": total_elapsed_ms,
        "phase_totals_seconds": phase_totals_seconds,
        "degraded_event_count": len(degraded_events),
        "final_research_status": node_timings[-1].get("research_status") if node_timings else None,
        "final_degraded_reason": node_timings[-1].get("degraded_reason") if node_timings else None,
        "unique_nodes": sorted(node_counter.keys()),
        "node_hit_count": dict(sorted(node_counter.items())),
    }
