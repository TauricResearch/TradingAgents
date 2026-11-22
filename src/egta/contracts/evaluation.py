"""Evaluation contracts: comparison & replay (implements the approved FR-05 spec).

# Implements: FR-05, NFR-08, NFR-09

``compare_runs`` takes typed ``RunSummary`` inputs (bare dicts rejected) and
returns an ``EvaluationResult``. Comparability requires equal
``manifest_hash`` / snapshot / model / prompt / code / policy; any mismatch yields
``INCOMPLETE`` with a specific ``IncompleteReason`` and is NOT a win
(``winner is None``, both ``*_win`` False). A missing result / unknown usage
yields ``MISSING_RESULT`` / ``MISSING_USAGE``; a rubric metric not observed on
BOTH sides yields ``MISSING_METRIC``. ``incomplete`` is a STATUS, never raised.

Threshold handling (D Option Y), evaluated per side (never ``{**base, **enh}``):
- both within threshold -> COMPLETE, ``failures=[]``;
- one/both sides exceed -> REVIEW, per-side ``THRESHOLD_VIOLATION`` failures;
- observed value is used (never the threshold); ``quality_labels`` come from the
  ENHANCED side; ``run_pair_id``/``case_id`` are explicit.
Winner/composite scoring is deferred (DEBT-FR05-D4): ``winner``/``baseline_win``/
``enhanced_win`` stay None/False. ``THRESHOLD_VIOLATION`` is NOT an
``IncompleteReason`` (it is a ``failures`` string). Definitions:
docs/req/contracts-summary.md §2.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from egta.contracts.audit import dedupe_events, verify_chain
from egta.contracts.events import RunEvent
from egta.contracts.manifest import MetricDef

_H64 = r"^[0-9a-f]{64}$"
_CODE = r"^([0-9a-f]{40}|[0-9a-f]{64})$"

# operator -> predicate(observed, threshold)
_OPERATORS = {
    "eq": lambda v, t: v == t,
    "lte": lambda v, t: v <= t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "gt": lambda v, t: v > t,
}


class CompletionStatus(StrEnum):
    """Terminal status of a comparison; HOLD is NOT a member (it is an action)."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    FAILED = "FAILED"


class IncompleteReason(StrEnum):
    """Why a pair is INCOMPLETE (THRESHOLD_VIOLATION is NOT a member)."""

    MANIFEST_MISMATCH = "MANIFEST_MISMATCH"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    PROMPT_MISMATCH = "PROMPT_MISMATCH"
    CODE_MISMATCH = "CODE_MISMATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    MISSING_RESULT = "MISSING_RESULT"
    MISSING_USAGE = "MISSING_USAGE"
    MISSING_METRIC = "MISSING_METRIC"


class EvaluationResult(BaseModel):
    """One variant's outcome in a paired comparison (§5.1 complete)."""

    model_config = ConfigDict(extra="allow")

    run_pair_id: str
    case_id: str
    variant: str
    manifest_hash: str
    completion_status: CompletionStatus
    incomplete_reason: IncompleteReason | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    quality_labels: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    winner: str | None = None
    baseline_win: bool = False
    enhanced_win: bool = False

    @model_validator(mode="after")
    def _reason_consistency(self) -> EvaluationResult:
        if self.completion_status is CompletionStatus.INCOMPLETE:
            if self.incomplete_reason is None:
                raise ValueError("INCOMPLETE requires incomplete_reason")
            self.winner = None
            self.baseline_win = False
            self.enhanced_win = False
        elif (
            self.completion_status is CompletionStatus.COMPLETE
            and self.incomplete_reason is not None
        ):
            raise ValueError("COMPLETE must not carry an incomplete_reason")
        return self


class RunSummary(BaseModel):
    """Typed input to ``compare_runs`` (a RunSpec normalized upstream)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    variant: str
    target_snapshot_id: str
    model_config_hash: str = Field(pattern=_H64)
    prompt_hash: str = Field(pattern=_H64)
    code_hash: str = Field(pattern=_CODE)
    policy_hash: str = Field(pattern=_H64)
    manifest_hash: str = Field(pattern=_H64)
    has_result: bool = True
    has_usage: bool = True
    metrics: dict[str, float] = Field(default_factory=dict)
    quality_labels: list[str] = Field(default_factory=list)


class ReplayState(BaseModel):
    """Reconstructed state of a run's event log."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    last_sequence: int
    chain_tip_hash: str
    event_count: int
    metrics: dict[str, float]
    events: list[RunEvent]


def replay_events(events: list[RunEvent], *, anchor: str | None = None) -> ReplayState:
    """Reconstruct a run's state offline from its events (deterministic).

    Deduplicates first (``dedupe_events``; conflicting duplicates raise
    ``DuplicateConflict``), then verifies the chain, sorts by ``(run_id,
    sequence)``, and folds metrics. ``event_count`` is the number of deduplicated
    events.
    """
    deduped = dedupe_events(events)
    verify_chain(deduped, anchor=anchor)
    ordered = sorted(deduped, key=lambda e: (e.run_id, e.sequence))
    metrics: dict[str, float] = {}
    for event in ordered:
        metrics.update(event.metrics)
    return ReplayState(
        run_id=ordered[0].run_id,
        last_sequence=ordered[-1].sequence,
        chain_tip_hash=ordered[-1].payload_hash,
        event_count=len(deduped),
        metrics=metrics,
        events=ordered,
    )


