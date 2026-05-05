from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingagents_service.api.app import create_app
from tradingagents_service.api.dependencies import get_shadow_run_repository
from tradingagents_service.db.models import EvaluationRunStatus
from tradingagents_service.evaluations import build_shadow_run_evaluation_input, compute_shadow_run_evaluation


def _run_obj(run_id):
    return type(
        "Run",
        (),
        {
            "id": run_id,
            "status": type("S", (), {"value": "succeeded"})(),
            "ticker": "MSFT",
            "trade_date": date(2026, 4, 29),
            "selected_analysts": ["news"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "provider": "ollama",
            "model": "llama3.2:latest",
            "error_message": None,
            "metadata_json": {"target_profile": {"investor_type": "growth", "horizon": "12m"}},
        },
    )()


def _output_obj():
    return type(
        "Output",
        (),
        {
            "final_rating": "Buy",
            "decision_markdown": "Buy MSFT without source citations.",
            "state_log_dir": "output/logs/MSFT/TradingAgentsStrategy_logs",
            "memory_log_path": "output/memory/trading_memory.md",
            "provider_metadata": {
                "quality": {
                    "status": "failed",
                    "findings": [
                        {
                            "code": "missing_source_object_citation",
                            "severity": "error",
                            "message": "Structured source objects were produced, but no IDs were cited.",
                        },
                        {
                            "code": "pre_synthesis_scope_contamination",
                            "severity": "error",
                            "message": "News report mentions Marvell.",
                            "evidence": "marvell (MRVL)",
                        },
                    ],
                    "source_summary": {
                        "valid_source_ids": ["SRC-NEWS-1", "RAW-TOOL-0001"],
                        "cited_source_ids": [],
                        "raw_tool_output_ids": ["RAW-TOOL-0001"],
                        "pre_synthesis_scope_audit": {"status": "failed"},
                    },
                    "recommendation_audit": {
                        "rating_vs_scorecard": "divergent",
                        "scorecard_suggested_rating": "Hold",
                        "scorecard_suggested_direction": "bearish",
                        "target_profile_status": "not_addressed",
                    },
                }
            },
        },
    )()


@pytest.mark.unit
def test_compute_shadow_run_evaluation_flags_insufficient_evidence():
    run_id = uuid4()
    payload = build_shadow_run_evaluation_input(run=_run_obj(run_id), output=_output_obj(), artifacts=[])
    result = compute_shadow_run_evaluation(
        evaluation_input=payload,
        evaluator_type="system",
        evaluator_model="heuristic-v1",
    )

    assert result.result_json["label"] == "insufficient_evidence"
    assert result.result_json["needs_human_review"] is True
    assert result.annotation is not None
    assert result.annotation.severity == "high"
    scores = {score.dimension: score for score in result.scores}
    assert scores["ticker_scope"].score == 0
    assert scores["evidence_traceability"].pass_fail is False
    assert "claim_traceability" in scores
    assert result.input_json["target_profile"]["investor_type"] == "growth"
    assert result.result_json["dimensions"][3]["evidence"]["target_profile_status"] == "not_addressed"
    assert "pre_synthesis_scope_contamination" in result.result_json["unsupported_claim_markers"]


@pytest.mark.unit
def test_compute_shadow_run_evaluation_treats_missing_claim_graph_as_insufficient_evidence():
    payload = {
        "target_type": "shadow_run",
        "shadow_run": {
            "run_id": str(uuid4()),
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "selected_analysts": ["market"],
            "status": "succeeded",
            "provider": "ollama",
            "model": "llama3.2:latest",
            "target_profile": {},
        },
        "decision": {
            "final_rating": "Hold",
            "decision_markdown": "Rating: Hold. Market momentum is mixed [SRC-MARKET-1].",
            "state_log_dir": "output/logs/NVDA/TradingAgentsStrategy_logs",
            "memory_log_path": "output/memory/trading_memory.md",
        },
        "quality": {
            "status": "failed",
            "findings": [
                {
                    "code": "missing_claim_graph_evidence",
                    "severity": "error",
                    "message": "Evidence was produced, but no claim graph evidence was extracted for synthesis.",
                }
            ],
            "source_summary": {
                "valid_source_ids": ["SRC-MARKET-1"],
                "cited_source_ids": ["SRC-MARKET-1"],
                "raw_tool_output_ids": [],
                "claim_count": 0,
                "claim_source_ids": [],
                "claim_backed_factor_count": 0,
            },
            "recommendation_audit": {
                "scorecard_reconciliation": {
                    "status": "aligned",
                    "requires_reconciliation": False,
                    "reconciled": True,
                }
            },
        },
        "target_profile": {},
        "artifacts": [],
    }

    result = compute_shadow_run_evaluation(evaluation_input=payload)

    assert result.result_json["label"] == "insufficient_evidence"
    assert result.result_json["needs_human_review"] is True
    assert "missing_claim_graph_evidence" in result.result_json["unsupported_claim_markers"]
    scores = {score.dimension: score for score in result.scores}
    assert scores["claim_traceability"].score == 10.0
    assert scores["claim_traceability"].pass_fail is False


class _EvalStubRepo:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.eval_id = uuid4()
        self.rubric_id = uuid4()
        self.score_id = uuid4()
        self.annotation_id = uuid4()
        self.created_kwargs = None

    async def get_run_by_id(self, run_id):
        return _run_obj(self.run_id) if run_id == self.run_id else None

    async def get_output_by_run_id(self, run_id):
        return _output_obj() if run_id == self.run_id else None

    async def get_artifacts_by_run_id(self, run_id):
        return []

    async def ensure_evaluation_rubric(self, **kwargs):
        return type(
            "Rubric",
            (),
            {
                "id": self.rubric_id,
                "name": kwargs["name"],
                "version": kwargs["version"],
                "scope_type": kwargs["scope_type"],
                "status": kwargs["status"],
                "description": kwargs["description"],
                "definition_json": kwargs["definition_json"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )()

    async def get_evaluation_rubric_by_id(self, rubric_id):
        return None

    async def list_evaluation_rubrics(self, *, status=None):
        return []

    async def create_completed_evaluation_run(self, **kwargs):
        self.created_kwargs = kwargs
        return type(
            "EvaluationRun",
            (),
            {
                "id": self.eval_id,
                "evaluation_rubric_id": self.rubric_id,
                "target_type": "shadow_run",
                "target_id": self.run_id,
                "shadow_run_id": self.run_id,
                "evaluator_type": kwargs["evaluator_type"],
                "evaluator_model": kwargs["evaluator_model"],
                "status": EvaluationRunStatus.SUCCEEDED,
                "trace_id": kwargs["trace_id"],
                "input_json": kwargs["input_json"],
                "result_json": kwargs["result_json"],
                "error": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )()

    async def get_evaluation_scores(self, evaluation_run_id):
        return [
            type(
                "Score",
                (),
                {
                    "id": self.score_id,
                    "dimension": "decision_readiness",
                    "score": 20.0,
                    "confidence": 0.82,
                    "pass_fail": False,
                    "basis": "heuristic",
                    "rationale": "Overall gate.",
                    "evidence_json": {"quality_status": "failed"},
                    "created_at": datetime.now(timezone.utc),
                },
            )()
        ]

    async def get_annotations_for_target(self, *, target_type, target_id):
        return [
            type(
                "Annotation",
                (),
                {
                    "id": self.annotation_id,
                    "label": "insufficient_evidence",
                    "severity": "high",
                    "basis": "derived",
                    "annotator_actor_type": "system",
                    "annotator_actor_id": "evaluation-queue",
                    "annotator_role": "evaluator",
                    "notes": "Shadow run lacks enough cited, in-scope evidence for reliable judgement.",
                    "evidence_json": {"quality_status": "failed"},
                    "created_at": datetime.now(timezone.utc),
                },
            )()
        ]

    async def list_evaluation_runs(self, **kwargs):
        return []


@pytest.mark.unit
def test_create_shadow_run_evaluation_endpoint():
    app = create_app()
    stub = _EvalStubRepo()

    async def _repo_override():
        yield stub

    app.dependency_overrides[get_shadow_run_repository] = _repo_override
    with TestClient(app) as client:
        resp = client.post(
            f"/v1/evaluations/shadow-runs/{stub.run_id}",
            json={"evaluator_type": "system", "evaluator_model": "heuristic-v1"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["shadow_run_id"] == str(stub.run_id)
    assert body["result"]["label"] == "insufficient_evidence"
    assert body["scores"][0]["dimension"] == "decision_readiness"
    assert body["annotations"][0]["label"] == "insufficient_evidence"
    assert stub.created_kwargs["evaluator_model"] == "heuristic-v1"
