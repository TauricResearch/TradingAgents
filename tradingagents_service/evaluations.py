from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradingagents_service.db.repository import AnnotationCreate, EvaluationScoreCreate

DEFAULT_RUBRIC_NAME = "shadow-run-frontier-readiness"
DEFAULT_RUBRIC_VERSION = "2026-05-01"


DEFAULT_RUBRIC_DEFINITION: dict[str, Any] = {
    "origin": "ported-from-tremor-evaluation-layer",
    "purpose": "Evaluate TradingAgents shadow-run outputs for evidence, verification, scoring, and judgement readiness.",
    "dimensions": [
        {
            "key": "evidence_traceability",
            "label": "Evidence traceability",
            "min_pass_score": 80,
            "checks": ["source object citations", "raw tool citations", "explicit source references"],
        },
        {
            "key": "ticker_scope",
            "label": "Ticker/entity scope",
            "min_pass_score": 90,
            "checks": ["requested ticker consistency", "out-of-scope issuer contamination"],
        },
        {
            "key": "scorecard_reconciliation",
            "label": "Scorecard reconciliation",
            "min_pass_score": 75,
            "checks": ["PM rating versus deterministic scorecard", "explicit reconciliation on divergence"],
        },
        {
            "key": "decision_readiness",
            "label": "Decision readiness",
            "min_pass_score": 80,
            "checks": ["quality status", "critical findings", "overall evidentiary posture"],
        },
    ],
    "labels": ["accept", "accept_with_notes", "needs_revision", "insufficient_evidence", "reject"],
    "frontier_model_contract": {
        "input": "shadow run decision, quality metadata, source summary, recommendation audit, artifact manifest",
        "output": "JSON scores, label, rationale, verification notes, unsupported_claim markers",
        "storage": "evaluation_runs.result_json and evaluation_scores.evidence_json",
    },
}


@dataclass(frozen=True)
class EvaluationComputation:
    input_json: dict[str, Any]
    result_json: dict[str, Any]
    scores: list[EvaluationScoreCreate]
    annotation: AnnotationCreate | None


def build_shadow_run_evaluation_input(*, run: Any, output: Any | None, artifacts: list[Any]) -> dict[str, Any]:
    provider_metadata = output.provider_metadata if output is not None and output.provider_metadata else {}
    quality = provider_metadata.get("quality") or {}
    target_profile = run.metadata_json.get("target_profile") if isinstance(getattr(run, "metadata_json", None), dict) else {}
    return {
        "target_type": "shadow_run",
        "shadow_run": {
            "run_id": str(run.id),
            "ticker": run.ticker,
            "trade_date": run.trade_date.isoformat(),
            "selected_analysts": list(run.selected_analysts or []),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "provider": run.provider,
            "model": run.model,
            "target_profile": target_profile if isinstance(target_profile, dict) else {},
        },
        "decision": {
            "final_rating": output.final_rating if output is not None else None,
            "decision_markdown": output.decision_markdown if output is not None else None,
            "state_log_dir": output.state_log_dir if output is not None else None,
            "memory_log_path": output.memory_log_path if output is not None else None,
        },
        "quality": quality,
        "target_profile": target_profile if isinstance(target_profile, dict) else {},
        "artifacts": [
            {
                "artifact_id": str(artifact.id),
                "kind": artifact.artifact_type,
                "path": artifact.path,
                "metadata": artifact.metadata_json or {},
            }
            for artifact in artifacts
        ],
    }


