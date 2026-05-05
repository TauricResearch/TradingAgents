from __future__ import annotations

import os
from uuid import uuid4
from pathlib import Path
from typing import Any, Callable

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents_service.artifacts import ArtifactStore, LocalArtifactBackend
from tradingagents_service.provenance import (
    RunTelemetryRecorder,
    ToolProvenanceRecorder,
    write_run_telemetry,
    write_tool_provenance,
)
from tradingagents_service.quality import assess_shadow_run_quality
from tradingagents_service.recommendation_contract import build_recommendation_contract

from .types import ShadowRunRequest, ShadowRunResult


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _build_config(request: ShadowRunRequest, output_root: Path) -> dict[str, Any]:
    if request.env_file is not None:
        _load_env_file(request.env_file)

    config = DEFAULT_CONFIG.copy()
    config["results_dir"] = str(output_root / "logs")
    config["data_cache_dir"] = str(output_root / "cache")
    config["memory_log_path"] = str(output_root / "memory" / "trading_memory.md")
    config["selected_analysts"] = list(request.selected_analysts)
    config["llm_provider"] = request.provider
    config["deep_think_llm"] = request.deep_model
    config["quick_think_llm"] = request.quick_model
    config["checkpoint_enabled"] = request.checkpoint_enabled
    config["max_debate_rounds"] = int(request.max_debate_rounds)
    config["max_risk_discuss_rounds"] = int(request.max_risk_rounds)
    return config


def _run_id_for_request(request: ShadowRunRequest) -> str:
    if request.shadow_run_id:
        return request.shadow_run_id
    return uuid4().hex


def _collect_artifacts(
    *,
    artifact_store: ArtifactStore,
    memory_log_path: Path,
    state_log_dir: Path,
    trade_date: str,
    provenance_dir: Path | None = None,
    telemetry_dir: Path | None = None,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if memory_log_path.exists():
        artifacts.append(
            artifact_store.manifest_entry_for_file(
                kind="memory_log",
                path=memory_log_path,
                content_type="text/markdown",
            ).__dict__
        )

    state_log_path = state_log_dir / f"full_states_log_{trade_date}.json"
    if state_log_path.exists():
        artifacts.append(
            artifact_store.manifest_entry_for_file(
                kind="state_log",
                path=state_log_path,
                content_type=_guess_content_type(state_log_path),
            ).__dict__
        )
    if provenance_dir is not None and provenance_dir.exists():
        for path in sorted(provenance_dir.rglob("*")):
            if path.is_file():
                artifacts.append(
                    artifact_store.manifest_entry_for_file(
                        kind="raw_tool_output",
                        path=path,
                        content_type=_guess_content_type(path),
                        ).__dict__
                    )
    if telemetry_dir is not None and telemetry_dir.exists():
        for path in sorted(telemetry_dir.rglob("*")):
            if path.is_file():
                artifacts.append(
                    artifact_store.manifest_entry_for_file(
                        kind="run_telemetry",
                        path=path,
                        content_type=_guess_content_type(path),
                    ).__dict__
                )
    return artifacts


def _guess_content_type(path: Path) -> str:
    if path.suffix == ".jsonl":
        return "application/x-ndjson"
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".md":
        return "text/markdown"
    if path.suffix == ".csv":
        return "text/csv"
    if path.suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


def run_shadow_job(
    request: ShadowRunRequest,
    artifact_store: ArtifactStore | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ShadowRunResult:
    output_root = request.repo_root / "output"
    shadow_run_id = _run_id_for_request(request)
    run_root = output_root / "runs" / shadow_run_id
    for path in (
        run_root / "logs",
        run_root / "cache",
        run_root / "memory",
        run_root / "provenance",
        run_root / "telemetry",
    ):
        path.mkdir(parents=True, exist_ok=True)

    config = _build_config(request, output_root=run_root)
    provenance_recorder = ToolProvenanceRecorder(shadow_run_id=shadow_run_id)
    telemetry_recorder = RunTelemetryRecorder(shadow_run_id=shadow_run_id)
    graph = TradingAgentsGraph(
        selected_analysts=request.selected_analysts,
        debug=request.debug,
        config=config,
        callbacks=[provenance_recorder, telemetry_recorder],
    )
    final_state, decision = graph.propagate(
        request.ticker,
        request.trade_date,
        progress_callback=progress_callback,
        target_profile=request.target_profile,
    )
    final_state["target_profile"] = request.target_profile or {}

    state_log_dir = Path(config["results_dir"]) / request.ticker / "TradingAgentsStrategy_logs"
    memory_log_path = Path(config["memory_log_path"])
    provenance_dir = run_root / "provenance" / request.ticker / str(request.trade_date)
    telemetry_dir = run_root / "telemetry" / request.ticker / str(request.trade_date)
    graph_raw_tool_outputs = final_state.get("raw_tool_outputs") if isinstance(final_state.get("raw_tool_outputs"), list) else []
    raw_tool_outputs = graph_raw_tool_outputs or provenance_recorder.records
    telemetry_records = telemetry_recorder.records
    raw_tool_manifest = write_tool_provenance(raw_tool_outputs, provenance_dir, shadow_run_id=shadow_run_id)
    telemetry_manifest = write_run_telemetry(telemetry_records, telemetry_dir, shadow_run_id=shadow_run_id)
    final_state["raw_tool_outputs"] = raw_tool_outputs
    final_state["raw_tool_provenance"] = raw_tool_manifest or {}
    final_state["run_telemetry"] = telemetry_manifest or {}
    final_state["raw_tool_provenance_expected"] = True
    final_state["shadow_run_id"] = shadow_run_id
    backend = artifact_store or LocalArtifactBackend()
    artifacts = _collect_artifacts(
        artifact_store=backend,
        memory_log_path=memory_log_path,
        state_log_dir=state_log_dir,
        trade_date=request.trade_date,
        provenance_dir=provenance_dir,
        telemetry_dir=telemetry_dir,
    )
    quality = assess_shadow_run_quality(
        ticker=request.ticker,
        final_trade_decision=final_state.get("final_trade_decision"),
        final_state=final_state,
    ).to_dict()
    recommendation_contract = build_recommendation_contract(
        final_rating=decision,
        decision_markdown=final_state.get("final_trade_decision"),
        quality=quality,
        telemetry_summary=telemetry_manifest or {},
        target_profile=request.target_profile,
    )
    quality["recommendation_contract"] = recommendation_contract

    return ShadowRunResult(
        shadow_run_id=shadow_run_id,
        ticker=request.ticker,
        trade_date=request.trade_date,
        decision=recommendation_contract["final_rating"],
        final_trade_decision=recommendation_contract["decision_markdown"],
        state_log_dir=str(state_log_dir),
        memory_log_path=str(memory_log_path),
        provider=request.provider,
        deep_model=request.deep_model,
        quick_model=request.quick_model,
        artifacts=artifacts,
        quality=quality,
        telemetry=telemetry_manifest or {},
    )
