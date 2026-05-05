from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tradingagents_service.recommendation_contract import build_recommendation_contract


REPORT_KEYS = ("market_report", "sentiment_report", "news_report", "fundamentals_report")


def load_state_from_artifacts(artifacts: list[Any], *, trade_date: date | str | None = None) -> dict[str, Any]:
    candidates = _state_log_artifacts_for_date(artifacts, trade_date=trade_date)
    if not candidates:
        candidates = _state_log_artifacts_for_date(artifacts, trade_date=None)
    for artifact in candidates:
        path = _artifact_path(getattr(artifact, "path", ""))
        if path is None or not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _state_log_artifacts_for_date(artifacts: list[Any], *, trade_date: date | str | None) -> list[Any]:
    state_logs = [artifact for artifact in artifacts if getattr(artifact, "artifact_type", None) == "state_log"]
    if trade_date is None:
        return state_logs
    date_text = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)
    expected_name = f"full_states_log_{date_text}.json"
    matches = []
    for artifact in state_logs:
        path = _artifact_path(getattr(artifact, "path", ""))
        if path is not None and path.name == expected_name:
            matches.append(artifact)
    return matches


def build_shadow_run_trace(
    *,
    run: Any,
    output: Any | None,
    events: list[Any],
    artifacts: list[Any],
    state: dict[str, Any] | None = None,
    evaluations: list[Any] | None = None,
) -> dict[str, Any]:
    state = state or {}
    provider_metadata = output.provider_metadata if output is not None and output.provider_metadata else {}
    quality = provider_metadata.get("quality") or {}
    precedent_summary = provider_metadata.get("precedent_summary") if isinstance(provider_metadata.get("precedent_summary"), dict) else {}
    recommendation_contract = {}
    if output is not None:
        recommendation_contract = quality.get("recommendation_contract") if isinstance(quality, dict) else {}
        if not isinstance(recommendation_contract, dict):
            recommendation_contract = build_recommendation_contract(
                final_rating=output.final_rating,
                decision_markdown=output.decision_markdown,
                quality=quality,
                telemetry_summary=provider_metadata.get("telemetry") if isinstance(provider_metadata.get("telemetry"), dict) else {},
            )
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    _add_node(
        nodes,
        "request",
        "Run Request",
        "input",
        _status(run.status),
        f"{run.ticker} {run.trade_date.isoformat()} via {', '.join(run.selected_analysts or [])}",
        {
            "ticker": run.ticker,
            "trade_date": run.trade_date.isoformat(),
            "selected_analysts": run.selected_analysts or [],
            "provider": run.provider,
            "model": run.model,
        },
        {"event_count": len(events)},
    )

    raw_tool_outputs = state.get("raw_tool_outputs") if isinstance(state.get("raw_tool_outputs"), list) else []
    raw_source_ids = [
        item.get("source_id")
        for item in raw_tool_outputs
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    ]
    _add_node(
        nodes,
        "raw-tools",
        "Raw Tool Evidence",
        "tooling",
        "captured" if raw_tool_outputs else "empty",
        f"{len(raw_tool_outputs)} raw tool outputs captured",
        {
            "raw_tool_outputs": [
                {
                    "source_id": item.get("source_id"),
                    "tool_name": item.get("tool_name"),
                    "analyst": item.get("analyst"),
                    "bytes": item.get("bytes"),
                    "output_sha256": item.get("output_sha256"),
                    "content": item.get("content") or item.get("output"),
                }
                for item in raw_tool_outputs
                if isinstance(item, dict)
            ]
        },
        {"raw_tool_count": len(raw_tool_outputs), "source_id_count": len(raw_source_ids)},
    )

    telemetry_artifacts = [
        artifact
        for artifact in artifacts
        if getattr(artifact, "artifact_type", None) == "run_telemetry"
        or getattr(artifact, "artifact_type", None) == "run_telemetry_manifest"
    ]
    telemetry_summary = state.get("run_telemetry") if isinstance(state.get("run_telemetry"), dict) else {}
    if telemetry_artifacts or telemetry_summary:
        telemetry_payload = {
            "telemetry_summary": telemetry_summary,
            "telemetry_artifacts": [
                {
                    "artifact_id": str(artifact.id),
                    "kind": artifact.artifact_type,
                    "path": artifact.path,
                    "metadata": artifact.metadata_json or {},
                }
                for artifact in telemetry_artifacts
            ],
        }
        _add_node(
            nodes,
            "telemetry",
            "Run Telemetry",
            "audit",
            "captured" if telemetry_artifacts or telemetry_summary else "empty",
            f"{len(telemetry_artifacts)} telemetry artifact(s)",
            telemetry_payload,
            {
                "telemetry_artifact_count": len(telemetry_artifacts),
                "llm_call_count": telemetry_summary.get("llm_call_count", 0),
                "tool_call_count": telemetry_summary.get("tool_call_count", 0),
                "token_total": telemetry_summary.get("token_total", 0),
            },
        )

    if precedent_summary:
        _add_node(
            nodes,
            "precedents",
            "Cross-Run Precedents",
            "retrieval",
            "available",
            f"{precedent_summary.get('precedent_count', 0)} precedent(s)",
            {"precedent_summary": precedent_summary},
            {"precedent_count": precedent_summary.get("precedent_count", 0)},
        )

    report_payload = {
        key: {
            "present": bool(state.get(key)),
            "chars": len(state.get(key) or ""),
            "content": state.get(key) or "",
        }
        for key in REPORT_KEYS
    }
    present_reports = [key for key, value in report_payload.items() if value["present"]]
    _add_node(
        nodes,
        "analyst-reports",
        "Analyst Reports",
        "agent",
        "generated" if present_reports else "empty",
        f"{len(present_reports)} report(s): {', '.join(present_reports) or 'none'}",
        report_payload,
        {f"{key}_chars": value["chars"] for key, value in report_payload.items()},
    )

    investment_debate = state.get("investment_debate_state") if isinstance(state.get("investment_debate_state"), dict) else {}
    _add_node(
        nodes,
        "research",
        "Research Debate And Manager",
        "agent",
        "generated" if state.get("investment_plan") else "empty",
        f"investment_plan chars={len(state.get('investment_plan') or '')}",
        {
            "investment_debate_state": investment_debate,
            "investment_plan": state.get("investment_plan") or "",
        },
        {
            "bull_chars": len(investment_debate.get("bull_history") or ""),
            "bear_chars": len(investment_debate.get("bear_history") or ""),
            "plan_chars": len(state.get("investment_plan") or ""),
        },
    )

    _add_node(
        nodes,
        "trader",
        "Trader Proposal",
        "agent",
        "generated" if state.get("trader_investment_decision") else "empty",
        f"trader_decision chars={len(state.get('trader_investment_decision') or '')}",
        {"trader_investment_decision": state.get("trader_investment_decision") or ""},
        {"decision_chars": len(state.get("trader_investment_decision") or "")},
    )

    risk_debate = state.get("risk_debate_state") if isinstance(state.get("risk_debate_state"), dict) else {}
    _add_node(
        nodes,
        "risk",
        "Risk Debate",
        "agent",
        "generated" if risk_debate else "empty",
        f"risk histories chars={sum(len(str(risk_debate.get(k) or '')) for k in ('aggressive_history', 'conservative_history', 'neutral_history'))}",
        {"risk_debate_state": risk_debate},
        {
            "aggressive_chars": len(risk_debate.get("aggressive_history") or ""),
            "conservative_chars": len(risk_debate.get("conservative_history") or ""),
            "neutral_chars": len(risk_debate.get("neutral_history") or ""),
        },
    )

    _add_node(
        nodes,
        "pm-audit",
        "PM Audit Inputs",
        "audit",
        "available" if quality or state.get("source_objects") else "empty",
        f"{len(state.get('source_objects') or [])} source objects; quality={quality.get('status', 'unknown')}",
        {
            "source_objects": state.get("source_objects") or [],
            "source_registry": state.get("source_registry") or {},
            "claim_graph": state.get("claim_graph") or {},
            "skill_registry": state.get("skill_registry") or {},
            "recommendation_scorecard": state.get("recommendation_scorecard") or {},
            "pre_synthesis_scope_audit": state.get("pre_synthesis_scope_audit") or {},
            "quality_source_summary": quality.get("source_summary") or {},
            "quality_recommendation_audit": quality.get("recommendation_audit") or {},
        },
        {
            "source_object_count": len(state.get("source_objects") or []),
            "claim_count": len((state.get("claim_graph") or {}).get("claim_objects") or []),
            "quality_finding_count": len(quality.get("findings") or []),
        },
    )

    _add_node(
        nodes,
        "portfolio-manager",
        "Portfolio Manager Decision",
        "agent",
        "invalid" if recommendation_contract.get("invalidated_by_quality_gate") else "generated" if output is not None and output.decision_markdown else "empty",
        f"final_rating={recommendation_contract.get('final_rating') if output is not None else '-'}",
        {
            "final_rating": recommendation_contract.get("final_rating") if output is not None else None,
            "final_decision_markdown": recommendation_contract.get("decision_markdown") if output is not None else None,
            "recommendation_status": recommendation_contract.get("recommendation_status") if output is not None else None,
            "invalidated_by_quality_gate": bool(recommendation_contract.get("invalidated_by_quality_gate")),
            "original_final_rating": recommendation_contract.get("original_final_rating") if output is not None else None,
            "state_log_dir": output.state_log_dir if output is not None else None,
            "memory_log_path": output.memory_log_path if output is not None else None,
        },
        {"decision_chars": len(recommendation_contract.get("decision_markdown") or "") if output is not None else 0},
    )

    _add_node(
        nodes,
        "quality",
        "Quality Gate",
        "audit",
        quality.get("status") or "not_assessed",
        f"{len(quality.get('findings') or [])} finding(s)",
        quality,
        {"finding_count": len(quality.get("findings") or [])},
    )

    _add_node(
        nodes,
        "artifacts",
        "Artifact Store",
        "storage",
        "available" if artifacts else "empty",
        f"{len(artifacts)} artifact(s)",
        {
            "artifacts": [
                {
                    "artifact_id": str(artifact.id),
                    "kind": artifact.artifact_type,
                    "path": artifact.path,
                    "metadata": artifact.metadata_json or {},
                }
                for artifact in artifacts
            ]
        },
        {"artifact_count": len(artifacts)},
    )

    latest_eval = evaluations[0] if evaluations else None
    eval_payload = latest_eval.result_json if latest_eval is not None else None
    _add_node(
        nodes,
        "evaluation",
        "Evaluation Judgement",
        "evaluation",
        eval_payload.get("label") if isinstance(eval_payload, dict) and eval_payload.get("label") else "not_run",
        _evaluation_summary(eval_payload),
        {
            "evaluation_run_id": str(latest_eval.id) if latest_eval is not None else None,
            "result": eval_payload,
        },
        {"overall_score": eval_payload.get("overall_score") if isinstance(eval_payload, dict) else None},
    )

    for source, target, label in (
        ("request", "raw-tools", "configures selected tools"),
        ("raw-tools", "telemetry", "tool and llm telemetry"),
        ("telemetry", "analyst-reports", "telemetry into report context"),
        ("precedents", "analyst-reports", "retrieved precedents into report context"),
        ("analyst-reports", "research", "reports into bull/bear debate"),
        ("research", "trader", "investment plan into trader action"),
        ("trader", "risk", "trader action into risk debate"),
        ("risk", "pm-audit", "risk state into audit builders"),
        ("pm-audit", "portfolio-manager", "source IDs, scorecard, scope audit"),
        ("portfolio-manager", "quality", "final decision assessed"),
        ("quality", "artifacts", "quality metadata stored with outputs"),
        ("artifacts", "evaluation", "artifact bundle judged"),
    ):
        edges.append({"from_node": source, "to_node": target, "label": label})

    return {
        "nodes": nodes,
        "edges": edges,
        "artifact_refs": [
            {
                "artifact_id": str(artifact.id),
                "kind": artifact.artifact_type,
                "path": artifact.path,
                "metadata": artifact.metadata_json or {},
            }
            for artifact in artifacts
        ],
        "precedent_summary": precedent_summary or {},
    }


def _add_node(
    nodes: list[dict[str, Any]],
    node_id: str,
    label: str,
    kind: str,
    status: str,
    summary: str,
    payload: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    nodes.append(
        {
            "node_id": node_id,
            "label": label,
            "kind": kind,
            "status": status,
            "summary": summary,
            "metrics": metrics,
            "payload": payload,
        }
    )


def _artifact_path(uri: str) -> Path | None:
    if not uri:
        return None
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        return Path(parsed.path)
    return Path(uri)


def _status(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _evaluation_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "No evaluation run yet"
    label = payload.get("label") or "-"
    overall = payload.get("overall_score")
    return f"label={label}; overall={overall if overall is not None else '-'}"