def compute_shadow_run_evaluation(
    *,
    evaluation_input: dict[str, Any],
    evaluator_type: str = "system",
    evaluator_model: str | None = None,
) -> EvaluationComputation:
    """Score a shadow run using Tremor-style evaluation semantics.

    The first implementation is deterministic and stores a frontier-ready
    contract. When an LLM judge is enabled, its result should fill the same
    dimensions and evidence fields rather than changing the schema.
    """
    quality = evaluation_input.get("quality") or {}
    target_profile = evaluation_input.get("target_profile") if isinstance(evaluation_input.get("target_profile"), dict) else {}
    findings = quality.get("findings") or []
    source_summary = quality.get("source_summary") or {}
    recommendation_audit = quality.get("recommendation_audit") or {}
    quality_status = quality.get("status")

    error_codes = {f.get("code") for f in findings if f.get("severity") == "error"}
    warning_codes = {f.get("code") for f in findings if f.get("severity") == "warning"}

    valid_source_ids = source_summary.get("valid_source_ids") or []
    cited_source_ids = source_summary.get("cited_source_ids") or []
    raw_tool_ids = source_summary.get("raw_tool_output_ids") or []
    cited_raw_ids = [source_id for source_id in cited_source_ids if source_id in set(raw_tool_ids)]

    evidence_score = 100.0
    if valid_source_ids and not cited_source_ids:
        evidence_score = 15.0
    elif raw_tool_ids and not cited_raw_ids:
        evidence_score = 45.0
    elif "no_explicit_source_reference" in warning_codes:
        evidence_score = 60.0

    scope_audit = source_summary.get("pre_synthesis_scope_audit") or {}
    ticker_scope_score = 100.0
    if "pre_synthesis_scope_contamination" in error_codes:
        ticker_scope_score = 0.0
    elif scope_audit.get("status") == "warning":
        ticker_scope_score = 70.0

    scorecard_reconciliation = recommendation_audit.get("scorecard_reconciliation")
    if not isinstance(scorecard_reconciliation, dict):
        scorecard_reconciliation = {
            "status": recommendation_audit.get("rating_vs_scorecard") or "unscored",
            "final_rating": recommendation_audit.get("final_rating"),
            "final_direction": recommendation_audit.get("directions", {}).get("portfolio_manager"),
            "scorecard_rating": recommendation_audit.get("scorecard_suggested_rating"),
            "scorecard_direction": recommendation_audit.get("scorecard_suggested_direction"),
            "explicit_reconciliation": False,
            "requires_reconciliation": recommendation_audit.get("rating_vs_scorecard") == "divergent",
            "reconciled": recommendation_audit.get("rating_vs_scorecard") != "divergent",
        }
    scorecard_alignment = scorecard_reconciliation.get("status")
    scorecard_score = 100.0
    if scorecard_alignment == "divergent":
        scorecard_score = 40.0
        if "scorecard_reconciliation_missing" in error_codes:
            scorecard_score = 0.0
    elif scorecard_alignment == "unscored":
        scorecard_score = 55.0

    target_profile_status = recommendation_audit.get("target_profile_status")
    target_profile_score = 100.0
    if target_profile and target_profile_status == "not_addressed":
        target_profile_score = 50.0
        if "target_profile_not_addressed" in warning_codes:
            target_profile_score = 35.0

    decision_readiness_score = min(evidence_score, ticker_scope_score, scorecard_score, target_profile_score)
    if quality_status == "failed":
        decision_readiness_score = min(decision_readiness_score, 20.0)
    elif quality_status == "warning":
        decision_readiness_score = min(decision_readiness_score, 70.0)

    score_rows = [
        _score(
            "evidence_traceability",
            evidence_score,
            "heuristic",
            "Checks whether final judgement cites available report and raw-tool source IDs.",
            {
                "valid_source_ids": valid_source_ids,
                "cited_source_ids": cited_source_ids,
                "raw_tool_output_ids": raw_tool_ids,
                "finding_codes": sorted(error_codes | warning_codes),
            },
        ),
        _score(
            "ticker_scope",
            ticker_scope_score,
            "heuristic",
            "Checks requested ticker/entity scope before final synthesis.",
            {"pre_synthesis_scope_audit": scope_audit},
        ),
        _score(
            "scorecard_reconciliation",
            scorecard_score,
            "heuristic",
            "Checks PM recommendation against deterministic scoring layer.",
            {
                "rating_vs_scorecard": scorecard_alignment,
                "scorecard_reconciliation": scorecard_reconciliation,
                "scorecard_suggested_rating": recommendation_audit.get("scorecard_suggested_rating"),
                "scorecard_suggested_direction": recommendation_audit.get("scorecard_suggested_direction"),
            },
        ),
        _score(
            "decision_readiness",
            decision_readiness_score,
            "heuristic",
            "Overall gate for Flint advisory ingestion and frontier-model review readiness.",
            {
                "quality_status": quality_status,
                "finding_codes": sorted(error_codes | warning_codes),
                "target_profile_status": target_profile_status,
                "target_profile": target_profile,
            },
        ),
    ]
    overall = round(sum(row.score for row in score_rows) / len(score_rows), 2)
    label = _label_for(overall=overall, error_codes=error_codes)
    severity = _severity_for(label)
    needs_human_review = label in {"needs_revision", "insufficient_evidence", "reject"}
    unsupported_claim_markers = sorted(
        code
        for code in error_codes | warning_codes
        if code
        in {
            "missing_source_object_citation",
            "missing_raw_tool_citation",
            "no_explicit_source_reference",
            "pre_synthesis_scope_contamination",
            "scorecard_reconciliation_missing",
            "target_profile_not_addressed",
        }
    )

    result_json = {
        "label": label,
        "overall_score": overall,
        "needs_human_review": needs_human_review,
        "basis": "heuristic",
        "evaluator_type": evaluator_type,
        "evaluator_model": evaluator_model,
        "summary": _summary_for(label),
        "unsupported_claim_markers": unsupported_claim_markers,
        "dimensions": [
            {
                "dimension": row.dimension,
                "score": row.score,
                "confidence": row.confidence,
                "pass_fail": row.pass_fail,
                "basis": row.basis,
                "rationale": row.rationale,
                "evidence": row.evidence_json,
            }
            for row in score_rows
        ],
        "frontier_model_ready": True,
        "frontier_contract_version": DEFAULT_RUBRIC_VERSION,
    }
    annotation = None
    if needs_human_review:
        annotation = AnnotationCreate(
            label=label,
            severity=severity,
            notes=result_json["summary"],
            evidence_json={
                "overall_score": overall,
                "unsupported_claim_markers": unsupported_claim_markers,
                "quality_status": quality_status,
            },
        )
    return EvaluationComputation(
        input_json=evaluation_input,
        result_json=result_json,
        scores=score_rows,
        annotation=annotation,
    )


