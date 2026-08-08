"""Attach price labels only after an immutable decision batch exists.

This module intentionally has no forecast-model dependency or model credential
handling.  Provider failures become explicit missing labels instead of dropped
sample dates.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from tradingagents.logging_utils import safe_exception_type
from tradingagents.research.artifacts import (
    ArtifactRef,
    FilesystemArtifactStore,
    require_payload_reference,
)
from tradingagents.research.contracts import (
    DecisionBatch,
    EvidenceSnapshot,
    OutcomeBatch,
    OutcomeObservation,
    OutcomeRecord,
    parse_contract,
)
from tradingagents.research.decision_validation import (
    replay_decision_batch,
    validate_decision_batch_protocol,
    validate_snapshot_protocol,
)
from tradingagents.research.errors import OutcomeUnavailableError
from tradingagents.research.outcome_validation import validate_outcome_observation
from tradingagents.research.outcomes import OutcomeProvider
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    build_identity,
)


def attach_labels(
    *,
    decisions: DecisionBatch,
    decision_ref: ArtifactRef,
    provider: OutcomeProvider,
) -> OutcomeBatch:
    require_payload_reference(
        decision_ref, kind="decisions", payload=decisions.model_dump(mode="json")
    )
    validate_decision_batch_protocol(decisions)
    expected_provider = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
        "exploratory_history_adapter"
    ]["provider_id"]
    if provider.provider_name != expected_provider:
        raise ValueError("outcome provider differs from the frozen protocol")
    outcomes = []
    for decision in decisions.decisions:
        error_type = None
        try:
            observation = provider.observe(
                decision_date=decision.decision_date,
                universe=decisions.universe,
                benchmark=decisions.benchmark,
            )
            if not isinstance(observation, OutcomeObservation):
                observation = parse_contract(OutcomeObservation, observation)
        except OutcomeUnavailableError as exc:
            error_type = safe_exception_type(exc)
            observed_at = datetime.now(timezone.utc)
            attempted = (
                f"{provider.provider_name}:{decision.decision_date.isoformat()}"
            ).encode()
            observation = OutcomeObservation(
                provider=provider.provider_name,
                observed_at=observed_at,
                vintage_id=f"unavailable:{decision.decision_date.isoformat()}",
                raw_payload_sha256=hashlib.sha256(attempted).hexdigest(),
                entry_date=None,
                exit_date=None,
                asset_returns=dict.fromkeys(decisions.universe),
                benchmark_return=None,
                cash_return=0.0,
                provenance={
                    "provider": provider.provider_name,
                    "status": "provider_failure",
                },
            )
        validate_outcome_observation(
            observation,
            decision_date=decision.decision_date,
            universe=decisions.universe,
            benchmark=decisions.benchmark,
            error_type=error_type,
        )
        missing = observation.benchmark_return is None or any(
            value is None for value in observation.asset_returns.values()
        )
        outcomes.append(
            OutcomeRecord(
                decision_date=decision.decision_date,
                status="missing" if missing else "complete",
                observation=observation,
                error_type=error_type,
            )
        )
    return OutcomeBatch(
        run_id=decisions.run_id,
        build_id=build_identity(),
        decision_artifact_id=decision_ref.artifact_id,
        decision_payload_sha256=decision_ref.payload_sha256,
        provider=provider.provider_name,
        universe=decisions.universe,
        benchmark=decisions.benchmark,
        outcomes=tuple(outcomes),
    )


def label_from_artifact(
    *,
    artifact_store: FilesystemArtifactStore,
    decision_artifact_id: str,
    provider: OutcomeProvider,
) -> ArtifactRef:
    decision_ref, payload = artifact_store.load_with_ref(
        "decisions", decision_artifact_id
    )
    decisions = parse_contract(DecisionBatch, payload)
    snapshot_ref, snapshot_payload = artifact_store.load_with_ref(
        "snapshot", decisions.snapshot_artifact_id
    )
    snapshot = parse_contract(EvidenceSnapshot, snapshot_payload)
    validate_snapshot_protocol(snapshot, decisions.checkpoint)
    replay_decision_batch(
        decisions,
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
    )
    batch = attach_labels(
        decisions=decisions,
        decision_ref=decision_ref,
        provider=provider,
    )
    return artifact_store.commit("labels", batch.model_dump(mode="json"))
