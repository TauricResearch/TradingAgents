import asyncio

from agent_os.backend.routes import runs as runs_route


def _scan_result(node_id: str, message: str) -> dict:
    return {
        "id": f"{node_id}-result",
        "node_id": node_id,
        "type": "result",
        "agent": node_id.upper(),
        "identifier": "MARKET",
        "message": message,
        "response": message,
    }


def _scan_tool(parent_node_id: str) -> dict:
    return {
        "id": f"{parent_node_id}-tool",
        "node_id": f"tool_{parent_node_id}",
        "parent_node_id": parent_node_id,
        "type": "tool",
        "agent": parent_node_id.upper(),
        "identifier": "MARKET",
        "message": "tool running",
    }


def test_build_scan_rerun_state_ignores_placeholder_results_before_tool_completion():
    events = [
        _scan_result("sector_scanner", "Let me gather the sector data first."),
        _scan_tool("sector_scanner"),
        _scan_result("market_movers_scanner", "# Market report"),
        _scan_result("gatekeeper_scanner", "# Gatekeeper report"),
        _scan_result("geopolitical_scanner", "# Geopolitical report"),
    ]

    state = runs_route._build_scan_rerun_state(events)

    assert state["sector_performance_report"] == ""
    assert state["market_movers_report"] == "# Market report"
    assert state["gatekeeper_universe_report"] == "# Gatekeeper report"
    assert state["geopolitical_report"] == "# Geopolitical report"


def test_infer_scan_resume_node_picks_sector_when_other_phase_one_branches_finished():
    events = [
        _scan_result("sector_scanner", "Let me gather the sector data first."),
        _scan_tool("sector_scanner"),
        _scan_result("market_movers_scanner", "# Market report"),
        _scan_result("gatekeeper_scanner", "# Gatekeeper report"),
        _scan_result("geopolitical_scanner", "# Geopolitical report"),
    ]

    assert runs_route._infer_scan_resume_node(events) == "sector_scanner"


def test_stop_run_cancels_task(monkeypatch):
    run_id = "run-stop"

    class _Task:
        def __init__(self) -> None:
            self.cancel_called = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancel_called = True

    task = _Task()
    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31"},
        "events": [],
        "rerun_seq": 0,
    }
    runs_route.run_tasks[run_id] = task

    try:
        result = asyncio.run(runs_route.stop_run(run_id, user={"user_id": "u"}))
    finally:
        runs_route.runs.pop(run_id, None)
        runs_route.run_tasks.pop(run_id, None)

    assert result == {"run_id": run_id, "status": "stopping", "stopped": True}
    assert task.cancel_called is True


def test_stop_run_does_not_corrupt_completed_run_when_task_disappears():
    run_id = "run-stop-race"

    class _TaskMap(dict):
        def get(self, key, default=None):
            if key == run_id:
                runs_route.runs[run_id]["status"] = "completed"
            return super().get(key, default)

    original_run_tasks = runs_route.run_tasks
    runs_route.run_tasks = _TaskMap()
    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31"},
        "events": [],
        "rerun_seq": 0,
    }

    try:
        result = asyncio.run(runs_route.stop_run(run_id, user={"user_id": "u"}))
    finally:
        runs_route.runs.pop(run_id, None)
        runs_route.run_tasks = original_run_tasks

    assert result == {"run_id": run_id, "status": "completed", "stopped": False}


def test_resume_run_auto_reuses_same_run_id(monkeypatch):
    run_id = "run-resume"
    captured: dict[str, object] = {}

    async def _gen():
        if False:
            yield {}

    def _fake_set_run_task(target_run_id: str, coro) -> None:
        captured["run_id"] = target_run_id
        coro.close()

    monkeypatch.setattr(runs_route, "_set_run_task", _fake_set_run_task)
    monkeypatch.setattr(runs_route, "_append_system_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(runs_route.engine, "run_auto", lambda rid, params: _gen())

    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "failed",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31", "portfolio_id": "p1"},
        "events": [],
        "rerun_seq": 0,
    }

    try:
        result = asyncio.run(
            runs_route.resume_run(run_id, background_tasks=None, user={"user_id": "u"})
        )
    finally:
        runs_route.runs.pop(run_id, None)

    assert result["run_id"] == run_id
    assert result["mode"] == "same_run"
    assert captured["run_id"] == run_id


