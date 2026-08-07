"""Attach price labels only after an immutable decision batch exists.

This module intentionally has no forecast-model dependency or model credential
handling.  Provider failures become explicit missing labels instead of dropped
sample dates.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from tradingagents.research.artifacts import (
    ArtifactRef,
    FilesystemArtifactStore,
    require_payload_reference,
)
from tradingagents.research.contracts import (
    DecisionBatch,
    OutcomeBatch,
    OutcomeObservation,
    OutcomeRecord,
    parse_contract,
)
from tradingagents.research.outcomes import OutcomeProvider
from tradingagents.research_protocol import build_identity


def _safe_error_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"


def attach_labels(
    *,
    decisions: DecisionBatch,
    decision_ref: ArtifactRef,
    provider: OutcomeProvider,
) -> OutcomeBatch:
    require_payload_reference(
        decision_ref, kind="decisions", payload=decisions.model_dump(mode="json")
    )
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
            if observation.provider != provider.provider_name:
                raise ValueError("outcome provider returned a different provider identity")
            if set(observation.asset_returns) != set(decisions.universe):
                raise ValueError("outcome provider returned a different universe")
            if observation.observed_at <= decision.decision_cutoff:
                raise ValueError("outcome was captured before its decision cutoff")
            if observation.entry_date is not None and (
                observation.entry_date <= decision.decision_date
                or observation.exit_date is None
                or observation.exit_date <= observation.entry_date
            ):
                raise ValueError("outcome provider returned an invalid decision horizon")
            if observation.exit_date is not None and (
                observation.observed_at.date() < observation.exit_date
            ):
                raise ValueError("outcome was captured before its exit session")
        except Exception as exc:
            error_type = _safe_error_type(exc)
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
    decision_ref = artifact_store.load_ref("decisions", decision_artifact_id)
    decisions = parse_contract(
        DecisionBatch, artifact_store.load("decisions", decision_artifact_id)
    )
    batch = attach_labels(
        decisions=decisions,
        decision_ref=decision_ref,
        provider=provider,
    )
    return artifact_store.commit("labels", batch.model_dump(mode="json"))
