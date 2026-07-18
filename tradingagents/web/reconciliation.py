"""Strict append-only reconciliation of observation candidates and graph durability."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    APPLICATION_STATE_FIELDS,
    BUSINESS_PROJECTION_VERSION,
    RESERVED_OBSERVATION_FIELD,
    SERIALIZER_VERSION,
    BusinessStateProjectionV1,
    canonical_sha256,
    pending_writes_touch_business_state,
)
from tradingagents.observability.events import (
    ObservationCommitV1,
    PersistedEvent,
    RunEventDraft,
)

ApplicationStatus = Literal["committed", "pending_apply", "abandoned"]


class CheckpointObservationIncompatible(RuntimeError):
    """The SQLite frontier and append-only observation history cannot be joined."""

    def __init__(self, categories: tuple[str, ...]):
        self.categories = tuple(dict.fromkeys(categories))
        super().__init__(
            "checkpoint_observation_incompatible: " + ", ".join(self.categories)
        )


@dataclass(frozen=True)
class TaskCandidate:
    graph_task_id: str
    graph_step: int
    node_id: str
    commit: ObservationCommitV1
    event_id: str
    sequence: int
    artifact_id: str
    content_sha256: str


@dataclass(frozen=True)
class TaskStart:
    graph_task_id: str
    graph_step: int
    node_id: str
    event_id: str


@dataclass(frozen=True)
class DurableCheckpoint:
    checkpoint_id: str
    graph_step: int
    channel_values: Mapping[str, Any]
    state_sha256: str
    next_nodes: tuple[str, ...]
    pending_writes: tuple[tuple[Any, ...], ...] = ()
    updated_channels: tuple[str, ...] = ()

    @classmethod
    def from_stream_payload(cls, payload: Mapping[str, Any]) -> DurableCheckpoint:
        config = payload.get("config")
        metadata = payload.get("metadata")
        values = payload.get("values")
        if not isinstance(config, Mapping) or not isinstance(metadata, Mapping):
            raise CheckpointObservationIncompatible(("checkpoint_shape",))
        configurable = config.get("configurable")
        checkpoint_id = (
            configurable.get("checkpoint_id")
            if isinstance(configurable, Mapping)
            else None
        )
        graph_step = metadata.get("step")
        if (
            not isinstance(checkpoint_id, str)
            or not checkpoint_id
            or not isinstance(graph_step, int)
            or not isinstance(values, Mapping)
        ):
            raise CheckpointObservationIncompatible(("checkpoint_shape",))
        next_nodes = payload.get("next") or ()
        if not isinstance(next_nodes, (list, tuple)) or any(
            not isinstance(node, str) for node in next_nodes
        ):
            raise CheckpointObservationIncompatible(("checkpoint_shape",))
        return cls(
            checkpoint_id=checkpoint_id,
            graph_step=graph_step,
            channel_values=values,
            state_sha256=BusinessStateProjectionV1.from_channel_values(values).sha256,
            next_nodes=tuple(next_nodes),
            updated_channels=_updated_channels_from_metadata(metadata),
        )

    @classmethod
    def from_checkpoint_tuple(
        cls,
        value: Any,
        *,
        next_nodes: Sequence[str] | None = None,
    ) -> DurableCheckpoint:
        if value is None:
            raise CheckpointObservationIncompatible(("checkpoint_missing",))
        config = getattr(value, "config", None)
        checkpoint = getattr(value, "checkpoint", None)
        metadata = getattr(value, "metadata", None)
        if not all(isinstance(item, Mapping) for item in (config, checkpoint, metadata)):
            raise CheckpointObservationIncompatible(("checkpoint_shape",))
        configurable = config.get("configurable")
        checkpoint_id = (
            configurable.get("checkpoint_id")
            if isinstance(configurable, Mapping)
            else None
        ) or checkpoint.get("id")
        graph_step = metadata.get("step")
        channel_values = checkpoint.get("channel_values")
        pending_writes = getattr(value, "pending_writes", ()) or ()
        if (
            not isinstance(checkpoint_id, str)
            or not checkpoint_id
            or not isinstance(graph_step, int)
            or not isinstance(channel_values, Mapping)
            or not isinstance(pending_writes, (list, tuple))
        ):
            raise CheckpointObservationIncompatible(("checkpoint_shape",))
        return cls(
            checkpoint_id=checkpoint_id,
            graph_step=graph_step,
            channel_values=channel_values,
            state_sha256=BusinessStateProjectionV1.from_channel_values(
                channel_values
            ).sha256,
            next_nodes=tuple(next_nodes)
            if next_nodes is not None
            else _next_nodes_from_channel_values(channel_values),
            pending_writes=tuple(tuple(write) for write in pending_writes),
            updated_channels=_updated_channels_from_metadata(metadata),
        )


@dataclass(frozen=True)
class CheckpointTransition:
    checkpoint: DurableCheckpoint
    applied_commits: tuple[ObservationCommitV1, ...]
    mutation: bool
    barrier_only: bool
    parent_checkpoint_id: str | None = None

    @property
    def applied_task_ids(self) -> tuple[str, ...]:
        return tuple(commit.graph_task_id for commit in self.applied_commits)

    def event_draft(self, run_id: str) -> RunEventDraft:
        return RunEventDraft(
            run_id,
            "graph.checkpoint_committed",
            {
                "graph_step": self.checkpoint.graph_step,
                "applied_task_ids": list(self.applied_task_ids),
                "state_sha256": self.checkpoint.state_sha256,
                "next_nodes": list(self.checkpoint.next_nodes),
                "checkpoint_id": self.checkpoint.checkpoint_id,
                "mutation": self.mutation,
                "barrier_only": self.barrier_only,
                "parent_checkpoint_id": self.parent_checkpoint_id,
                "reconciled": False,
                "observation_commits": [
                    commit.as_dict() for commit in self.applied_commits
                ],
            },
            status="committed",
        )


@dataclass(frozen=True)
class ReconciliationPlan:
    base_sequence: int
    latest_checkpoint_id: str
    latest_transition: CheckpointTransition
    missing_checkpoint_transition: CheckpointTransition | None
    committed_task_ids: tuple[str, ...]
    pending_apply_task_ids: tuple[str, ...]
    abandoned_task_ids: tuple[str, ...]
    candidates: Mapping[str, TaskCandidate]
    starts: Mapping[str, TaskStart]
    pending_commits: Mapping[str, ObservationCommitV1]
    compensation_drafts: tuple[RunEventDraft, ...]

    @property
    def status_by_task(self) -> dict[str, ApplicationStatus]:
        return {
            **dict.fromkeys(self.committed_task_ids, "committed"),
            **dict.fromkeys(self.pending_apply_task_ids, "pending_apply"),
            **dict.fromkeys(self.abandoned_task_ids, "abandoned"),
        }

    def append_only_drafts(self, run_id: str) -> tuple[RunEventDraft, ...]:
        drafts: list[RunEventDraft] = []
        if self.missing_checkpoint_transition is not None:
            drafts.append(self.missing_checkpoint_transition.event_draft(run_id))
        for task_id in self.abandoned_task_ids:
            candidate = self.candidates.get(task_id)
            started = self.starts.get(task_id)
            if started is None and candidate is not None:
                started = TaskStart(
                    task_id,
                    candidate.graph_step,
                    candidate.node_id,
                    candidate.event_id,
                )
            if started is None:
                raise CheckpointObservationIncompatible(("abandoned_task_missing",))
            drafts.append(
                RunEventDraft(
                    run_id,
                    "graph.task_abandoned",
                    {
                        "graph_task_id": task_id,
                        "graph_step": started.graph_step,
                        "node_id": started.node_id,
                        "reason": "checkpoint_not_committed",
                    },
                    node_id=(candidate.commit.node_id if candidate else started.node_id),
                    status="abandoned",
                )
            )
        drafts.extend(self.compensation_drafts)
        return tuple(drafts)


def checkpoint_transition(
    current: DurableCheckpoint,
    parent: DurableCheckpoint | None,
    candidates: Mapping[str, TaskCandidate],
) -> CheckpointTransition:
    current_commits = observation_commit_map(current.channel_values)
    parent_commits = observation_commit_map(parent.channel_values) if parent else {}
    if set(parent_commits) - set(current_commits):
        raise CheckpointObservationIncompatible(("commit_token_removed",))
    changed_existing = {
        task_id
        for task_id in set(parent_commits) & set(current_commits)
        if canonical_sha256(parent_commits[task_id].as_dict())
        != canonical_sha256(current_commits[task_id].as_dict())
    }
    if changed_existing:
        raise CheckpointObservationIncompatible(("commit_token_changed",))
    new_task_ids = tuple(sorted(set(current_commits) - set(parent_commits)))
    applied = tuple(
        _match_candidate(current_commits[task_id], candidates) for task_id in new_task_ids
    )
    applied_commits = tuple(candidate.commit for candidate in applied)

    if not applied_commits:
        if parent is None:
            projection = BusinessStateProjectionV1.from_channel_values(
                current.channel_values
            )
            if current.graph_step != -1 or projection.values:
                raise CheckpointObservationIncompatible(
                    ("unproven_initial_tokenless_checkpoint",)
                )
            return CheckpointTransition(current, (), False, True, None)
        if current.state_sha256 != parent.state_sha256:
            raise CheckpointObservationIncompatible(
                ("tokenless_business_state_change",)
            )
        if set(current.updated_channels) & set(APPLICATION_STATE_FIELDS):
            raise CheckpointObservationIncompatible(
                ("tokenless_application_channel_update",)
            )
        if pending_writes_touch_business_state(parent.pending_writes):
            raise CheckpointObservationIncompatible(
                ("tokenless_pending_business_write",)
            )
        return CheckpointTransition(
            current,
            (),
            False,
            True,
            parent.checkpoint_id,
        )
    transition = CheckpointTransition(
        current,
        applied_commits,
        True,
        False,
        parent.checkpoint_id if parent is not None else None,
    )
    _validate_checkpoint_routes(transition)
    return transition


def reconcile_checkpoint_frontier(
    events: Sequence[PersistedEvent],
    latest_tuple: Any,
    parent_tuple: Any | None,
    *,
    latest_next_nodes: Sequence[str] | None = None,
    parent_next_nodes: Sequence[str] | None = None,
    read_artifact: Callable[[str], bytes] | None = None,
) -> ReconciliationPlan:
    starts = task_start_map(events)
    candidates = candidate_map(events, read_artifact=read_artifact)
    latest = DurableCheckpoint.from_checkpoint_tuple(
        latest_tuple,
        next_nodes=latest_next_nodes,
    )
    parent = (
        DurableCheckpoint.from_checkpoint_tuple(
            parent_tuple,
            next_nodes=parent_next_nodes,
        )
        if parent_tuple is not None
        else None
    )
    _validate_started_candidate_pairs(starts, candidates)
    transition = checkpoint_transition(latest, parent, candidates)
    checkpoint_events = [
        event for event in events if event.type == "graph.checkpoint_committed"
    ]
    committed_ids = _committed_task_ids(checkpoint_events)
    abandoned_existing = _abandoned_task_ids(events)
    missing_transition = _missing_checkpoint_transition(
        checkpoint_events,
        latest,
        parent,
        transition,
    )
    if missing_transition is not None:
        committed_ids = tuple(
            dict.fromkeys((*committed_ids, *missing_transition.applied_task_ids))
        )

    pending_commits = pending_observation_commit_map(latest.pending_writes)
    durable_commits = observation_commit_map(latest.channel_values)
    for task_id, commit in pending_commits.items():
        if task_id in committed_ids or task_id in durable_commits:
            raise CheckpointObservationIncompatible(("pending_task_already_committed",))
        _match_candidate(commit, candidates)

    for commit in durable_commits.values():
        _match_candidate(commit, candidates)

    pending_ids = tuple(sorted(pending_commits))
    if abandoned_existing & (set(committed_ids) | set(pending_ids)):
        raise CheckpointObservationIncompatible(("abandoned_task_is_durable",))
    tails = (
        set(starts) | set(candidates)
    ) - set(committed_ids) - set(pending_ids) - abandoned_existing
    abandoned = tuple(sorted(tails))
    _validate_durable_commit_coverage(latest, committed_ids)
    compensation = _abandonment_compensation(events, abandoned)
    return ReconciliationPlan(
        base_sequence=max((event.sequence for event in events), default=0),
        latest_checkpoint_id=latest.checkpoint_id,
        latest_transition=transition,
        missing_checkpoint_transition=missing_transition,
        committed_task_ids=tuple(committed_ids),
        pending_apply_task_ids=pending_ids,
        abandoned_task_ids=abandoned,
        candidates=candidates,
        starts=starts,
        pending_commits=pending_commits,
        compensation_drafts=compensation,
    )


def apply_reconciliation_plan(
    store: Any,
    run_id: str,
    plan: ReconciliationPlan,
    *,
    current_checkpoint_id: Callable[[], str | None] | None = None,
    observer: Any | None = None,
) -> tuple[PersistedEvent, ...]:
    """Append a fully validated plan while rejecting event/checkpoint drift."""
    sink = observer.emit if observer is not None else store.append_event
    persisted: list[PersistedEvent] = []
    with store.lock_for(run_id):
        events = store.read_events(run_id)
        sequence = events[-1].sequence if events else 0
        if sequence != plan.base_sequence:
            raise CheckpointObservationIncompatible(("event_frontier_drift",))
        if (
            current_checkpoint_id is not None
            and current_checkpoint_id() != plan.latest_checkpoint_id
        ):
            raise CheckpointObservationIncompatible(("checkpoint_frontier_drift",))
        for draft in plan.append_only_drafts(run_id):
            persisted.append(sink(draft))
    if observer is not None and persisted:
        refresh = getattr(observer, "refresh_from_events", None)
        if callable(refresh):
            refresh()
    return tuple(persisted)


def task_start_map(events: Sequence[PersistedEvent]) -> dict[str, TaskStart]:
    starts: dict[str, TaskStart] = {}
    for event in events:
        if event.type != "graph.task_started":
            continue
        task_id = event.payload.get("graph_task_id")
        graph_step = event.payload.get("graph_step")
        node_id = event.payload.get("node_id")
        if (
            not isinstance(task_id, str)
            or not task_id
            or not isinstance(graph_step, int)
            or graph_step < 0
            or not isinstance(node_id, str)
            or not node_id
        ):
            raise CheckpointObservationIncompatible(("task_started_shape",))
        if task_id in starts:
            raise CheckpointObservationIncompatible(("duplicate_task_started",))
        starts[task_id] = TaskStart(task_id, graph_step, node_id, event.event_id)
    return starts


def candidate_map(
    events: Sequence[PersistedEvent],
    *,
    read_artifact: Callable[[str], bytes] | None = None,
) -> dict[str, TaskCandidate]:
    candidates: dict[str, TaskCandidate] = {}
    abandoned_sequences: dict[str, list[int]] = {}
    for event in events:
        if event.type == "graph.task_abandoned":
            task_id = event.payload.get("graph_task_id")
            if isinstance(task_id, str) and task_id:
                abandoned_sequences.setdefault(task_id, []).append(event.sequence)
    for event in events:
        if event.type != "graph.task_output_ready":
            continue
        raw = event.payload.get("observation_commit")
        commit = _parse_commit(raw)
        task_id = commit.graph_task_id
        previous = candidates.get(task_id)
        if previous is not None and not any(
            previous.sequence < abandoned_sequence < event.sequence
            for abandoned_sequence in abandoned_sequences.get(task_id, ())
        ):
            raise CheckpointObservationIncompatible(("duplicate_task_candidate",))
        event_step = event.payload.get("graph_step")
        event_node = event.payload.get("node_id")
        artifact_id = event.payload.get("business_delta_artifact_id")
        content_sha256 = event.payload.get("content_sha256")
        expected_node = commit.node_id or "__input__"
        if (
            event_step != commit.graph_step
            or event_node != expected_node
            or not isinstance(artifact_id, str)
            or not isinstance(content_sha256, str)
            or content_sha256 != commit.business_delta_sha256
            or artifact_id.rsplit(":", 1)[-1] != content_sha256
        ):
            raise CheckpointObservationIncompatible(("task_candidate_content",))
        if read_artifact is not None:
            try:
                content = read_artifact(artifact_id)
            except Exception as exc:
                raise CheckpointObservationIncompatible(
                    ("task_candidate_artifact",)
                ) from exc
            if hashlib.sha256(content).hexdigest() != content_sha256:
                raise CheckpointObservationIncompatible(
                    ("task_candidate_artifact",)
                )
        candidates[task_id] = TaskCandidate(
            graph_task_id=task_id,
            graph_step=commit.graph_step,
            node_id=str(event.payload.get("node_id") or commit.node_id or "__input__"),
            commit=commit,
            event_id=event.event_id,
            sequence=event.sequence,
            artifact_id=artifact_id,
            content_sha256=content_sha256,
        )
    return candidates


def observation_commit_map(
    channel_values: Mapping[str, Any],
) -> dict[str, ObservationCommitV1]:
    raw = channel_values.get(RESERVED_OBSERVATION_FIELD, {})
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise CheckpointObservationIncompatible(("commit_map_shape",))
    commits: dict[str, ObservationCommitV1] = {}
    for task_id, value in raw.items():
        if not isinstance(task_id, str) or not task_id:
            raise CheckpointObservationIncompatible(("commit_map_shape",))
        commit = _parse_commit(value)
        if commit.graph_task_id != task_id:
            raise CheckpointObservationIncompatible(("commit_task_id_mismatch",))
        commits[task_id] = commit
    return commits


def _validate_started_candidate_pairs(
    starts: Mapping[str, TaskStart],
    candidates: Mapping[str, TaskCandidate],
) -> None:
    for task_id in set(starts) & set(candidates):
        started = starts[task_id]
        candidate = candidates[task_id]
        if (
            started.graph_step != candidate.graph_step
            or started.node_id != candidate.node_id
        ):
            raise CheckpointObservationIncompatible(
                ("task_started_candidate_mismatch",)
            )


def _abandoned_task_ids(events: Sequence[PersistedEvent]) -> set[str]:
    abandoned: dict[str, tuple[int, str, str]] = {}
    abandoned_sequence: dict[str, int] = {}
    latest_candidate_sequence: dict[str, int] = {}
    for event in events:
        if event.type == "graph.task_output_ready":
            raw = event.payload.get("observation_commit")
            if isinstance(raw, Mapping):
                task_id = raw.get("graph_task_id")
                if isinstance(task_id, str) and task_id:
                    latest_candidate_sequence[task_id] = event.sequence
            continue
        if event.type != "graph.task_abandoned":
            continue
        payload = event.payload
        task_id = payload.get("graph_task_id")
        value = (
            payload.get("graph_step"),
            payload.get("node_id"),
            payload.get("reason"),
        )
        if not isinstance(task_id, str) or not task_id:
            raise CheckpointObservationIncompatible(("task_abandoned_shape",))
        previous = abandoned.get(task_id)
        if previous is not None and previous != value:
            raise CheckpointObservationIncompatible(("task_abandoned_conflict",))
        abandoned[task_id] = value
        abandoned_sequence[task_id] = event.sequence
    return {
        task_id
        for task_id in abandoned
        if latest_candidate_sequence.get(task_id, 0)
        <= abandoned_sequence[task_id]
    }


def _committed_task_ids(
    checkpoint_events: Sequence[PersistedEvent],
) -> tuple[str, ...]:
    task_ids: list[str] = []
    for event in checkpoint_events:
        applied = event.payload.get("applied_task_ids")
        if not isinstance(applied, list) or any(
            not isinstance(task_id, str) or not task_id for task_id in applied
        ):
            raise CheckpointObservationIncompatible(("checkpoint_event_shape",))
        task_ids.extend(applied)
    if len(task_ids) != len(set(task_ids)):
        raise CheckpointObservationIncompatible(("task_committed_twice",))
    return tuple(task_ids)


def _abandonment_compensation(
    events: Sequence[PersistedEvent],
    abandoned_task_ids: Sequence[str],
) -> tuple[RunEventDraft, ...]:
    abandoned = set(abandoned_task_ids)
    if not abandoned:
        return ()
    terminal_tools: dict[str, list[PersistedEvent]] = {}
    for event in events:
        if event.type not in {"tool.committed", "tool.cancelled"}:
            continue
        terminal_tools.setdefault(str(event.payload["tool_call_id"]), []).append(event)
    drafts: list[RunEventDraft] = []
    for event in events:
        if event.type != "tool.requested":
            continue
        payload = event.payload
        task_id = str(payload["graph_task_id"])
        if task_id not in abandoned:
            continue
        tool_call_id = str(payload["tool_call_id"])
        later_terminals = [
            terminal
            for terminal in terminal_tools.get(tool_call_id, ())
            if terminal.sequence > event.sequence
        ]
        if any(terminal.type == "tool.committed" for terminal in later_terminals):
            raise CheckpointObservationIncompatible(
                ("abandoned_tool_already_committed",)
            )
        if any(terminal.type == "tool.cancelled" for terminal in later_terminals):
            continue
        drafts.append(
            RunEventDraft(
                event.run_id,
                "tool.cancelled",
                {
                    "turn_id": payload["turn_id"],
                    "graph_task_id": task_id,
                    "attempt_id": payload["attempt_id"],
                    "tool_call_id": tool_call_id,
                    "tool_name": payload["tool_name"],
                    "reason": "checkpoint_not_committed",
                },
                team_id=event.team_id,
                actor_id=event.actor_id,
                node_id=event.node_id,
                parent_event_id=event.event_id,
                status="cancelled",
            )
        )
    return tuple(drafts)


def pending_observation_commit_map(
    pending_writes: Sequence[tuple[Any, ...]],
) -> dict[str, ObservationCommitV1]:
    commits: dict[str, ObservationCommitV1] = {}
    business_write_tasks: set[str] = set()
    for write in pending_writes:
        if len(write) < 3:
            raise CheckpointObservationIncompatible(("pending_write_shape",))
        task_id, channel, value = write[0], write[1], write[2]
        if not isinstance(task_id, str) or not isinstance(channel, str):
            raise CheckpointObservationIncompatible(("pending_write_shape",))
        if channel == RESERVED_OBSERVATION_FIELD:
            if not isinstance(value, Mapping):
                raise CheckpointObservationIncompatible(("pending_commit_shape",))
            for commit_task_id, raw_commit in value.items():
                commit = _parse_commit(raw_commit)
                if commit_task_id != commit.graph_task_id or task_id != commit.graph_task_id:
                    raise CheckpointObservationIncompatible(
                        ("pending_commit_task_id_mismatch",)
                    )
                if commit.graph_task_id in commits:
                    raise CheckpointObservationIncompatible(
                        ("duplicate_pending_commit",)
                    )
                commits[commit.graph_task_id] = commit
        elif pending_writes_touch_business_state((write,)):
            business_write_tasks.add(task_id)
    if business_write_tasks - set(commits):
        raise CheckpointObservationIncompatible(
            ("pending_business_write_without_commit",)
        )
    return commits


def _parse_commit(value: Any) -> ObservationCommitV1:
    if not isinstance(value, Mapping):
        raise CheckpointObservationIncompatible(("commit_token_shape",))
    expected_fields = {
        "serializer_version",
        "projection_version",
        "agent_state_schema_sha256",
        "task_kind",
        "graph_task_id",
        "graph_step",
        "business_delta_sha256",
        "node_id",
        "turn_id",
        "tool_call_ids",
    }
    if set(value) != expected_fields:
        raise CheckpointObservationIncompatible(("commit_token_shape",))
    normalized = dict(value)
    tool_call_ids = normalized.get("tool_call_ids")
    if not isinstance(tool_call_ids, (list, tuple)) or any(
        not isinstance(tool_call_id, str) or not tool_call_id
        for tool_call_id in tool_call_ids
    ):
        raise CheckpointObservationIncompatible(("commit_token_shape",))
    normalized["tool_call_ids"] = tuple(tool_call_ids)
    try:
        commit = ObservationCommitV1(**normalized)
    except (TypeError, ValueError) as exc:
        raise CheckpointObservationIncompatible(("commit_token_shape",)) from exc
    if (
        commit.task_kind not in {"input", "role", "tool", "maintenance"}
        or (commit.node_id is not None and not isinstance(commit.node_id, str))
        or (commit.turn_id is not None and not isinstance(commit.turn_id, str))
    ):
        raise CheckpointObservationIncompatible(("commit_token_shape",))
    if (
        commit.serializer_version != SERIALIZER_VERSION
        or commit.projection_version != BUSINESS_PROJECTION_VERSION
        or commit.agent_state_schema_sha256 != AGENT_STATE_SCHEMA_SHA256
    ):
        raise CheckpointObservationIncompatible(("commit_token_schema",))
    return commit


def _match_candidate(
    commit: ObservationCommitV1,
    candidates: Mapping[str, TaskCandidate],
) -> TaskCandidate:
    candidate = candidates.get(commit.graph_task_id)
    if candidate is None:
        raise CheckpointObservationIncompatible(("missing_task_candidate",))
    if canonical_sha256(candidate.commit.as_dict()) != canonical_sha256(commit.as_dict()):
        raise CheckpointObservationIncompatible(("task_candidate_token_mismatch",))
    return candidate


def _missing_checkpoint_transition(
    checkpoint_events: Sequence[PersistedEvent],
    latest: DurableCheckpoint,
    parent: DurableCheckpoint | None,
    transition: CheckpointTransition,
) -> CheckpointTransition | None:
    if not checkpoint_events:
        if parent is not None and observation_commit_map(parent.channel_values):
            raise CheckpointObservationIncompatible(
                ("checkpoint_event_frontier_too_far_behind",)
            )
        return transition
    checkpoint_ids: set[str] = set()
    for event in checkpoint_events:
        checkpoint_id = event.payload.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise CheckpointObservationIncompatible(("checkpoint_event_shape",))
        if checkpoint_id in checkpoint_ids:
            raise CheckpointObservationIncompatible(("duplicate_checkpoint_event",))
        checkpoint_ids.add(checkpoint_id)
    last = checkpoint_events[-1]
    checkpoint_id = last.payload.get("checkpoint_id")
    if checkpoint_id == latest.checkpoint_id:
        _validate_existing_checkpoint_event(last, transition)
        return None
    if parent is not None and checkpoint_id == parent.checkpoint_id:
        _validate_checkpoint_marker_against_durable_state(last, parent)
        return transition
    raise CheckpointObservationIncompatible(("checkpoint_event_frontier_mismatch",))


def _validate_existing_checkpoint_event(
    event: PersistedEvent,
    transition: CheckpointTransition,
) -> None:
    expected = {
        "graph_step": transition.checkpoint.graph_step,
        "applied_task_ids": list(transition.applied_task_ids),
        "state_sha256": transition.checkpoint.state_sha256,
        "next_nodes": list(transition.checkpoint.next_nodes),
        "checkpoint_id": transition.checkpoint.checkpoint_id,
        "mutation": transition.mutation,
        "barrier_only": transition.barrier_only,
    }
    if any(event.payload.get(key) != value for key, value in expected.items()):
        raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))
    raw_commits = event.payload.get("observation_commits")
    if raw_commits is not None:
        if not isinstance(raw_commits, list):
            raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))
        parsed = tuple(_parse_commit(value) for value in raw_commits)
        if tuple(commit.as_dict() for commit in parsed) != tuple(
            commit.as_dict() for commit in transition.applied_commits
        ):
            raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))


def _validate_checkpoint_marker_against_durable_state(
    event: PersistedEvent,
    checkpoint: DurableCheckpoint,
) -> None:
    payload = event.payload
    if (
        payload.get("graph_step") != checkpoint.graph_step
        or payload.get("state_sha256") != checkpoint.state_sha256
        or payload.get("next_nodes") != list(checkpoint.next_nodes)
    ):
        raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))
    applied_ids = payload.get("applied_task_ids")
    if not isinstance(applied_ids, list) or any(
        not isinstance(task_id, str) for task_id in applied_ids
    ):
        raise CheckpointObservationIncompatible(("checkpoint_event_shape",))
    if (
        payload.get("mutation") is not bool(applied_ids)
        or payload.get("barrier_only") is bool(applied_ids)
    ):
        raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))
    durable = observation_commit_map(checkpoint.channel_values)
    if set(applied_ids) - set(durable):
        raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))
    raw_commits = payload.get("observation_commits")
    if raw_commits is not None:
        if not isinstance(raw_commits, list):
            raise CheckpointObservationIncompatible(("checkpoint_event_shape",))
        parsed = tuple(_parse_commit(value) for value in raw_commits)
        if tuple(commit.graph_task_id for commit in parsed) != tuple(applied_ids):
            raise CheckpointObservationIncompatible(("checkpoint_event_content_mismatch",))
        for commit in parsed:
            if canonical_sha256(commit.as_dict()) != canonical_sha256(
                durable[commit.graph_task_id].as_dict()
            ):
                raise CheckpointObservationIncompatible(
                    ("checkpoint_event_content_mismatch",)
                )


def _validate_durable_commit_coverage(
    latest: DurableCheckpoint,
    committed_task_ids: Sequence[str],
) -> None:
    durable_ids = set(observation_commit_map(latest.channel_values))
    if durable_ids - set(committed_task_ids):
        raise CheckpointObservationIncompatible(("durable_task_without_commit_event",))
    if set(committed_task_ids) - durable_ids:
        raise CheckpointObservationIncompatible(("commit_event_without_durable_task",))


def _next_nodes_from_channel_values(values: Mapping[str, Any]) -> tuple[str, ...]:
    prefix = "branch:to:"
    return tuple(
        sorted(
            channel.removeprefix(prefix)
            for channel, value in values.items()
            if isinstance(channel, str)
            and channel.startswith(prefix)
            and value is not None
        )
    )


def _updated_channels_from_metadata(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    writes = metadata.get("writes")
    if not isinstance(writes, Mapping):
        return ()
    channels: set[str] = set()
    for delta in writes.values():
        if isinstance(delta, Mapping):
            channels.update(str(channel) for channel in delta)
    return tuple(sorted(channels))


def _validate_checkpoint_routes(transition: CheckpointTransition) -> None:
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS

    tool_by_role = {
        spec.agent_node: spec.tool_node for spec in ANALYST_NODE_SPECS.values()
    }
    role_by_tool = {tool: role for role, tool in tool_by_role.items()}
    next_nodes = set(transition.checkpoint.next_nodes)
    for commit in transition.applied_commits:
        if commit.task_kind == "role" and commit.tool_call_ids:
            expected = tool_by_role.get(commit.node_id or "")
            if expected is not None and expected not in next_nodes:
                raise CheckpointObservationIncompatible(("role_tool_route_mismatch",))
        if commit.task_kind == "tool":
            expected = role_by_tool.get(commit.node_id or "")
            if expected is not None and expected not in next_nodes:
                raise CheckpointObservationIncompatible(("tool_role_route_mismatch",))
