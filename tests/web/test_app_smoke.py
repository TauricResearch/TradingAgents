import pytest
from fastapi.testclient import TestClient

from web.app import DEFAULT_CONFIG, app
from web.models import AnalysisRequest
from web.run_state import run_state
from web.run_state import RunState
from web.models import StreamEvent
from web.streaming import (
    _StreamAccumulator,
    _emit_research_team_events,
    _emit_risk_team_events,
    sse,
)


def test_index_returns_ok():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200


def test_clear_checkpoints_returns_deleted_count(monkeypatch):
    def fake_clear_all_checkpoints(data_cache_dir):
        return 3

    monkeypatch.setattr("web.app.clear_all_checkpoints", fake_clear_all_checkpoints)
    client = TestClient(app)

    response = client.post("/api/checkpoints/clear")

    assert response.status_code == 200
    assert response.json() == {"cleared": 3}


def test_saved_reports_lists_state_logs(tmp_path, monkeypatch):
    report_dir = tmp_path / "NVDA" / "TradingAgentsStrategy_logs"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "full_states_log_2026-01-15.json"
    report_file.write_text('{"company_of_interest":"NVDA"}', encoding="utf-8")
    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    client = TestClient(app)

    response = client.get("/api/reports")

    assert response.status_code == 200
    assert response.json()["reports"] == [
        {
            "path": "NVDA/TradingAgentsStrategy_logs/full_states_log_2026-01-15.json",
            "ticker": "NVDA",
            "analysis_date": "2026-01-15",
            "modified": report_file.stat().st_mtime_ns,
        }
    ]


def test_load_saved_report_returns_json(tmp_path, monkeypatch):
    report_dir = tmp_path / "NVDA" / "TradingAgentsStrategy_logs"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "full_states_log_2026-01-15.json"
    report_file.write_text('{"company_of_interest":"NVDA","trade_date":"2026-01-15"}', encoding="utf-8")
    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    client = TestClient(app)

    response = client.get(
        "/api/reports/load",
        params={"path": "NVDA/TradingAgentsStrategy_logs/full_states_log_2026-01-15.json"},
    )

    assert response.status_code == 200
    assert response.json()["company_of_interest"] == "NVDA"


def test_load_saved_report_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    client = TestClient(app)

    response = client.get("/api/reports/load", params={"path": "../secret.json"})

    assert response.status_code == 404


def _analysis_payload() -> dict:
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-01-15",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_think_llm": "gpt-5.4-mini",
        "deep_think_llm": "gpt-5.4",
    }


def test_analyze_streams_success_and_releases_run_state(monkeypatch):
    def fake_stream_analysis(request: AnalysisRequest, run_id: str):
        yield f'data: {{"type":"run_started","payload":{{"run_id":"{run_id}"}}}}\n\n'
        yield f'data: {{"type":"run_completed","payload":{{"run_id":"{run_id}"}}}}\n\n'

    monkeypatch.setattr("web.app.stream_analysis", fake_stream_analysis)
    client = TestClient(app)

    response = client.post("/api/analyze", json=_analysis_payload())

    assert response.status_code == 200
    assert "run_started" in response.text
    assert "run_completed" in response.text
    assert run_state.active_run_id is None


def test_analyze_streams_failure_and_releases_run_state(monkeypatch):
    def fake_stream_analysis(request: AnalysisRequest, run_id: str):
        raise RuntimeError("provider failed")
        yield ""

    monkeypatch.setattr("web.app.stream_analysis", fake_stream_analysis)
    client = TestClient(app)

    response = client.post("/api/analyze", json=_analysis_payload())

    assert response.status_code == 200
    assert "run_failed" in response.text
    assert "provider failed" in response.text
    assert run_state.active_run_id is None


def test_analyze_rejects_when_run_active():
    active_id = run_state.start()
    client = TestClient(app)
    try:
        response = client.post("/api/analyze", json=_analysis_payload())
    finally:
        run_state.finish(active_id)

    assert response.status_code == 409
    assert "Another analysis run is already active" in response.text


def test_run_state_allows_only_one_active_run():
    state = RunState()
    run_id = state.start()

    with pytest.raises(RuntimeError):
        state.start()

    state.finish(run_id)
    assert state.start()


def test_sse_serializes_non_finite_floats_as_null():
    output = sse(StreamEvent(type="stats", payload={"nan": float("nan")}))

    assert '"nan": null' in output


def test_accumulator_dedupes_messages_without_ids():
    message = type("MessageWithoutId", (), {"id": None, "content": "Continue"})()
    accumulator = _StreamAccumulator(["market"])

    assert accumulator.new_message_start_index([message]) == 0
    assert accumulator.new_message_start_index([message]) == 1


def test_accumulator_allows_same_no_id_content_at_different_positions():
    message_type = type("MessageWithoutId", (), {"id": None, "content": "Continue"})
    accumulator = _StreamAccumulator(["market"])

    assert accumulator.new_message_start_index([message_type()]) == 0
    assert accumulator.new_message_start_index([message_type(), message_type()]) == 1


def test_accumulator_allows_same_no_id_content_after_reset():
    message_type = type("MessageWithoutId", (), {"id": None, "content": "Continue"})
    other_type = type("OtherMessageWithoutId", (), {"id": None, "content": "Other"})
    accumulator = _StreamAccumulator(["market"])

    assert accumulator.new_message_start_index([message_type()]) == 0
    assert accumulator.new_message_start_index([other_type()]) == 0
    assert accumulator.new_message_start_index([message_type()]) == 0


def test_accumulator_dedupes_overlapping_no_id_batches():
    first_type = type("FirstMessageWithoutId", (), {"id": None, "content": "A"})
    second_type = type("SecondMessageWithoutId", (), {"id": None, "content": "B"})
    third_type = type("ThirdMessageWithoutId", (), {"id": None, "content": "C"})
    accumulator = _StreamAccumulator(["market"])

    assert accumulator.new_message_start_index([first_type(), second_type()]) == 0
    assert accumulator.new_message_start_index([second_type(), third_type()]) == 1


def test_research_report_section_is_accumulated():
    accumulator = _StreamAccumulator(["market"])

    _emit_research_team_events(
        accumulator,
        {
            "bull_history": "Bull case",
            "bear_history": "Bear case",
            "judge_decision": "Manager decision",
        },
    )

    report = accumulator.report_sections["investment_plan"]
    assert "Bull case" in report
    assert "Bear case" in report
    assert "Manager decision" in report


def test_risk_report_section_is_accumulated():
    accumulator = _StreamAccumulator(["market"])

    _emit_risk_team_events(
        accumulator,
        {
            "aggressive_history": "Aggressive case",
            "conservative_history": "Conservative case",
            "neutral_history": "Neutral case",
            "judge_decision": "Portfolio decision",
        },
    )

    report = accumulator.report_sections["final_trade_decision"]
    assert "Aggressive case" in report
    assert "Conservative case" in report
    assert "Neutral case" in report
    assert "Portfolio decision" in report
