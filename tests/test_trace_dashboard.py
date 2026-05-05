from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingagents_service.api.app import create_app
from tradingagents_service.api.dependencies import get_shadow_run_repository
from tradingagents_service.db.models import EvaluationRunStatus
from tradingagents_service.trace import build_shadow_run_trace, load_state_from_artifacts


def _run(run_id):
    return type(
        "Run",
        (),
        {
            "id": run_id,
            "ticker": "MSFT",
            "trade_date": date(2026, 4, 29),
            "selected_analysts": ["news"],
            "provider": "ollama",
            "model": "llama3.2:latest",
            "status": type("S", (), {"value": "succeeded"})(),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "error_message": None,
        },
    )()


def _output():
    return type(
        "Output",
        (),
        {
            "final_rating": "Buy",
            "decision_markdown": "Buy MSFT without citing RAW-TOOL-0001.",
            "state_log_dir": "output/logs/MSFT",
            "memory_log_path": "output/memory/trading_memory.md",
            "provider_metadata": {
                "quality": {
                    "status": "failed",
                    "findings": [{"code": "missing_raw_tool_citation", "severity": "error"}],
                    "source_summary": {"valid_source_ids": ["RAW-TOOL-0001"], "cited_source_ids": []},
                    "recommendation_audit": {"final_rating": "Buy"},
                }
            },
        },
    )()


def _artifact(path, kind="state_log"):
    return type(
        "Artifact",
        (),
        {
            "id": uuid4(),
            "artifact_type": kind,
            "path": f"file://{path}",
            "metadata_json": {"sha256": "abc", "bytes": 10, "content_type": "application/json"},
        },
    )()


@pytest.mark.unit
def test_trace_builder_projects_information_flow(tmp_path):
    run_id = uuid4()
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "news_report": "News report",
                "raw_tool_outputs": [
                    {
                        "source_id": "RAW-TOOL-0001",
                        "tool_name": "get_news",
                        "analyst": "news",
                        "bytes": 20,
                        "content": "raw news",
                    }
                ],
                "run_telemetry": {
                    "shadow_run_id": "run-1",
                    "llm_call_count": 1,
                    "tool_call_count": 1,
                    "token_total": 42,
                },
                "source_objects": [{"source_id": "SRC-NEWS-1"}],
                "investment_plan": "Buy plan",
                "trader_investment_decision": "Trader buy",
                "risk_debate_state": {"aggressive_history": "risk"},
            }
        ),
        encoding="utf-8",
    )
    artifacts = [_artifact(state_path)]
    state = load_state_from_artifacts(artifacts)
    trace = build_shadow_run_trace(
        run=_run(run_id),
        output=_output(),
        events=[],
        artifacts=artifacts,
        state=state,
        evaluations=[],
    )

    node_ids = [node["node_id"] for node in trace["nodes"]]
    assert node_ids == [
        "request",
        "raw-tools",
        "telemetry",
        "analyst-reports",
        "research",
        "trader",
        "risk",
        "pm-audit",
        "portfolio-manager",
        "quality",
        "artifacts",
        "evaluation",
    ]
    raw_node = next(node for node in trace["nodes"] if node["node_id"] == "raw-tools")
    assert raw_node["metrics"]["raw_tool_count"] == 1
    telemetry_node = next(node for node in trace["nodes"] if node["node_id"] == "telemetry")
    assert telemetry_node["metrics"]["token_total"] == 42
    quality_node = next(node for node in trace["nodes"] if node["node_id"] == "quality")
    assert quality_node["status"] == "failed"
    assert trace["edges"][0] == {
        "from_node": "request",
        "to_node": "raw-tools",
        "label": "configures selected tools",
    }
    assert trace["edges"][1] == {
        "from_node": "raw-tools",
        "to_node": "telemetry",
        "label": "tool and llm telemetry",
    }


@pytest.mark.unit
def test_load_state_from_artifacts_prefers_matching_trade_date(tmp_path):
    stale_path = tmp_path / "full_states_log_2026-05-05.json"
    current_path = tmp_path / "full_states_log_2026-05-04.json"
    stale_path.write_text(json.dumps({"news_report": "stale", "raw_tool_outputs": []}), encoding="utf-8")
    current_path.write_text(json.dumps({"news_report": "current", "raw_tool_outputs": []}), encoding="utf-8")
    artifacts = [_artifact(stale_path), _artifact(current_path)]

    state = load_state_from_artifacts(artifacts, trade_date=date(2026, 5, 4))

    assert state["news_report"] == "current"


class _TraceRepo:
    def __init__(self, state_path):
        self.run_id = uuid4()
        self.eval_id = uuid4()
        self.state_path = state_path

    async def get_run_by_id(self, run_id):
        return _run(self.run_id) if run_id == self.run_id else None

    async def get_events_by_run_id(self, run_id):
        return []

    async def get_artifacts_by_run_id(self, run_id):
        return [_artifact(self.state_path)]

    async def get_output_by_run_id(self, run_id):
        return _output()

    async def list_evaluation_runs(self, **kwargs):
        return [
            type(
                "EvaluationRun",
                (),
                {
                    "id": self.eval_id,
                    "status": EvaluationRunStatus.SUCCEEDED,
                    "result_json": {"label": "insufficient_evidence", "overall_score": 35},
                },
            )()
        ]


@pytest.mark.unit
def test_trace_endpoint_returns_nodes(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"news_report": "News", "raw_tool_outputs": []}), encoding="utf-8")
    app = create_app()
    stub = _TraceRepo(state_path)

    async def _repo_override():
        yield stub

    app.dependency_overrides[get_shadow_run_repository] = _repo_override
    with TestClient(app) as client:
        resp = client.get(f"/v1/shadow-runs/{stub.run_id}/trace")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == str(stub.run_id)
    assert [node["node_id"] for node in body["nodes"]][:3] == ["request", "raw-tools", "analyst-reports"]
    assert body["nodes"][-1]["status"] == "insufficient_evidence"
