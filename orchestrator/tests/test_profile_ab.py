from orchestrator.profile_ab import build_comparison
from orchestrator.profile_trace_utils import build_trace_summary


def test_build_trace_summary_counts_degraded_events():
    summary = build_trace_summary(
        [
            {"nodes": ["Market Analyst"], "elapsed_ms": 110, "research_status": None, "degraded_reason": None},
            {"nodes": ["Bull Researcher"], "elapsed_ms": 220, "research_status": "degraded", "degraded_reason": "bull_timeout"},
        ],
        {"analyst": 0.11, "research": 0.22},
    )

    assert summary["event_count"] == 2
    assert summary["total_elapsed_ms"] == 330
    assert summary["degraded_event_count"] == 1
    assert summary["final_research_status"] == "degraded"
    assert summary["node_hit_count"]["Bull Researcher"] == 1


def test_build_comparison_prefers_faster_less_degraded_cohort():
    traces_a = [
        {
            "status": "ok",
            "trace_schema_version": "tradingagents.profile_trace.v1alpha1",
            "_source_path": "/tmp/a.json",
            "variant_label": "compact",
            "summary": {
                "total_elapsed_ms": 450,
                "event_count": 4,
                "final_research_status": "full",
                "phase_totals_seconds": {"research": 0.22, "risk": 0.10},
            },
        }
    ]
    traces_b = [
        {
            "status": "ok",
            "trace_schema_version": "tradingagents.profile_trace.v1alpha1",
            "_source_path": "/tmp/b.json",
            "variant_label": "verbose",
            "summary": {
                "total_elapsed_ms": 700,
                "event_count": 5,
                "final_research_status": "degraded",
                "phase_totals_seconds": {"research": 0.45, "risk": 0.15},
            },
        }
    ]

    payload = build_comparison(traces_a, traces_b, label_a="A", label_b="B")

    assert payload["cohorts"]["A"]["median_total_elapsed_ms"] == 450
    assert payload["cohorts"]["A"]["trace_schema_versions"] == ["tradingagents.profile_trace.v1alpha1"]
    assert payload["cohorts"]["B"]["degraded_run_count"] == 1
    assert payload["comparison"]["faster_label"] == "A"
    assert payload["comparison"]["lower_error_rate_label"] is None
    assert payload["comparison"]["recommended_label"] == "A"
