from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents_service.db.models import ShadowRunStatus
from tradingagents_service.recommendation_contract import build_recommendation_contract


REPORT_KEYS = ("market_report", "sentiment_report", "news_report", "fundamentals_report")


def _metadata(output: Any | None) -> dict[str, Any]:
    if output is None or not isinstance(output.provider_metadata, dict):
        return {}
    return output.provider_metadata


def _quality(output: Any | None) -> dict[str, Any]:
    metadata = _metadata(output)
    quality = metadata.get("quality")
    return quality if isinstance(quality, dict) else {}


def _contract(
    output: Any | None,
    quality: dict[str, Any],
    *,
    target_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _metadata(output)
    telemetry_summary = metadata.get("telemetry") if isinstance(metadata.get("telemetry"), dict) else {}
    if output is None:
        return build_recommendation_contract(
            final_rating=None,
            decision_markdown=None,
            quality=quality,
            telemetry_summary=telemetry_summary,
            target_profile=target_profile,
        )
    existing = quality.get("recommendation_contract")
    if isinstance(existing, dict):
        return existing
    return build_recommendation_contract(
        final_rating=output.final_rating,
        decision_markdown=output.decision_markdown,
        quality=quality,
        telemetry_summary=telemetry_summary,
        target_profile=target_profile,
    )


def _md_escape_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True, default=str) + "\n```"


def _text_block(value: Any) -> str:
    text = "" if value is None else str(value)
    return "```text\n" + text.strip() + "\n```"


def report_output_path(*, run: Any, output_root: Path = Path("output")) -> Path:
    return (
        output_root
        / "reports"
        / str(run.ticker)
        / run.trade_date.isoformat()
        / f"{run.id}.md"
    )


