"""Contract tests for checkpoint/candidate frontier reconciliation.

These tests intentionally exercise the pure classifier with checkpoint-shaped
objects.  They do not need a LangGraph checkpointer or a RunStore.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    BUSINESS_PROJECTION_VERSION,
    RESERVED_OBSERVATION_FIELD,
    SERIALIZER_VERSION,
)
from tradingagents.observability.events import (
    ObservationCommitV1,
    PersistedEvent,
    RunEventDraft,
)
from tradingagents.web.reconciliation import (
    CheckpointObservationIncompatible,
    DurableCheckpoint,
    candidate_map,
    checkpoint_transition,
    reconcile_checkpoint_frontier,
)

RUN_ID = "run-frontier-contract"
NOW = datetime(2026, 7, 18, tzinfo=UTC)


def _commit(
    task_id: str,
    *,
    graph_step: int = 1,
    node_id: str = "Market Analyst",
    business_delta_sha256: str = "a" * 64,
    turn_id: str | None = None,
    tool_call_ids: tuple[str, ...] = (),
) -> ObservationCommitV1:
    return ObservationCommitV1(
        serializer_version=SERIALIZER_VERSION,
        projection_version=BUSINESS_PROJECTION_VERSION,
        agent_state_schema_sha256=AGENT_STATE_SCHEMA_SHA256,
        task_kind="role",
        graph_task_id=task_id,
        graph_step=graph_step,
        business_delta_sha256=business_delta_sha256,
        node_id=node_id,
        turn_id=turn_id,
        tool_call_ids=tool_call_ids,
    )


def _event(sequence: int, event_type: str, payload: dict[str, Any]) -> PersistedEvent:
    return PersistedEvent.from_draft(
        RunEventDraft(RUN_ID, event_type, payload),
        sequence,
        NOW,
    )


def _candidate_event(
    sequence: int,
    commit: ObservationCommitV1,
    **payload_overrides: Any,
) -> PersistedEvent:
    payload: dict[str, Any] = {
        "observation_commit": commit.as_dict(),
        "graph_step": commit.graph_step,
        "node_id": commit.node_id or "__input__",
        "business_delta_artifact_id": f"artifact:{commit.business_delta_sha256}",
        "media_type": "application/json",
        "content_sha256": commit.business_delta_sha256,
    }
    payload.update(payload_overrides)
    return _event(sequence, "graph.task_output_ready", payload)


def _checkpoint_tuple(
    checkpoint_id: str,
    graph_step: int,
    channel_values: dict[str, Any] | None = None,
    *,
    pending_writes: tuple[tuple[Any, ...], ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        config={"configurable": {"checkpoint_id": checkpoint_id}},
        checkpoint={
            "id": checkpoint_id,
            "channel_values": dict(channel_values or {}),
        },
        metadata={"step": graph_step},
        pending_writes=pending_writes,
    )


def _durable(
    checkpoint_id: str,
    graph_step: int,
    channel_values: dict[str, Any] | None = None,
    *,
    pending_writes: tuple[tuple[Any, ...], ...] = (),
) -> DurableCheckpoint:
    return DurableCheckpoint.from_checkpoint_tuple(
        _checkpoint_tuple(
            checkpoint_id,
            graph_step,
            channel_values,
            pending_writes=pending_writes,
        )
    )


def _values(
    *,
    market_report: str = "unchanged",
    commits: tuple[ObservationCommitV1, ...] = (),
) -> dict[str, Any]:
    values: dict[str, Any] = {"market_report": market_report}
    if commits:
        values[RESERVED_OBSERVATION_FIELD] = {
            commit.graph_task_id: commit.as_dict() for commit in commits
        }
    return values


def _checkpoint_event(
    sequence: int,
    checkpoint: DurableCheckpoint,
    commits: tuple[ObservationCommitV1, ...] = (),
    **payload_overrides: Any,
) -> PersistedEvent:
    payload: dict[str, Any] = {
        "graph_step": checkpoint.graph_step,
        "applied_task_ids": [commit.graph_task_id for commit in commits],
        "state_sha256": checkpoint.state_sha256,
        "next_nodes": list(checkpoint.next_nodes),
        "checkpoint_id": checkpoint.checkpoint_id,
        "mutation": bool(commits),
        "barrier_only": not commits,
        "observation_commits": [commit.as_dict() for commit in commits],
    }
    payload.update(payload_overrides)
    return _event(sequence, "graph.checkpoint_committed", payload)


def _task_started_event(
    sequence: int,
    commit: ObservationCommitV1,
) -> PersistedEvent:
    return _event(
        sequence,
        "graph.task_started",
        {
            "graph_task_id": commit.graph_task_id,
            "graph_step": commit.graph_step,
            "node_id": commit.node_id or "__input__",
        },
    )


def _assert_category(
    exc: pytest.ExceptionInfo[CheckpointObservationIncompatible],
    category: str,
) -> None:
    assert category in exc.value.categories


def test_commit_map_diff_applies_only_new_tokens() -> None:
    old = _commit("task-old", graph_step=1, business_delta_sha256="1" * 64)
    new = _commit("task-new", graph_step=2, business_delta_sha256="2" * 64)
    parent_tuple = _checkpoint_tuple("cp-parent", 1, _values(commits=(old,)))
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        2,
        _values(market_report="new report", commits=(old, new)),
    )
    parent = DurableCheckpoint.from_checkpoint_tuple(parent_tuple)
    events = (
        _candidate_event(1, old),
        _candidate_event(2, new),
        _checkpoint_event(3, parent, (old,)),
    )

    plan = reconcile_checkpoint_frontier(events, latest_tuple, parent_tuple)

    assert plan.missing_checkpoint_transition is not None
    assert plan.missing_checkpoint_transition.applied_task_ids == ("task-new",)
    assert plan.missing_checkpoint_transition.mutation is True
    assert plan.missing_checkpoint_transition.barrier_only is False
    assert plan.committed_task_ids == ("task-old", "task-new")
    assert plan.status_by_task == {
        "task-old": "committed",
        "task-new": "committed",
    }


def test_commit_token_removal_is_incompatible() -> None:
    commit = _commit("task-1")
    parent = _durable("cp-parent", 0, _values(commits=(commit,)))
    current = _durable("cp-current", 1, _values())

    with pytest.raises(CheckpointObservationIncompatible) as exc:
        checkpoint_transition(current, parent, {})

    _assert_category(exc, "commit_token_removed")


def test_existing_commit_token_cannot_change() -> None:
    original = _commit("task-1", business_delta_sha256="1" * 64)
    changed = _commit("task-1", business_delta_sha256="2" * 64)
    parent = _durable("cp-parent", 0, _values(commits=(original,)))
    current = _durable("cp-current", 1, _values(commits=(changed,)))

    with pytest.raises(CheckpointObservationIncompatible) as exc:
        checkpoint_transition(current, parent, {})

    _assert_category(exc, "commit_token_changed")


def test_paired_pending_business_write_is_pending_apply() -> None:
    commit = _commit("task-pending")
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(),
        pending_writes=(
            (commit.graph_task_id, "market_report", "pending report"),
            (
                commit.graph_task_id,
                RESERVED_OBSERVATION_FIELD,
                {commit.graph_task_id: commit.as_dict()},
            ),
        ),
    )

    plan = reconcile_checkpoint_frontier(
        (_candidate_event(1, commit),),
        latest_tuple,
        parent_tuple,
    )

    assert plan.pending_apply_task_ids == (commit.graph_task_id,)
    assert plan.status_by_task[commit.graph_task_id] == "pending_apply"
    assert plan.committed_task_ids == ()
    assert plan.abandoned_task_ids == ()


def test_unpaired_pending_business_write_is_incompatible() -> None:
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(),
        pending_writes=(("task-pending", "market_report", "pending report"),),
    )

    with pytest.raises(CheckpointObservationIncompatible) as exc:
        reconcile_checkpoint_frontier((), latest_tuple, parent_tuple)

    assert {
        "pending_business_write_without_commit",
        "tokenless_pending_business_write",
    } & set(exc.value.categories)


def test_uncommitted_candidate_is_abandoned() -> None:
    commit = _commit("task-tail")
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple("cp-latest", 1, _values())

    plan = reconcile_checkpoint_frontier(
        (_task_started_event(1, commit), _candidate_event(2, commit)),
        latest_tuple,
        parent_tuple,
    )

    assert plan.abandoned_task_ids == (commit.graph_task_id,)
    assert plan.status_by_task[commit.graph_task_id] == "abandoned"
    drafts = plan.append_only_drafts(RUN_ID)
    abandoned = next(draft for draft in drafts if draft.type == "graph.task_abandoned")
    assert abandoned.payload["reason"] == "checkpoint_not_committed"


def test_retried_task_can_commit_new_candidate_after_abandoned_attempt() -> None:
    first = _commit("task-retried", business_delta_sha256="1" * 64)
    retried = _commit("task-retried", business_delta_sha256="2" * 64)
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(market_report="retried", commits=(retried,)),
    )
    events = (
        _task_started_event(1, first),
        _candidate_event(2, first),
        _event(
            3,
            "graph.task_abandoned",
            {
                "graph_task_id": first.graph_task_id,
                "graph_step": first.graph_step,
                "node_id": first.node_id,
                "reason": "checkpoint_not_committed",
            },
        ),
        _candidate_event(4, retried),
    )

    plan = reconcile_checkpoint_frontier(events, latest_tuple, None)

    assert plan.committed_task_ids == (retried.graph_task_id,)
    assert plan.abandoned_task_ids == ()


def test_repeated_abandonment_cancels_each_reused_tool_request_by_sequence() -> None:
    first = _commit(
        "task-retried",
        business_delta_sha256="1" * 64,
        turn_id="turn-1",
        tool_call_ids=("call-price",),
    )
    retried = _commit(
        "task-retried",
        business_delta_sha256="2" * 64,
        turn_id="turn-1",
        tool_call_ids=("call-price",),
    )
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple("cp-latest", 1, _values())

    def requested(sequence: int) -> PersistedEvent:
        return _event(
            sequence,
            "tool.requested",
            {
                "turn_id": "turn-1",
                "graph_task_id": "task-retried",
                "attempt_id": f"attempt-{sequence}",
                "tool_call_id": "call-price",
                "tool_name": "lookup_price",
                "arguments": {"symbol": "AAPL"},
            },
        )

    events = (
        _task_started_event(1, first),
        _candidate_event(2, first),
        requested(3),
        _event(
            4,
            "graph.task_abandoned",
            {
                "graph_task_id": first.graph_task_id,
                "graph_step": first.graph_step,
                "node_id": first.node_id,
                "reason": "checkpoint_not_committed",
            },
        ),
        _event(
            5,
            "tool.cancelled",
            {
                "turn_id": "turn-1",
                "graph_task_id": "task-retried",
                "attempt_id": "attempt-3",
                "tool_call_id": "call-price",
                "tool_name": "lookup_price",
                "reason": "checkpoint_not_committed",
            },
        ),
        _candidate_event(6, retried),
        requested(7),
    )

    plan = reconcile_checkpoint_frontier(events, latest_tuple, parent_tuple)
    cancellations = [
        draft
        for draft in plan.append_only_drafts(RUN_ID)
        if draft.type == "tool.cancelled"
    ]

    assert len(cancellations) == 1
    assert cancellations[0].payload["attempt_id"] == "attempt-7"


def test_tokenless_unchanged_checkpoint_is_barrier_only() -> None:
    parent = _durable("cp-parent", 4, _values())
    current = _durable("cp-current", 5, _values())

    transition = checkpoint_transition(current, parent, {})

    assert transition.applied_task_ids == ()
    assert transition.mutation is False
    assert transition.barrier_only is True


def test_tokenless_business_state_change_is_incompatible() -> None:
    parent = _durable("cp-parent", 0, _values(market_report="before"))
    current = _durable("cp-current", 1, _values(market_report="after"))

    with pytest.raises(CheckpointObservationIncompatible) as exc:
        checkpoint_transition(current, parent, {})

    _assert_category(exc, "tokenless_business_state_change")


def test_tokenless_checkpoint_cannot_consume_parent_business_write() -> None:
    parent = _durable(
        "cp-parent",
        0,
        _values(),
        pending_writes=(("task-tokenless", "market_report", "write"),),
    )
    current = _durable("cp-current", 1, _values())

    with pytest.raises(CheckpointObservationIncompatible):
        checkpoint_transition(current, parent, {})


def test_durable_token_must_exactly_match_candidate_token() -> None:
    candidate_commit = _commit("task-1", business_delta_sha256="1" * 64)
    durable_commit = _commit("task-1", business_delta_sha256="2" * 64)
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(commits=(durable_commit,)),
    )

    with pytest.raises(CheckpointObservationIncompatible) as exc:
        reconcile_checkpoint_frontier(
            (_candidate_event(1, candidate_commit),),
            latest_tuple,
            None,
        )

    _assert_category(exc, "task_candidate_token_mismatch")


@pytest.mark.parametrize(
    ("payload_override", "bad_value"),
    (
        ("graph_step", 999),
        ("node_id", "Bear Researcher"),
        ("content_sha256", "f" * 64),
    ),
)
def test_candidate_envelope_must_match_embedded_commit(
    payload_override: str,
    bad_value: Any,
) -> None:
    commit = _commit("task-1")

    with pytest.raises(CheckpointObservationIncompatible):
        candidate_map(
            (
                _candidate_event(
                    1,
                    commit,
                    **{payload_override: bad_value},
                ),
            )
        )


def test_existing_checkpoint_marker_is_idempotent() -> None:
    commit = _commit("task-1")
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(market_report="report", commits=(commit,)),
    )
    latest = DurableCheckpoint.from_checkpoint_tuple(latest_tuple)
    events = (
        _candidate_event(1, commit),
        _checkpoint_event(2, latest, (commit,)),
    )

    plan = reconcile_checkpoint_frontier(events, latest_tuple, parent_tuple)

    assert plan.missing_checkpoint_transition is None
    assert plan.committed_task_ids == (commit.graph_task_id,)
    assert plan.append_only_drafts(RUN_ID) == ()


@pytest.mark.parametrize(
    ("payload_override", "bad_value"),
    (
        ("mutation", False),
        ("barrier_only", True),
        ("observation_commits", []),
    ),
)
def test_existing_checkpoint_marker_conflict_is_incompatible(
    payload_override: str,
    bad_value: Any,
) -> None:
    commit = _commit("task-1")
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(market_report="report", commits=(commit,)),
    )
    latest = DurableCheckpoint.from_checkpoint_tuple(latest_tuple)
    events = (
        _candidate_event(1, commit),
        _checkpoint_event(
            2,
            latest,
            (commit,),
            **{payload_override: bad_value},
        ),
    )

    with pytest.raises(CheckpointObservationIncompatible):
        reconcile_checkpoint_frontier(events, latest_tuple, parent_tuple)


def test_existing_checkpoint_marker_core_field_conflict_is_incompatible() -> None:
    commit = _commit("task-1")
    parent_tuple = _checkpoint_tuple("cp-parent", 0, _values())
    latest_tuple = _checkpoint_tuple(
        "cp-latest",
        1,
        _values(market_report="report", commits=(commit,)),
    )
    latest = DurableCheckpoint.from_checkpoint_tuple(latest_tuple)
    events = (
        _candidate_event(1, commit),
        _checkpoint_event(2, latest, (commit,), state_sha256="f" * 64),
    )

    with pytest.raises(CheckpointObservationIncompatible) as exc:
        reconcile_checkpoint_frontier(events, latest_tuple, parent_tuple)

    _assert_category(exc, "checkpoint_event_content_mismatch")
