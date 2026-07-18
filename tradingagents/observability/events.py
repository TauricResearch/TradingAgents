"""Versioned event envelope and immutable relationship contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


EVENT_SCHEMA_VERSION = 1
SHA256_LENGTH = 64


class InvalidEvent(ValueError):
    pass


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f"{name} is required")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != SHA256_LENGTH or any(ch not in "0123456789abcdef" for ch in value):
        raise InvalidEvent(f"{name} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    media_type: str
    content_sha256: str
    byte_size: int
    locator: str

    def __post_init__(self) -> None:
        for name in ("artifact_id", "kind", "media_type", "locator"):
            _require_text(getattr(self, name), name)
        _require_sha256(self.content_sha256, "content_sha256")
        if self.byte_size < 0:
            raise InvalidEvent("byte_size must be non-negative")


@dataclass(frozen=True)
class ObservationCommitV1:
    serializer_version: int
    projection_version: int
    agent_state_schema_sha256: str
    task_kind: Literal["input", "role", "tool", "maintenance"]
    graph_task_id: str
    graph_step: int
    business_delta_sha256: str
    node_id: str | None = None
    turn_id: str | None = None
    tool_call_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.serializer_version < 1 or self.projection_version < 1:
            raise InvalidEvent("serializer and projection versions must be positive")
        _require_sha256(self.agent_state_schema_sha256, "agent_state_schema_sha256")
        _require_sha256(self.business_delta_sha256, "business_delta_sha256")
        _require_text(self.graph_task_id, "graph_task_id")
        if self.graph_step < 0:
            raise InvalidEvent("graph_step must be non-negative")
        if self.task_kind != "input" and not self.node_id:
            raise InvalidEvent(f"node_id is required for {self.task_kind} tasks")
        if len(set(self.tool_call_ids)) != len(self.tool_call_ids):
            raise InvalidEvent("tool_call_ids must be unique and ordered")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


BASE_REQUIRED_PAYLOADS: dict[str, frozenset[str]] = {
    "graph.task_started": frozenset({"graph_task_id", "graph_step", "node_id"}),
    "graph.task_abandoned": frozenset(
        {"graph_task_id", "graph_step", "node_id", "reason"}
    ),
    "graph.task_output_ready": frozenset(
        {
            "observation_commit",
            "graph_step",
            "node_id",
            "business_delta_artifact_id",
            "media_type",
            "content_sha256",
        }
    ),
    "graph.step_applied": frozenset(
        {"graph_step", "applied_task_ids", "state_sha256", "next_nodes"}
    ),
    "graph.checkpoint_committed": frozenset(
        {"graph_step", "applied_task_ids", "state_sha256", "next_nodes", "checkpoint_id"}
    ),
    "role.status_changed": frozenset(
        {"role_instance_id", "previous_status", "new_status", "reason"}
    ),
    "agent.message": frozenset(
        {"turn_id", "graph_task_id", "message_id", "message_kind"}
    ),
    "state.updated": frozenset({"turn_id", "changed_keys"}),
    "report.updated": frozenset({"turn_id", "report_kind", "revision", "artifact_id"}),
    "artifact.written": frozenset(
        {
            "artifact_id",
            "kind",
            "media_type",
            "content_sha256",
            "byte_size",
            "locator",
        }
    ),
}


def required_payload_fields(event_type: str) -> frozenset[str]:
    if event_type.startswith("run."):
        required = {"run_status"}
        if event_type in {"run.completed", "run.failed", "run.cancelled"}:
            required.add("summary")
        if event_type in {"run.interrupted", "run.resumed"}:
            required.add("checkpoint_sequence")
        return frozenset(required)
    if event_type.startswith("turn."):
        required = {
            "role_instance_id",
            "turn_id",
            "graph_task_id",
            "graph_step",
            "turn_index",
            "turn_status",
        }
        if event_type == "turn.output_ready":
            required.add("artifact_id")
        if event_type == "turn.resumed":
            required.add("resumed_from_sequence")
        if event_type in {
            "turn.completed",
            "turn.failed",
            "turn.cancelled",
            "turn.interrupted",
        }:
            required.update({"reason", "duration_ms"})
        return frozenset(required)
    if event_type.startswith("model."):
        required = {
            "turn_id",
            "graph_task_id",
            "attempt_id",
            "model_call_id",
            "provider",
            "model",
            "invocation_path",
        }
        if event_type != "model.started":
            required.update({"duration_ms", "usage"})
        return frozenset(required)
    if event_type.startswith("input."):
        required = {
            "turn_id",
            "graph_task_id",
            "capture_kind",
            "artifact_id",
            "content_sha256",
            "redaction_manifest",
        }
        if event_type == "input.prompt_snapshot":
            required.update({"attempt_id", "model_call_id"})
        return frozenset(required)
    if event_type.startswith("tool."):
        required = {
            "turn_id",
            "graph_task_id",
            "attempt_id",
            "tool_call_id",
            "tool_name",
        }
        if event_type == "tool.requested":
            required.add("arguments")
        elif event_type.startswith("tool.execution_"):
            required.add("tool_execution_id")
        elif event_type == "tool.committed":
            required.add("checkpoint_event_id")
        elif event_type == "tool.cancelled":
            required.add("reason")
        return frozenset(required)
    if event_type.startswith("data.") and event_type != "data.cache_hit":
        required = {
            "turn_id",
            "graph_task_id",
            "vendor_call_id",
            "method",
            "vendor",
            "stage",
            "data_status",
        }
        if event_type != "data.progress":
            required.add("duration_ms")
        return frozenset(required)
    if event_type == "data.cache_hit":
        return frozenset(
            {
                "turn_id",
                "graph_task_id",
                "cache_hit_id",
                "cache_key_sha256",
                "origin_vendor_call_ids",
                "origin_artifacts",
                "age_ms",
            }
        )
    if event_type == "stats.updated":
        return frozenset()
    return BASE_REQUIRED_PAYLOADS.get(event_type, frozenset())


def validate_event_payload(event_type: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise InvalidEvent("payload must be a dict")
    missing = required_payload_fields(event_type) - payload.keys()
    if missing:
        raise InvalidEvent(
            f"{event_type} payload missing required fields: {', '.join(sorted(missing))}"
        )
    if event_type == "stats.updated" and not (
        payload.get("turn_id") or payload.get("model_call_id")
    ):
        raise InvalidEvent("stats.updated requires turn_id or model_call_id")
    if event_type == "tool.requested" and "tool_execution_id" in payload:
        raise InvalidEvent("tool.requested cannot contain tool_execution_id")


@dataclass(frozen=True)
class RunEventDraft:
    run_id: str
    type: str
    payload: dict[str, Any]
    team_id: str | None = None
    actor_id: str | None = None
    node_id: str | None = None
    status: str | None = None
    parent_event_id: str | None = None
    schema_version: int = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.type, "type")
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise InvalidEvent(f"unsupported event schema version: {self.schema_version}")
        validate_event_payload(self.type, self.payload)


@dataclass(frozen=True)
class PersistedEvent:
    event_id: str
    run_id: str
    sequence: int
    timestamp: str
    type: str
    payload: dict[str, Any]
    team_id: str | None = None
    actor_id: str | None = None
    node_id: str | None = None
    status: str | None = None
    parent_event_id: str | None = None
    schema_version: int = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.type, "type")
        if self.sequence < 1:
            raise InvalidEvent("sequence must be positive")
        if self.event_id != f"{self.run_id}:{self.sequence}":
            raise InvalidEvent("event_id must be <run_id>:<sequence>")
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise InvalidEvent(f"unsupported event schema version: {self.schema_version}")
        try:
            parsed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise InvalidEvent("timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise InvalidEvent("timestamp must be timezone-aware")
        validate_event_payload(self.type, self.payload)

    @classmethod
    def from_draft(
        cls,
        draft: RunEventDraft,
        sequence: int,
        timestamp: datetime | None = None,
    ) -> PersistedEvent:
        captured = timestamp or datetime.now(UTC)
        if captured.tzinfo is None:
            raise InvalidEvent("timestamp must be timezone-aware")
        return cls(
            event_id=f"{draft.run_id}:{sequence}",
            run_id=draft.run_id,
            sequence=sequence,
            timestamp=captured.astimezone(UTC).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            type=draft.type,
            payload=draft.payload,
            team_id=draft.team_id,
            actor_id=draft.actor_id,
            node_id=draft.node_id,
            status=draft.status,
            parent_event_id=draft.parent_event_id,
            schema_version=draft.schema_version,
        )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

