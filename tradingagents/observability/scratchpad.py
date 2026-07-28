"""Safe, replay-oriented scratchpad contracts.

The scratchpad is an operational trace, not a transcript of model reasoning.
It deliberately records only stable hashes, artifact references, and small
typed lifecycle facts. In particular it must never contain private chain of
thought, raw prompts, or raw tool results.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradingagents.observability.canonical import canonical_business_value
from tradingagents.observability.redaction import redact_recursive

SCRATCHPAD_SCHEMA_VERSION = 1
ScratchpadEventType = Literal[
    "tool_limit",
    "thinking",
    "microcompact",
    "compaction",
    "context_cleared",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}:[0-9a-f]{64}$")
_DETAIL_CODE = re.compile(r"^[a-z][a-z0-9_:-]{0,79}$")
_QUERY_KEYS = frozenset({"ticker", "asset_type", "analysis_date"})
_UNSAFE_KEYS = frozenset(
    {
        "args",
        "arguments",
        "chain_of_thought",
        "content",
        "prompt",
        "raw_result",
        "reasoning",
        "result",
        "thinking",
    }
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def safe_value_sha256(value: Any) -> str | None:
    """Hash a redacted value without retaining a recoverable copy of it."""
    if value is None:
        return None
    redacted = redact_recursive(value).value
    return hashlib.sha256(canonical_business_value(redacted).bytes).hexdigest()


class ScratchpadEntry(BaseModel):
    """One safe lifecycle entry written to a run-local ``scratchpad.jsonl``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCRATCHPAD_SCHEMA_VERSION] = SCRATCHPAD_SCHEMA_VERSION
    entry_id: str = Field(default_factory=lambda: f"scratch_{uuid.uuid4().hex}")
    run_id: str
    timestamp: str = Field(default_factory=_timestamp)
    event_type: ScratchpadEventType
    detail_code: str
    query: dict[str, str] = Field(default_factory=dict)
    arguments_sha256: str | None = None
    result_sha256: str | None = None
    artifact_ids: tuple[str, ...] = ()
    metadata: dict[str, int | float | bool | None] = Field(default_factory=dict)
    thinking_persisted: Literal[False] = False
    event_id: str | None = None
    event_sequence: int | None = Field(default=None, ge=1)

    @field_validator("run_id")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value is required")
        return value

    @field_validator("detail_code")
    @classmethod
    def _validate_detail_code(cls, value: str) -> str:
        if not _DETAIL_CODE.fullmatch(value):
            raise ValueError("detail_code must be a short machine-readable code")
        return value

    @field_validator("arguments_sha256", "result_sha256")
    @classmethod
    def _validate_digest(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("digest must be a lowercase SHA-256 hex value")
        return value

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: dict[str, str]) -> dict[str, str]:
        unsafe = _UNSAFE_KEYS.intersection(value)
        if unsafe:
            raise ValueError(f"unsafe scratchpad fields are not permitted: {sorted(unsafe)}")
        unknown = set(value).difference(_QUERY_KEYS)
        if unknown:
            raise ValueError(f"unsupported scratchpad query fields: {sorted(unknown)}")
        if any(len(item) > 48 or "\n" in item for item in value.values()):
            raise ValueError("scratchpad query values must be short identifiers")
        return value

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, int | float | bool | None]) -> dict[str, int | float | bool | None]:
        unsafe = _UNSAFE_KEYS.intersection(value)
        if unsafe:
            raise ValueError(f"unsafe scratchpad fields are not permitted: {sorted(unsafe)}")
        if any(not _DETAIL_CODE.fullmatch(key) for key in value):
            raise ValueError("scratchpad metadata keys must be machine-readable codes")
        return value

    @field_validator("artifact_ids")
    @classmethod
    def _validate_artifact_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _ARTIFACT_ID.fullmatch(artifact_id) for artifact_id in value):
            raise ValueError("scratchpad artifact references must be valid artifact ids")
        return value

    @model_validator(mode="after")
    def _validate_thinking_event(self) -> ScratchpadEntry:
        if self.event_type == "thinking" and self.detail_code != "private_reasoning_not_persisted":
            raise ValueError(
                "thinking entries must state that private reasoning was not persisted"
            )
        return self

    @classmethod
    def from_values(
        cls,
        *,
        run_id: str,
        event_type: ScratchpadEventType,
        detail_code: str,
        query: dict[str, str] | None = None,
        arguments: Any = None,
        result: Any = None,
        artifact_ids: tuple[str, ...] | list[str] = (),
        metadata: dict[str, int | float | bool | None] | None = None,
    ) -> ScratchpadEntry:
        return cls(
            run_id=run_id,
            event_type=event_type,
            detail_code=detail_code,
            query=dict(query or {}),
            arguments_sha256=safe_value_sha256(arguments),
            result_sha256=safe_value_sha256(result),
            artifact_ids=tuple(dict.fromkeys(artifact_ids)),
            metadata=dict(metadata or {}),
        )

    def event_payload(self) -> dict[str, Any]:
        """The event projection; it contains the same safe subset as JSONL."""
        return {
            "scratchpad_entry_id": self.entry_id,
            "scratchpad_event_type": self.event_type,
            "detail_code": self.detail_code,
            "arguments_sha256": self.arguments_sha256,
            "result_sha256": self.result_sha256,
            "artifact_ids": list(self.artifact_ids),
            "thinking_persisted": False,
        }
