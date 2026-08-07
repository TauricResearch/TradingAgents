"""Generate and commit targets from a frozen evidence snapshot.

This module intentionally has no price-label or outcome-provider dependency.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, Literal

from tradingagents.global_research import (
    _evidence_id,
    prepare_evidence,
    validate_forecast_bundle,
)
from tradingagents.portfolio_backtest import optimize_forecast_weights
from tradingagents.research.artifacts import (
    ArtifactRef,
    FilesystemArtifactStore,
    require_payload_reference,
)
from tradingagents.research.contracts import (
    DecisionBatch,
    DecisionRecord,
    EvidenceSnapshot,
    ModelCheckpointSpec,
    parse_contract,
)
from tradingagents.research.model import ForecastModel
from tradingagents.research.x_availability import validate_bound_x_selection
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    build_identity,
)


def _safe_error_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"


def _allocator_config(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    policy = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
    config = {
        "gross_limit": float(policy["gross_limit"]),
        "max_weight": float(policy["max_weight"]),
        "max_sector_weight": float(policy["max_sector_weight"]),
        "turnover_hurdle_bps": float(policy["turnover_hurdle_bps"]),
        "minimum_trade_weight": float(policy["minimum_trade_weight"]),
        "trading_cost_bps": float(policy["trading_cost_bps"]),
        "slippage_bps": float(policy["slippage_bps"]),
    }
    if overrides:
        unknown = set(overrides) - set(config)
        if unknown:
            raise ValueError(f"unknown allocator settings: {sorted(unknown)}")
        config.update({key: float(value) for key, value in overrides.items()})
    return config


def _neutral_decision(
    *,
    snapshot_slice,
    universe: tuple[str, ...],
    current_weights: dict[str, float],
) -> DecisionRecord:
    cash = max(0.0, 1.0 - sum(current_weights.values()))
    diagnostics = {
        "weights": dict(current_weights),
        "turnover": 0.0,
        "cash_weight": cash,
        "active_forecasts": [],
        "abstentions": list(universe),
        "binding_constraints": [],
        "reason": "snapshot has no complete eligible evidence input",
    }
    return DecisionRecord(
        decision_date=snapshot_slice.decision_date,
        decision_cutoff=snapshot_slice.decision_cutoff,
        status="no_evidence",
        input_selection_manifest_id=snapshot_slice.selection_manifest["manifest_id"],
        forecast_bundle=None,
        target_weights=dict(current_weights),
        cash_weight=cash,
        turnover=0.0,
        allocator_diagnostics=diagnostics,
    )


def _require_frozen_protocol(snapshot: EvidenceSnapshot, checkpoint: ModelCheckpointSpec) -> None:
    if snapshot.protocol_id != GLOBAL_EVENT_V2_PROTOCOL_ID:
        raise ValueError("decision runner supports only the compiled global-event protocol")
    if snapshot.collection_policy_id != GLOBAL_EVENT_V2_PROTOCOL["evidence"][
        "expected_collector_semantics_id"
    ]:
        raise ValueError("snapshot collector policy differs from the frozen protocol")
    universe = GLOBAL_EVENT_V2_PROTOCOL["universe"]
    if snapshot.universe != tuple(universe["symbols"]) \
            or snapshot.sectors != universe["sectors"]:
        raise ValueError("snapshot universe differs from the frozen protocol")
    if snapshot.benchmark != GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["benchmark"]:
        raise ValueError("snapshot benchmark differs from the frozen protocol")
    forecast = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
    if checkpoint.provider != forecast["provider"] \
            or checkpoint.requested_model != forecast["requested_model"]:
        raise ValueError("checkpoint differs from the frozen forecast protocol")
    if not set(checkpoint.returned_model_allowlist).issubset(
        set(forecast["allowed_returned_models"])
    ):
        raise ValueError("checkpoint returned-model allowlist exceeds the protocol")
    for item in snapshot.slices:
        validate_bound_x_selection(item.selection_manifest, item.raw_evidence)
        if item.coverage.get("x_cycle_availability") != item.selection_manifest.get(
            "x_cycle_availability"
        ):
            raise ValueError("snapshot coverage differs from its X availability binding")


def _selected_arm_rows(snapshot_slice, arm: str) -> tuple[dict[str, Any], ...]:
    selection_key = "champion" if arm == "global_events" else "without_public_reaction"
    expected_ids = snapshot_slice.selection_manifest.get(
        "ordered_selected_evidence_ids", {}
    ).get(selection_key)
    if not isinstance(expected_ids, list) or any(
        not isinstance(value, str) for value in expected_ids
    ):
        raise ValueError("snapshot selection manifest lacks the requested evidence arm")
    candidates = tuple(
        row
        for row in snapshot_slice.raw_evidence
        if arm == "global_events" or row.get("source") != "x"
    )
    prepared = prepare_evidence(list(candidates))
    actual_ids = [row["evidence_id"] for row in prepared]
    if actual_ids != expected_ids:
        raise ValueError("snapshot selected evidence cannot be reproduced from raw lineage")
    raw_by_id = {_evidence_id(row): row for row in candidates}
    if len(raw_by_id) != len(candidates) or any(
        evidence_id not in raw_by_id for evidence_id in expected_ids
    ):
        raise ValueError("snapshot selected evidence has ambiguous raw lineage")
    selected = tuple(raw_by_id[evidence_id] for evidence_id in expected_ids)
    if prepare_evidence(list(selected)) != prepared:
        raise ValueError("snapshot selected projection is not stable in isolation")
    return selected


def generate_decisions(
    *,
    snapshot: EvidenceSnapshot,
    snapshot_ref: ArtifactRef,
    checkpoint: ModelCheckpointSpec,
    model: ForecastModel,
    arm: Literal["global_events", "without_public_reaction"] = "global_events",
    allocator_overrides: Mapping[str, Any] | None = None,
) -> DecisionBatch:
    """Run the model sequentially without ever making outcome data available."""
    require_payload_reference(
        snapshot_ref, kind="snapshot", payload=snapshot.model_dump(mode="json")
    )
    if arm not in {"global_events", "without_public_reaction"}:
        raise ValueError("unknown decision arm")
    _require_frozen_protocol(snapshot, checkpoint)
    checkpoint.require_predates(tuple(item.decision_cutoff for item in snapshot.slices))
    allocator = _allocator_config(allocator_overrides)
    current_weights = dict.fromkeys(snapshot.universe, 0.0)
    decisions = []
    for item in snapshot.slices:
        coverage_complete = item.coverage.get("complete") is True
        selection_key = "champion" if arm == "global_events" else "without_public_reaction"
        selected = item.selection_manifest.get("ordered_selected_evidence_ids", {}).get(
            selection_key, []
        )
        if not coverage_complete or not selected:
            record = _neutral_decision(
                snapshot_slice=item,
                universe=snapshot.universe,
                current_weights=current_weights,
            )
            decisions.append(record)
            continue
        arm_evidence = _selected_arm_rows(item, arm)
        try:
            bundle = model.forecast(
                checkpoint=checkpoint,
                decision_date=item.decision_date.isoformat(),
                raw_evidence=arm_evidence,
                universe=snapshot.universe,
            )
            if not isinstance(bundle, dict):
                raise TypeError("forecast adapter must return a mapping")
            if bundle.get("checkpoint_id") != checkpoint.checkpoint_id or (
                bundle.get("checkpoint_weights_sha256") != checkpoint.weights_sha256
            ):
                raise ValueError("forecast bundle differs from the declared checkpoint")
            response_metadata = bundle.get("response_metadata")
            if not isinstance(response_metadata, dict):
                raise ValueError("forecast bundle lacks response metadata")
            returned_models = {
                value.strip()
                for key in ("model_name", "model", "model_id")
                if isinstance((value := response_metadata.get(key)), str) and value.strip()
            }
            if len(returned_models) != 1 or (
                returned_models.pop() not in checkpoint.returned_model_allowlist
            ):
                raise ValueError("forecast bundle returned a different model checkpoint")
            forecast = validate_forecast_bundle(
                bundle,
                provider=checkpoint.provider,
                requested_model=checkpoint.requested_model,
                decision_date=item.decision_date.isoformat(),
                rows=list(arm_evidence),
                universe=list(snapshot.universe),
            )
            rows = [row.model_dump(mode="json") for row in forecast.forecasts]
            result = optimize_forecast_weights(
                rows,
                current_weights=current_weights,
                sectors=snapshot.sectors,
                gross_limit=allocator["gross_limit"],
                max_weight=allocator["max_weight"],
                max_sector_weight=allocator["max_sector_weight"],
                turnover_hurdle_bps=allocator["turnover_hurdle_bps"],
                minimum_trade_weight=allocator["minimum_trade_weight"],
            )
            diagnostics = {"weights": dict(result.weights), **asdict(result)}
            record = DecisionRecord(
                decision_date=item.decision_date,
                decision_cutoff=item.decision_cutoff,
                status="success",
                input_selection_manifest_id=item.selection_manifest["manifest_id"],
                forecast_bundle=bundle,
                target_weights=result.weights,
                cash_weight=result.cash_weight,
                turnover=result.turnover,
                allocator_diagnostics=diagnostics,
            )
            current_weights = dict(result.weights)
        except Exception as exc:  # one failed checkpoint date remains in the sample
            cash = max(0.0, 1.0 - sum(current_weights.values()))
            record = DecisionRecord(
                decision_date=item.decision_date,
                decision_cutoff=item.decision_cutoff,
                status="failed",
                input_selection_manifest_id=item.selection_manifest["manifest_id"],
                forecast_bundle=None,
                target_weights=dict(current_weights),
                cash_weight=cash,
                turnover=0.0,
                allocator_diagnostics={
                    "weights": dict(current_weights),
                    "turnover": 0.0,
                    "cash_weight": cash,
                    "active_forecasts": [],
                    "abstentions": list(snapshot.universe),
                    "binding_constraints": [],
                    "reason": "model invocation failed; target carried forward",
                },
                error_type=_safe_error_type(exc),
            )
        decisions.append(record)
    return DecisionBatch(
        run_id=snapshot.run_id,
        build_id=build_identity(),
        protocol_id=snapshot.protocol_id,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        snapshot_payload_sha256=snapshot_ref.payload_sha256,
        checkpoint=checkpoint,
        arm=arm,
        universe=snapshot.universe,
        benchmark=snapshot.benchmark,
        initial_portfolio={
            "asset_weights": dict.fromkeys(snapshot.universe, 0.0),
            "cash_weight": 1.0,
        },
        allocator=allocator,
        decisions=tuple(decisions),
    )


def decide_from_artifact(
    *,
    artifact_store: FilesystemArtifactStore,
    snapshot_artifact_id: str,
    checkpoint: ModelCheckpointSpec,
    model: ForecastModel,
    arm: Literal["global_events", "without_public_reaction"] = "global_events",
    allocator_overrides: Mapping[str, Any] | None = None,
) -> ArtifactRef:
    snapshot_ref = artifact_store.load_ref("snapshot", snapshot_artifact_id)
    snapshot = parse_contract(
        EvidenceSnapshot, artifact_store.load("snapshot", snapshot_artifact_id)
    )
    batch = generate_decisions(
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
        checkpoint=checkpoint,
        model=model,
        arm=arm,
        allocator_overrides=allocator_overrides,
    )
    return artifact_store.commit("decisions", batch.model_dump(mode="json"))
