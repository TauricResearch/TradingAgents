"""Trace record schema (T1.1).

Every callback event in the audit stream produces one ``TraceRecord``.
The schema is intentionally narrow: anything that varies per event type
(messages list, tool input, etc.) lives under the loosely-typed
``payload`` dict so adding a new event type doesn't require schema
migration. What's locked is the spine — id, session, parent, type,
timestamp, and the content-addressed hash of the payload.

The fields exist for these reasons:
- ``record_id`` / ``parent_record_id`` reconstruct the call tree
  (tool calls inside a chain inside a graph node) without relying on
  file ordering, which append-only streams can't guarantee under
  concurrent writers.
- ``session_id`` groups all records from one ``TraceCallback`` instance
  so a CLI session = one logical file even if multiple were emitted.
- ``payload_hash`` is the cryptographic anchor T1.3's hash chain will
  link against. We compute it now so the on-disk format is ready for
  the chain when it ships, no migration needed.
- ``prev_hash`` is reserved for T1.3 and recorded as empty string in
  Phase 1 — a string rather than None to keep canonical JSON shape
  stable across phases.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


# Event type constants. Strings rather than enum so JSON-on-disk stays
# readable without a translation layer; also matches the LangChain
# callback method names so grep-ability is preserved.
LLM_START = "llm_start"
LLM_END = "llm_end"
TOOL_START = "tool_start"
TOOL_END = "tool_end"
NODE_ENTER = "node_enter"  # LangGraph node / chain start
NODE_EXIT = "node_exit"

TraceType = Literal[
    "llm_start", "llm_end",
    "tool_start", "tool_end",
    "node_enter", "node_exit",
]


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization for hashing.

    Sort keys, no extra whitespace, default str fallback for datetimes
    and other JSON-foreign types. Two semantically-equal records must
    produce byte-identical canonical JSON or the hash chain breaks.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hash_payload(payload: Dict[str, Any]) -> str:
    """SHA-256 of the payload's canonical JSON encoding, hex-encoded."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class TraceRecord(BaseModel):
    """One callback event in the trace stream.

    All identifying timestamps are UTC. ``record_id`` is intentionally a
    string (not the UUID type) so it round-trips through JSON without
    needing a custom encoder — the alternative is the hash chain breaking
    when a UUID gets stringified differently between writer and reader.
    """

    record_id: str = Field(
        description="UUID4 unique to this event."
    )
    session_id: str = Field(
        description="UUID of the TraceCallback instance that emitted this record."
    )
    parent_record_id: Optional[str] = Field(
        default=None,
        description=(
            "record_id of the enclosing event, when one exists. Tool calls "
            "fired from inside an LLM call carry the LLM call's record_id; "
            "LLM calls from inside a graph node carry the node_enter id; "
            "etc. Top-level events have None."
        ),
    )
    ts: datetime = Field(
        description="UTC timestamp of when this event fired."
    )
    type: TraceType = Field(
        description="Which lifecycle event this record represents."
    )
    node: Optional[str] = Field(
        default=None,
        description=(
            "Graph node name when extractable from LangChain's metadata "
            "(``langgraph_node`` key). None for events outside a graph."
        ),
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Event-specific contents. For llm_start: messages list, model "
            "name, invocation kwargs. For llm_end: full response, "
            "fingerprint, token usage, stop_reason. For tool_start/end: "
            "the tool's serialized form, input, and output. The structure "
            "is intentionally not strict — schema evolution is meant to "
            "happen via additive payload keys rather than top-level "
            "TraceRecord fields, so older trace files stay parseable."
        ),
    )
    payload_hash: str = Field(
        description="Hex SHA-256 of the canonical JSON encoding of payload."
    )
    prev_hash: str = Field(
        default="",
        description=(
            "Hex SHA-256 of the previous record's full canonical JSON, "
            "for the hash chain shipping in T1.3. Empty string in Phase 1; "
            "kept as a string (not None) so the on-disk shape is stable."
        ),
    )

    model_config = {"arbitrary_types_allowed": True}

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Return the dict used for hashing this record.

        Excludes ``prev_hash`` because by definition that points BACKWARD
        — the chain link is computed when this record is being appended,
        and including the back-pointer in its own hash would make it
        impossible for a verifier to recompute (chicken-and-egg).
        """
        return {
            "record_id": self.record_id,
            "session_id": self.session_id,
            "parent_record_id": self.parent_record_id,
            "ts": self.ts.isoformat().replace("+00:00", "Z"),
            "type": self.type,
            "node": self.node,
            "payload": self.payload,
            "payload_hash": self.payload_hash,
        }

    def canonical(self) -> str:
        """Canonical-JSON serialization of the full record, INCLUDING prev_hash.

        This is what T1.3's chain hashes the next record against — i.e.
        next.prev_hash == sha256(prev.canonical()).
        """
        d = self.to_canonical_dict()
        d["prev_hash"] = self.prev_hash
        return canonical_json(d)
