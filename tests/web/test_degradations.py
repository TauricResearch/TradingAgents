from tradingagents.observability.events import PersistedEvent, RunEventDraft
from tradingagents.web.degradations import summarize_data_degradations


def _event(sequence: int, event_type: str, **extra):
    payload = {
        "turn_id": "turn-1",
        "graph_task_id": "task-1",
        "vendor_call_id": f"vendor-call-{sequence}",
        "method": "get_stock_data",
        "vendor": "yfinance",
        "stage": "vendor",
        "data_status": "failed",
        **extra,
    }
    if event_type != "data.progress":
        payload.setdefault("duration_ms", 5)
    return PersistedEvent.from_draft(RunEventDraft("run-1", event_type, payload), sequence)


def test_degradation_marks_a_recovered_fallback_without_exposing_error_text():
    events = [
        _event(1, "data.failed", failure_code="network_unreachable"),
        _event(
            2,
            "data.completed",
            vendor="alpha_vantage",
            data_status="success",
        ),
    ]

    assert summarize_data_degradations(events) == [
        {
            "capability": "price_history",
            "status": "degraded",
            "attempted_vendors": ["yfinance", "alpha_vantage"],
            "selected_vendors": ["alpha_vantage"],
            "reasons": [{"vendor": "yfinance", "code": "network_unreachable"}],
            "affected_sections": ["独立分析", "交易计划", "组合经理裁决"],
        }
    ]


def test_degradation_marks_all_failed_attempts_as_unavailable():
    events = [
        _event(1, "data.failed", failure_code="not_configured"),
        _event(
            2,
            "data.failed",
            vendor="alpha_vantage",
            failure_code="network_unreachable",
        ),
    ]

    summary = summarize_data_degradations(events)

    assert summary[0]["status"] == "unavailable"
    assert summary[0]["selected_vendors"] == []
    assert summary[0]["reasons"] == [
        {"vendor": "yfinance", "code": "not_configured"},
        {"vendor": "alpha_vantage", "code": "network_unreachable"},
    ]