def _as_summary(value: RunSummary | dict) -> RunSummary:
    if isinstance(value, RunSummary):
        return value
    if isinstance(value, dict):
        raise TypeError("compare_runs requires typed RunSummary, not a bare dict")
    return RunSummary.model_validate(value)


def _fmt_violation(metric: str, side: str, observed: float,
                   operator: str, threshold: float) -> str:
    return (f"THRESHOLD_VIOLATION:{metric}:{side}:observed={float(observed)}"
            f":operator={operator}:threshold={float(threshold)}")


def compare_runs(
    baseline: RunSummary, enhanced: RunSummary, rubric: dict,
    *, manifest=None, run_pair_id: str | None = None, case_id: str | None = None,
) -> EvaluationResult:
    """Compare two typed run summaries under ``rubric``; INCOMPLETE is not a win.

    Check order (D#1): manifest -> snapshot/model/prompt/code/policy ->
    result/usage -> rubric observation. Rubric is validated as ``dict[str,
    MetricDef]`` (illegal -> ``ValidationError``). Each metric is required on
    BOTH sides (else ``MISSING_METRIC``); threshold breach (D Option Y) -> REVIEW
    with per-side ``THRESHOLD_VIOLATION`` failures. Winner/composite scoring is
    deferred (DEBT-FR05-D4): stays None/False.
    """
    base = _as_summary(baseline)
    enha = _as_summary(enhanced)
    pair_id = run_pair_id if run_pair_id is not None else base.run_id
    case = case_id if case_id is not None else base.variant

    def _incomplete(reason):
        return EvaluationResult(
            run_pair_id=pair_id, case_id=case, variant=enha.variant,
            manifest_hash=base.manifest_hash,
            completion_status=CompletionStatus.INCOMPLETE,
            incomplete_reason=reason,
        )

    # D#1: supplied manifest must recompute to both sides' manifest_hash.
    if manifest is not None:
        from egta.contracts.manifest import compute_manifest_hash

        computed = compute_manifest_hash(manifest)
        if (computed != manifest.manifest_hash
                or base.manifest_hash != computed
                or enha.manifest_hash != computed):
            return _incomplete(IncompleteReason.MANIFEST_MISMATCH)

    checks = (
        ("manifest_hash", IncompleteReason.MANIFEST_MISMATCH),
        ("target_snapshot_id", IncompleteReason.SNAPSHOT_MISMATCH),
        ("model_config_hash", IncompleteReason.MODEL_MISMATCH),
        ("prompt_hash", IncompleteReason.PROMPT_MISMATCH),
        ("code_hash", IncompleteReason.CODE_MISMATCH),
        ("policy_hash", IncompleteReason.POLICY_MISMATCH),
    )
    for field, reason in checks:
        if getattr(base, field) != getattr(enha, field):
            return _incomplete(reason)

    if not base.has_result or not enha.has_result:
        return _incomplete(IncompleteReason.MISSING_RESULT)
    if not base.has_usage or not enha.has_usage:
        return _incomplete(IncompleteReason.MISSING_USAGE)

    # Typed rubric validation (illegal -> ValidationError).
    rubric = TypeAdapter(dict[str, MetricDef]).validate_python(rubric)

    # Each metric must be observed on BOTH sides (checked separately).
    if any(name not in base.metrics or name not in enha.metrics for name in rubric):
        return _incomplete(IncompleteReason.MISSING_METRIC)

    # Scored value = enhanced observed value (never the threshold).
    scored = {name: float(enha.metrics[name]) for name in rubric}

    # D Option Y: per-side threshold evaluation.
    failures: list[str] = []
    for name, definition in rubric.items():
        predicate = _OPERATORS[definition.operator]
        for side, summary in (("baseline", base), ("enhanced", enha)):
            observed = float(summary.metrics[name])
            if not predicate(observed, definition.threshold):
                failures.append(_fmt_violation(
                    name, side, observed, definition.operator, definition.threshold))

    if failures:
        return EvaluationResult(
            run_pair_id=pair_id, case_id=case, variant=enha.variant,
            manifest_hash=base.manifest_hash,
            completion_status=CompletionStatus.REVIEW,
            incomplete_reason=None,
            metrics=scored,
            quality_labels=list(enha.quality_labels),
            failures=failures,
        )

    return EvaluationResult(
        run_pair_id=pair_id, case_id=case, variant=enha.variant,
        manifest_hash=base.manifest_hash,
        completion_status=CompletionStatus.COMPLETE,
        metrics=scored,
        quality_labels=list(enha.quality_labels),
        failures=[],
    )