def _score(
    dimension: str,
    score: float,
    basis: str,
    rationale: str,
    evidence_json: dict[str, Any],
) -> EvaluationScoreCreate:
    return EvaluationScoreCreate(
        dimension=dimension,
        score=round(score, 2),
        confidence=0.82,
        pass_fail=score >= 75,
        basis=basis,
        rationale=rationale,
        evidence_json=evidence_json,
    )


def _label_for(*, overall: float, error_codes: set[str]) -> str:
    if "pre_synthesis_scope_contamination" in error_codes:
        return "insufficient_evidence"
    if {"missing_source_object_citation", "missing_raw_tool_citation"} & error_codes:
        return "insufficient_evidence"
    if overall >= 90:
        return "accept"
    if overall >= 75:
        return "accept_with_notes"
    if overall >= 50:
        return "needs_revision"
    return "reject"


def _severity_for(label: str) -> str:
    if label == "reject":
        return "critical"
    if label == "insufficient_evidence":
        return "high"
    if label == "needs_revision":
        return "medium"
    return "low"


def _summary_for(label: str) -> str:
    if label == "accept":
        return "Shadow run passed evaluation gates and is ready for advisory review."
    if label == "accept_with_notes":
        return "Shadow run is usable with review notes; minor evidence or reconciliation gaps remain."
    if label == "needs_revision":
        return "Shadow run needs revision before Flint advisory ingestion."
    if label == "insufficient_evidence":
        return "Shadow run lacks enough cited, in-scope evidence for reliable judgement."
    return "Shadow run should be rejected for this advisory cycle."
