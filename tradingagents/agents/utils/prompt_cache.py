"""Prompt helpers for DeepSeek official API context-cache friendliness.

DeepSeek caches overlapping prompt prefixes automatically. These helpers keep
static instructions byte-stable and push run-specific data behind one dynamic
marker so tests can assert prefix stability without calling the API.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Sequence, Tuple

from tradingagents.dataflows.config import get_config


DYNAMIC_CONTEXT_MARKER = "## Dynamic Run Context"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def stable_join_sections(
    sections: Iterable[Tuple[str, Any]],
    *,
    marker: str = DYNAMIC_CONTEXT_MARKER,
) -> str:
    """Render dynamic prompt sections in caller-provided order.

    Empty bodies are skipped, but present sections are never re-ordered.
    """
    parts = [marker]
    for title, body in sections:
        text = _clean_text(body)
        if not text:
            continue
        parts.append(f"### {title}\n{text}")
    return "\n\n".join(parts).rstrip()


def trim_context_block(text: Any, max_chars: int, label: str) -> str:
    """Keep the most recent characters of a dynamic block with a stable marker."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    value = _clean_text(text)
    if len(value) <= max_chars:
        return value
    return f"[truncated {label}: kept most recent {max_chars} chars]\n{value[-max_chars:]}"


def get_prompt_cache_budget(key: str, default: int) -> int:
    """Read an integer budget from runtime config with a deterministic fallback."""
    raw = get_config().get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def budgeted_dynamic_text(text: Any, key: str, default: int, label: str) -> str:
    return trim_context_block(text, get_prompt_cache_budget(key, default), label)


def _message_role_and_content(message: Any) -> tuple[str, str]:
    if isinstance(message, dict):
        return str(message.get("role", "")), str(message.get("content", ""))
    if isinstance(message, tuple) and len(message) >= 2:
        return str(message[0]), str(message[1])
    role = getattr(message, "role", None) or getattr(message, "type", "")
    content = getattr(message, "content", "")
    return str(role), str(content)


def prompt_prefix_fingerprint(
    messages: Sequence[Any],
    *,
    dynamic_start_marker: str = DYNAMIC_CONTEXT_MARKER,
) -> str:
    """Hash only the static prefix before the dynamic context marker."""
    prefix_parts: list[dict[str, str]] = []
    for message in messages:
        role, content = _message_role_and_content(message)
        marker_index = content.find(dynamic_start_marker)
        if marker_index >= 0:
            prefix_parts.append({"role": role, "content": content[:marker_index]})
            break
        prefix_parts.append({"role": role, "content": content})
    payload = json.dumps(prefix_parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