def test_resume_run_pipeline_uses_checkpoint_phase(monkeypatch):
    run_id = "run-pipeline-resume"
    captured: dict[str, object] = {}

    async def _gen():
        if False:
            yield {}

    def _fake_set_run_task(target_run_id: str, coro) -> None:
        captured["run_id"] = target_run_id
        coro.close()

    def _fake_run_pipeline(execution_run_id: str, params: dict):
        captured["execution_run_id"] = execution_run_id
        captured["params"] = params
        return _gen()

    monkeypatch.setattr(runs_route, "_set_run_task", _fake_set_run_task)
    monkeypatch.setattr(runs_route, "_append_system_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runs_route,
        "_infer_pipeline_resume_phase",
        lambda run_id, params: ("analysts", "Market Analyst"),
    )
    monkeypatch.setattr(runs_route.engine, "run_pipeline", _fake_run_pipeline)

    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "pipeline",
        "status": "failed",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31", "ticker": "AAPL"},
        "events": [],
        "rerun_seq": 0,
    }

    try:
        result = asyncio.run(
            runs_route.resume_run(run_id, background_tasks=None, user={"user_id": "u"})
        )
    finally:
        runs_route.runs.pop(run_id, None)

    assert result == {
        "run_id": run_id,
        "status": "queued",
        "mode": "pipeline_checkpoint",
        "phase": "analysts",
    }
    assert captured["run_id"] == run_id
    assert captured["execution_run_id"] == f"{run_id}:resume:pipeline"
    assert captured["params"]["resume_from_latest_snapshot"] is True


def test_infer_pipeline_resume_phase_unexpected_error_falls_back(monkeypatch):
    def _raise_unexpected(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(runs_route, "create_report_store", _raise_unexpected)
    phase, node_name = runs_route._infer_pipeline_resume_phase(
        "run-pipeline-resume",
        {"ticker": "AAPL", "date": "2026-03-31"},
    )

    assert phase is None
    assert node_name is None


def test_submit_phase3_decision_retries_selected_tickers(monkeypatch):
    run_id = "run-phase3"
    captured: dict[str, object] = {}

    async def _gen():
        if False:
            yield {}

    def _fake_set_run_task(target_run_id: str, coro) -> None:
        captured["run_id"] = target_run_id
        coro.close()

    def _fake_run_auto_phase3_decision(
        execution_run_id: str, params: dict, retry_tickers: list[str], pending_decision: dict
    ):
        captured["execution_run_id"] = execution_run_id
        captured["params"] = params
        captured["retry_tickers"] = retry_tickers
        captured["pending_decision"] = pending_decision
        return _gen()

    monkeypatch.setattr(runs_route, "_set_run_task", _fake_set_run_task)
    monkeypatch.setattr(runs_route, "_append_system_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runs_route.engine, "run_auto_phase3_decision", _fake_run_auto_phase3_decision
    )

    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "awaiting_decision",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31", "portfolio_id": "p1"},
        "events": [],
        "rerun_seq": 0,
        "pending_phase3_decision": {
            "date": "2026-03-31",
            "portfolio_id": "p1",
            "incomplete_tickers": [
                {"ticker": "NVDA", "reason": "missing", "portfolio_context": "candidate"},
                {"ticker": "MSFT", "reason": "missing", "portfolio_context": "holding"},
            ],
        },
    }

    try:
        result = asyncio.run(
            runs_route.submit_phase3_decision(
                run_id,
                params={"retry_tickers": [" nvda ", "MSFT", "nvda"]},
                user={"user_id": "u"},
            )
        )
    finally:
        runs_route.runs.pop(run_id, None)

    assert result == {
        "run_id": run_id,
        "status": "queued",
        "retry_tickers": ["NVDA", "MSFT"],
    }
    assert runs_route.runs.get(run_id) is None
    assert captured["run_id"] == run_id
    assert captured["execution_run_id"] == f"{run_id}:phase3-decision"
    assert captured["retry_tickers"] == ["NVDA", "MSFT"]
    assert captured["params"] == {"date": "2026-03-31", "portfolio_id": "p1", "run_id": run_id}


def test_submit_phase3_decision_rejects_non_waiting_run():
    run_id = "run-not-waiting"
    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31", "portfolio_id": "p1"},
        "events": [],
        "rerun_seq": 0,
    }

    try:
        try:
            asyncio.run(
                runs_route.submit_phase3_decision(
                    run_id,
                    params={"retry_tickers": ["NVDA"]},
                    user={"user_id": "u"},
                )
            )
        except Exception as exc:
            assert exc.status_code == 409
            assert exc.detail == "Run is not waiting for a Phase 3 decision"
        else:
            raise AssertionError("Expected submit_phase3_decision to reject non-waiting runs")
    finally:
        runs_route.runs.pop(run_id, None)
