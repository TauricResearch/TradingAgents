from __future__ import annotations

import hashlib
from typing import Any

from langchain_core.messages import ToolMessage


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _message_content(message: ToolMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return repr(content)


def create_tool_provenance_capture_node(source_prefix: str):
    """Capture ToolNode messages into graph state before they are cleared."""

    def capture_tool_provenance(state) -> dict[str, Any]:
        existing = list(state.get("raw_tool_outputs") or [])
        seen = set(state.get("raw_tool_seen_ids") or [])
        captured = []

        for message in state.get("messages", []):
            if not isinstance(message, ToolMessage):
                continue
            tool_call_id = getattr(message, "tool_call_id", None) or getattr(message, "id", None)
            if not tool_call_id or tool_call_id in seen:
                continue

            sequence = len(existing) + len(captured) + 1
            content = _message_content(message)
            captured.append(
                {
                    "source_id": f"RAW-TOOL-{sequence:04d}",
                    "source_type": "raw_tool_output",
                    "tool_call_id": str(tool_call_id),
                    "tool_name": getattr(message, "name", None) or source_prefix,
                    "analyst": source_prefix,
                    "content": content,
                    "output": content,
                    "output_sha256": _hash_text(content),
                    "bytes": len(content.encode("utf-8")),
                    "status": getattr(message, "status", "succeeded"),
                }
            )
            seen.add(tool_call_id)

        if not captured:
            return {}
        return {
            "raw_tool_outputs": existing + captured,
            "raw_tool_seen_ids": sorted(seen),
        }

    return capture_tool_provenance
