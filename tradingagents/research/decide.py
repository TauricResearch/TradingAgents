"""Generate and commit targets from a frozen evidence snapshot.

This module intentionally has no price-label or outcome-provider dependency.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from tradingagents.global_research import validate_forecast_bundle
from tradingagents.logging_utils import safe_exception_type
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
from tradingagents.research.decision_validation import (
    allocator_config,
    replay_decision_batch,
    selected_arm_rows,
    validate_snapshot_protocol,
)
from tradingagents.research.errors import ForecastUnavailableError
from tradingagents.research.model import ForecastModel
from tradingagents.research_protocol import build_identity


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


def generate_decisions(
    *,
    snapshot: EvidenceSnapshot,
    snapshot_ref: ArtifactRef,
    checkpoint: ModelCheckpointSpec,
    model: ForecastModel,
    arm: Literal["global_events", "without_public_reaction"] = "global_events",
) -> DecisionBatch:
    """Run the model sequentially without ever making outcome data available."""
    require_payload_reference(
        snapshot_ref, kind="snapshot", payload=snapshot.model_dump(mode="json")
    )
    if arm not in {"global_events", "without_public_reaction"}:
        raise ValueError("unknown decision arm")
    validate_snapshot_protocol(snapshot, checkpoint)
    checkpoint.require_predates(tuple(item.decision_cutoff for item in snapshot.slices))
    allocator = allocator_config()
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
        arm_evidence = selected_arm_rows(item, arm)
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
        except ForecastUnavailableError as exc:
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
                error_type=safe_exception_type(exc),
            )
        decisions.append(record)
    batch = DecisionBatch(
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
    replay_decision_batch(batch, snapshot=snapshot, snapshot_ref=snapshot_ref)
    return batch


def decide_from_artifact(
    *,
    artifact_store: FilesystemArtifactStore,
    snapshot_artifact_id: str,
    checkpoint: ModelCheckpointSpec,
    model: ForecastModel,
    arm: Literal["global_events", "without_public_reaction"] = "global_events",
) -> ArtifactRef:
    snapshot_ref, payload = artifact_store.load_with_ref(
        "snapshot", snapshot_artifact_id
    )
    snapshot = parse_contract(EvidenceSnapshot, payload)
    batch = generate_decisions(
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
        checkpoint=checkpoint,
        model=model,
        arm=arm,
    )
    return artifact_store.commit("decisions", batch.model_dump(mode="json"))
