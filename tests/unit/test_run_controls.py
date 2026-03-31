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


def test_stop_run_sets_graceful_stop_without_cancelling_task(monkeypatch):
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
    assert task.cancel_called is False


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
        result = asyncio.run(runs_route.resume_run(run_id, background_tasks=None, user={"user_id": "u"}))
    finally:
        runs_route.runs.pop(run_id, None)

    assert result["run_id"] == run_id
    assert result["mode"] == "same_run"
    assert captured["run_id"] == run_id
