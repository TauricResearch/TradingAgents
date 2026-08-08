"""Pure replay checks for frozen global-event decision batches."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from tradingagents.evidence_lineage import evidence_id
from tradingagents.global_research import (
    bind_receipt_coverage_to_selection,
    formal_globalnews_selection_coverage,
    prepare_evidence,
    validate_forecast_bundle,
)
from tradingagents.portfolio_backtest import optimize_forecast_weights
from tradingagents.research.artifacts import ArtifactRef, require_payload_reference
from tradingagents.research.contracts import (
    DecisionBatch,
    EvidenceSnapshot,
    ModelCheckpointSpec,
)
from tradingagents.research.coverage import validate_global_event_receipt_coverage
from tradingagents.research.timeline import (
    decision_cutoff,
    require_contiguous_xnys_sessions,
)
from tradingagents.research.x_availability import validate_bound_x_selection
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
)


def allocator_config() -> dict[str, float]:
    policy = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
    config = {
        key: float(policy[key])
        for key in (
            "gross_limit",
            "max_weight",
            "max_sector_weight",
            "turnover_hurdle_bps",
            "minimum_trade_weight",
            "trading_cost_bps",
            "slippage_bps",
        )
    }
    return config


def validate_snapshot_protocol(
    snapshot: EvidenceSnapshot,
    checkpoint: ModelCheckpointSpec,
) -> None:
    """Replay every protocol-owned snapshot field before model or label access."""
    if snapshot.protocol_id != GLOBAL_EVENT_V2_PROTOCOL_ID:
        raise ValueError("decision runner supports only the compiled global-event protocol")
    if snapshot.collection_policy_id != GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID:
        raise ValueError("snapshot collector policy differs from the frozen protocol")
    universe = GLOBAL_EVENT_V2_PROTOCOL["universe"]
    if (
        snapshot.universe != tuple(universe["symbols"])
        or snapshot.sectors != universe["sectors"]
    ):
        raise ValueError("snapshot universe differs from the frozen protocol")
    if snapshot.benchmark != GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["benchmark"]:
        raise ValueError("snapshot benchmark differs from the frozen protocol")
    forecast = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
    if (
        checkpoint.provider != forecast["provider"]
        or checkpoint.requested_model != forecast["requested_model"]
    ):
        raise ValueError("checkpoint differs from the frozen forecast protocol")
    if not set(checkpoint.returned_model_allowlist).issubset(
        set(forecast["allowed_returned_models"])
    ):
        raise ValueError("checkpoint returned-model allowlist exceeds the protocol")

    require_contiguous_xnys_sessions(
        item.decision_date for item in snapshot.slices
    )
    for item in snapshot.slices:
        if item.decision_cutoff != decision_cutoff(item.decision_date):
            raise ValueError("snapshot cutoff differs from the frozen decision timeline")
        validate_bound_x_selection(item.selection_manifest, item.raw_evidence)
        if item.coverage.get("x_cycle_availability") != item.selection_manifest.get(
            "x_cycle_availability"
        ):
            raise ValueError("snapshot coverage differs from its X availability binding")
        receipt = item.coverage.get("receipt_coverage")
        binding = item.coverage.get("receipt_selection_binding")
        selection_coverage = item.coverage.get("selection_coverage")
        if not all(
            isinstance(value, dict)
            for value in (receipt, selection_coverage, binding)
        ):
            raise ValueError("snapshot receipt coverage binding is incomplete")
        validate_global_event_receipt_coverage(
            receipt, cutoff_utc=item.decision_cutoff.timestamp()
        )
        expected_selection_coverage = formal_globalnews_selection_coverage(
            item.selection_manifest
        )
        expected_binding = bind_receipt_coverage_to_selection(
            receipt, item.selection_manifest
        )
        expected_complete = bool(
            receipt.get("complete") is True
            and expected_selection_coverage.get("complete") is True
            and expected_binding.get("complete") is True
        )
        stored_complete = item.coverage.get("complete")
        if (
            not all(
                isinstance(value, bool)
                for value in (
                    receipt.get("complete"),
                    selection_coverage.get("complete"),
                    binding.get("complete"),
                    stored_complete,
                )
            )
            or selection_coverage != expected_selection_coverage
            or binding != expected_binding
            or stored_complete is not expected_complete
        ):
            raise ValueError("snapshot receipt coverage does not replay")


def validate_decision_batch_protocol(decisions: DecisionBatch) -> None:
    """Validate the protocol-owned fields before any outcome provider is called."""
    policy = GLOBAL_EVENT_V2_PROTOCOL
    universe = tuple(policy["universe"]["symbols"])
    if decisions.protocol_id != GLOBAL_EVENT_V2_PROTOCOL_ID:
        raise ValueError("decision batch differs from the frozen protocol")
    if decisions.universe != universe or decisions.benchmark != policy["portfolio"]["benchmark"]:
        raise ValueError("decision batch universe differs from the frozen protocol")
    checkpoint = decisions.checkpoint
    forecast = policy["forecast"]
    if checkpoint.provider != forecast["provider"] \
            or checkpoint.requested_model != forecast["requested_model"] \
            or not set(checkpoint.returned_model_allowlist).issubset(
                set(forecast["allowed_returned_models"])
            ):
        raise ValueError("decision checkpoint differs from the frozen protocol")

    expected_allocator = allocator_config()
    if set(decisions.allocator) != set(expected_allocator) or any(
        isinstance(decisions.allocator[key], bool)
        or not isinstance(decisions.allocator[key], (int, float))
        or float(decisions.allocator[key]) != expected
        for key, expected in expected_allocator.items()
    ):
        raise ValueError("decision allocator differs from the frozen protocol")
    dates = require_contiguous_xnys_sessions(
        decision.decision_date for decision in decisions.decisions
    )
    if any(
        decision.decision_cutoff != decision_cutoff(decision.decision_date)
        for decision in decisions.decisions
    ):
        raise ValueError("decision cutoff differs from the frozen timeline")
    checkpoint.require_predates(
        tuple(decision_cutoff(value) for value in dates)
    )

    sectors = policy["universe"]["sectors"]
    for decision in decisions.decisions:
        if any(
            isinstance(weight, bool) or not isinstance(weight, (int, float))
            for weight in (*decision.target_weights.values(), decision.cash_weight)
        ):
            raise ValueError("decision weights must be numeric")
        if sum(decision.target_weights.values()) > expected_allocator["gross_limit"] + 1e-12:
            raise ValueError("decision exceeds the frozen gross limit")
        if any(
            weight > expected_allocator["max_weight"] + 1e-12
            for weight in decision.target_weights.values()
        ):
            raise ValueError("decision exceeds the frozen position limit")
        sector_weights: dict[str, float] = {}
        for symbol, weight in decision.target_weights.items():
            sector = sectors[symbol]
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        if any(
            weight > expected_allocator["max_sector_weight"] + 1e-12
            for weight in sector_weights.values()
        ):
            raise ValueError("decision exceeds the frozen sector limit")


def selected_arm_rows(snapshot_slice, arm: str) -> tuple[dict[str, Any], ...]:
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
    if [row["evidence_id"] for row in prepared] != expected_ids:
        raise ValueError("snapshot selected evidence cannot be reproduced from raw lineage")
    raw_by_id = {evidence_id(row): row for row in candidates}
    if len(raw_by_id) != len(candidates) or any(
        evidence_id not in raw_by_id for evidence_id in expected_ids
    ):
        raise ValueError("snapshot selected evidence has ambiguous raw lineage")
    selected = tuple(raw_by_id[evidence_id] for evidence_id in expected_ids)
    if prepare_evidence(list(selected)) != prepared:
        raise ValueError("snapshot selected projection is not stable in isolation")
    return selected


def replay_decision_batch(
    decisions: DecisionBatch,
    *,
    snapshot: EvidenceSnapshot,
    snapshot_ref: ArtifactRef,
) -> None:
    """Recompute every target from the exact bound snapshot and forecast payload."""
    require_payload_reference(
        snapshot_ref,
        kind="snapshot",
        payload=snapshot.model_dump(mode="json"),
    )
    validate_decision_batch_protocol(decisions)
    if (
        decisions.snapshot_artifact_id != snapshot_ref.artifact_id
        or decisions.snapshot_payload_sha256 != snapshot_ref.payload_sha256
        or decisions.run_id != snapshot.run_id
        or decisions.protocol_id != snapshot.protocol_id
        or decisions.universe != snapshot.universe
        or decisions.benchmark != snapshot.benchmark
        or len(decisions.decisions) != len(snapshot.slices)
    ):
        raise ValueError("decision batch is not bound to the exact snapshot")

    current_weights = dict.fromkeys(decisions.universe, 0.0)
    for decision, snapshot_slice in zip(
        decisions.decisions, snapshot.slices, strict=True
    ):
        if (
            decision.decision_date != snapshot_slice.decision_date
            or decision.decision_cutoff != snapshot_slice.decision_cutoff
            or decision.input_selection_manifest_id
            != snapshot_slice.selection_manifest.get("manifest_id")
        ):
            raise ValueError("decision row differs from its snapshot slice")
        selection_key = (
            "champion"
            if decisions.arm == "global_events"
            else "without_public_reaction"
        )
        selected = snapshot_slice.selection_manifest.get(
            "ordered_selected_evidence_ids", {}
        ).get(selection_key, [])
        should_forecast = snapshot_slice.coverage.get("complete") is True and bool(selected)
        if not should_forecast:
            expected_status = "no_evidence"
            reason = "snapshot has no complete eligible evidence input"
        elif decision.status == "failed":
            if decision.error_type != "ForecastUnavailableError":
                raise ValueError("failed decision has a non-canonical error type")
            expected_status = "failed"
            reason = "model invocation failed; target carried forward"
        else:
            expected_status = "success"
            reason = None
        if decision.status != expected_status:
            raise ValueError("decision status does not replay from its snapshot")

        if expected_status == "success":
            bundle = decision.forecast_bundle
            assert isinstance(bundle, dict)
            if (
                bundle.get("checkpoint_id") != decisions.checkpoint.checkpoint_id
                or bundle.get("checkpoint_weights_sha256")
                != decisions.checkpoint.weights_sha256
            ):
                raise ValueError("forecast bundle differs from its checkpoint")
            arm_rows = selected_arm_rows(snapshot_slice, decisions.arm)
            forecast = validate_forecast_bundle(
                bundle,
                provider=decisions.checkpoint.provider,
                requested_model=decisions.checkpoint.requested_model,
                decision_date=decision.decision_date.isoformat(),
                rows=list(arm_rows),
                universe=list(decisions.universe),
            )
            result = optimize_forecast_weights(
                [row.model_dump(mode="json") for row in forecast.forecasts],
                current_weights=current_weights,
                sectors=GLOBAL_EVENT_V2_PROTOCOL["universe"]["sectors"],
                **{
                    key: decisions.allocator[key]
                    for key in (
                        "gross_limit",
                        "max_weight",
                        "max_sector_weight",
                        "turnover_hurdle_bps",
                        "minimum_trade_weight",
                    )
                },
            )
            expected_diagnostics = {"weights": dict(result.weights), **asdict(result)}
            if (
                decision.target_weights != result.weights
                or decision.cash_weight != result.cash_weight
                or decision.turnover != result.turnover
                or decision.allocator_diagnostics != expected_diagnostics
            ):
                raise ValueError("decision target does not replay from its forecast")
            current_weights = dict(result.weights)
            continue

        cash = max(0.0, 1.0 - sum(current_weights.values()))
        expected_diagnostics = {
            "weights": dict(current_weights),
            "turnover": 0.0,
            "cash_weight": cash,
            "active_forecasts": [],
            "abstentions": list(decisions.universe),
            "binding_constraints": [],
            "reason": reason,
        }
        if (
            decision.target_weights != current_weights
            or decision.cash_weight != cash
            or decision.turnover != 0.0
            or decision.allocator_diagnostics != expected_diagnostics
        ):
            raise ValueError("carried decision target does not replay")