def build_shadow_run_markdown_report(
    *,
    run: Any,
    output: Any | None,
    events: list[Any],
    artifacts: list[Any],
    state: dict[str, Any] | None = None,
    evaluations: list[Any] | None = None,
) -> str:
    state = state or {}
    evaluations = evaluations or []
    metadata = _metadata(output)
    quality = _quality(output)
    target_profile = run.metadata_json.get("target_profile") if isinstance(getattr(run, "metadata_json", None), dict) else {}
    contract = _contract(output, quality, target_profile=target_profile if isinstance(target_profile, dict) else None)
    source_summary = quality.get("source_summary") if isinstance(quality.get("source_summary"), dict) else {}
    recommendation_audit = (
        quality.get("recommendation_audit") if isinstance(quality.get("recommendation_audit"), dict) else {}
    )
    scorecard = recommendation_audit.get("scorecard") if isinstance(recommendation_audit.get("scorecard"), dict) else {}
    telemetry_summary = metadata.get("telemetry") if isinstance(metadata.get("telemetry"), dict) else {}
    precedent_summary = metadata.get("precedent_summary") if isinstance(metadata.get("precedent_summary"), dict) else {}
    claim_graph = state.get("claim_graph") if isinstance(state.get("claim_graph"), dict) else {}
    source_registry = state.get("source_registry") if isinstance(state.get("source_registry"), dict) else {}
    skill_registry = state.get("skill_registry") if isinstance(state.get("skill_registry"), dict) else {}
    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        f"# TradingAgents Shadow Run Report: {run.ticker} {run.trade_date.isoformat()}",
        "",
        f"- Run ID: `{run.id}`",
        f"- Generated At: `{generated_at}`",
        f"- Run Status: `{run.status.value if isinstance(run.status, ShadowRunStatus) else run.status}`",
        f"- Recommendation Status: `{contract.get('recommendation_status')}`",
        f"- Final Rating: `{contract.get('final_rating')}`",
        f"- Original Final Rating: `{contract.get('original_final_rating')}`",
        f"- Quality Status: `{quality.get('status', 'not_assessed')}`",
        f"- Selected Analysts: `{', '.join(run.selected_analysts or [])}`",
        f"- Provider: `{metadata.get('provider') or run.provider or '-'}`",
        f"- Deep Model: `{metadata.get('deep_model') or '-'}`",
        f"- Quick Model: `{metadata.get('quick_model') or '-'}`",
        f"- Target Profile: `{json.dumps(target_profile, sort_keys=True, default=str) if target_profile else '-'}`",
        "",
        "## Executive Interpretation",
        "",
    ]

    if contract.get("invalidated_by_quality_gate"):
        lines.extend(
            [
                "This run completed operationally, but the recommendation is invalid for downstream use.",
                "The original model output is retained as forensic evidence only.",
                "",
            ]
        )
    else:
        lines.extend(["This run produced a recommendation that was not invalidated by the quality gate.", ""])

    lines.extend(
        [
            "## Quality Gate",
            "",
            "| Severity | Code | Message | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    findings = quality.get("findings") if isinstance(quality.get("findings"), list) else []
    if findings:
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_escape_cell(finding.get("severity")),
                        _md_escape_cell(finding.get("code")),
                        _md_escape_cell(finding.get("message")),
                        _md_escape_cell(finding.get("evidence")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | No quality findings. | - |")

    lines.extend(
        [
            "",
            "## Recommendation Audit",
            "",
            _json_block(recommendation_audit),
            "",
            "## Source Summary",
            "",
            _json_block(source_summary),
            "",
            "## Scorecard",
            "",
            _json_block(scorecard),
            "",
            "## Claim Graph",
            "",
            _json_block(claim_graph),
            "",
            "## Source Registry",
            "",
            _json_block(source_registry),
            "",
            "## Skill Registry",
            "",
            _json_block(skill_registry),
            "",
            "## Telemetry Summary",
            "",
            _json_block(telemetry_summary),
            "",
            "## Precedent Summary",
            "",
            _json_block(precedent_summary),
            "",
            "## Runtime Timeline",
            "",
            "| Seq | Timestamp | Event | Stage | Status | Worker | Details |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        detail = payload.get("error") or payload.get("decision") or payload.get("raw_tool_count") or payload.get("chars") or ""
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape_cell(event.sequence),
                    _md_escape_cell(event.created_at.isoformat() if hasattr(event.created_at, "isoformat") else event.created_at),
                    _md_escape_cell(event.event_type),
                    _md_escape_cell(payload.get("stage")),
                    _md_escape_cell(payload.get("status")),
                    _md_escape_cell(payload.get("worker_id")),
                    _md_escape_cell(detail),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Kind | URI | Bytes | SHA-256 | Content Type |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for artifact in artifacts:
        metadata_json = artifact.metadata_json or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape_cell(artifact.artifact_type),
                    _md_escape_cell(artifact.path),
                    _md_escape_cell(metadata_json.get("bytes")),
                    _md_escape_cell(metadata_json.get("sha256")),
                    _md_escape_cell(metadata_json.get("content_type")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Analyst Reports",
            "",
        ]
    )
    for key in REPORT_KEYS:
        lines.extend([f"### {key}", "", _text_block(state.get(key) or ""), ""])

    raw_tool_outputs = state.get("raw_tool_outputs") if isinstance(state.get("raw_tool_outputs"), list) else []
    lines.extend(["## Raw Tool Outputs", ""])
    if raw_tool_outputs:
        for item in raw_tool_outputs:
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"### {item.get('source_id', 'RAW-TOOL')} `{item.get('tool_name', 'unknown')}`",
                    "",
                    f"- Status: `{item.get('status', '-')}`",
                    f"- Analyst: `{item.get('analyst', '-')}`",
                    f"- SHA-256: `{item.get('output_sha256', '-')}`",
                    f"- Bytes: `{item.get('bytes', '-')}`",
                    "",
                    _text_block(item.get("content") or item.get("output") or ""),
                    "",
                ]
            )
    else:
        lines.extend(["No raw tool outputs captured.", ""])

    lines.extend(
        [
            "## Final Decision Markdown",
            "",
            contract.get("decision_markdown") or "",
            "",
            "## Evaluation",
            "",
        ]
    )
    if evaluations:
        for evaluation in evaluations:
            lines.extend(
                [
                    f"### Evaluation `{evaluation.id}`",
                    "",
                    _json_block(evaluation.result_json or {}),
                    "",
                ]
            )
    else:
        lines.extend(["No evaluation run recorded.", ""])

    return "\n".join(lines).rstrip() + "\n"


def save_shadow_run_markdown_report(*, markdown: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def list_generated_markdown_reports(*, output_root: Path = Path("output"), limit: int = 100) -> list[dict[str, Any]]:
    report_root = output_root / "reports"
    if not report_root.exists():
        return []

    reports: list[dict[str, Any]] = []
    for path in report_root.glob("*/*/*.md"):
        try:
            stat = path.stat()
        except OSError:
            continue
        relative = path.relative_to(output_root)
        parts = relative.parts
        if len(parts) != 4:
            continue
        _, ticker, trade_date, filename = parts
        run_id = filename.removesuffix(".md")
        reports.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "trade_date": trade_date,
                "path": str(output_root / relative),
                "report_url": f"/v1/shadow-runs/{run_id}/report.md",
                "bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    reports.sort(key=lambda item: item["updated_at"], reverse=True)
    return reports[:limit]
