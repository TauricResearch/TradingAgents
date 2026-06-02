"""Disk-backed LLM response cache for TradingAgents.

Wraps a langchain chat model's ``invoke`` to memoize responses keyed on
``(model, normalized_messages, tools, tool_choice, sampling_params)``.
Turns repeated analyst/researcher/risk prompts into zero-cost local reads,
which is the single biggest lever for staying under OpenRouter free-tier
rate limits when iterating on a trade date.

Design notes
------------
* The cache is *opportunistic*. It never invalidates entries; callers
  control lifetime via ``cache_ttl_seconds``. The free-tier use case
  (resume a crashed run, replay the same date while tuning prompts) does
  not need precise invalidation.
* Keys are sha256 of canonical JSON. We hash the rendered prompt
  contents (system + human + tool messages), the bound tool names, and
  sampling-affecting kwargs (temperature, top_p, seed). Streaming
  (``stream()``) is bypassed — only ``invoke`` hits the cache.
* Cache misses never block. A failed write logs a warning and returns
  the live response; the next call tries again.
* Stored payloads round-trip through ``langchain_core.load.dumpd`` /
  ``load`` so AIMessage fields (tool_calls, additional_kwargs,
  response_metadata, usage_metadata) are preserved exactly. The load
  call passes ``allowed_objects=["messages"]`` to silence the
  langchain-core 1.3+ security warning (see
  ``tradingagents/__init__.py`` for the equivalent preload).
* The cache is opt-in per-instance via ``LLMResponseCache.enabled = True``
  and ``cache_dir`` set; the project default in ``default_config`` is
  ON, so a fresh build with no env-var overrides will cache. To
  disable for a run, set ``TRADINGAGENTS_LLM_CACHE_ENABLED=false``
  in your environment. ``get_default_cache`` resolves the cache from
  ``data_cache_dir``; pass an explicit path to override.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


# Suppress the langchain-core beta warning that fires every time ``load``
# is called. We pass ``allowed_objects='messages'`` which is the
# documented gate for untrusted chat input; the beta marker is a
# separate, broader signal that we don't need in a stable cache path.
# The deprecation half is already filtered in ``tradingagents/__init__.py``.
def _load_with_suppressed_beta(raw: Any) -> Any:
    """``langchain_core.load.load`` wrapped to silence its BetaWarning.

    ``LangChainBetaWarning`` subclasses ``DeprecationWarning``, not
    ``UserWarning``, so we filter on the deprecation half directly.
    The broader pending-deprecation variant is already filtered in
    ``tradingagents/__init__.py``.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=DeprecationWarning)
        from langchain_core.load import load as _lc_load
        return _lc_load(raw, allowed_objects="messages")


# ---- Key construction ---------------------------------------------------

# kwargs that, if present, change the response and must be part of the key.
# Anything outside this list (timeouts, callbacks, http_client) is
# non-semantic for caching purposes.
# Cross-reference: ``anthropic_client.py._PASSTHROUGH_KWARGS`` includes
# ``effort`` and ``google_client.py`` reads ``thinking_level`` /
# ``thinking_budget``; keeping these in sync is the only thing that
# prevents a same-prompt-different-mode cache hit from returning the
# wrong response.
_SEMANTIC_KWARGS: frozenset[str] = frozenset({
    "temperature",
    "top_p",
    "top_k",
    "seed",
    "max_tokens",
    "max_completion_tokens",
    "stop",
    "response_format",
    "reasoning_effort",
    "thinking_level",
    "thinking_budget",
    "thinking",         # Anthropic extended thinking dict
    "effort",           # Anthropic opus/sonnet 4.5+ effort level
    "extra_body",
})

# kwargs that, if present, change the response and need a structural hash
# rather than a direct repr. ``tools`` is the main one — a single tool
# can be a dict, a pydantic model, a BaseTool, or a callable, and any
# repr mismatch would invalidate the cache for the same logical request.
_STRUCTURAL_KWARGS: frozenset[str] = frozenset({"tools", "tool_choice"})


def _json_default(obj: Any) -> Any:
    """Best-effort fallback for objects ``json.dumps`` cannot serialize.

    Langchain tool definitions can be dicts, pydantic models, or callables.
    We normalize them to a stable shape: ``(type, name, description, schema)``
    for tools and the repr of anything else.
    """
    if hasattr(obj, "name") and hasattr(obj, "description"):
        schema = getattr(obj, "args_schema", None)
        return {
            "__type__": "tool",
            "name": getattr(obj, "name", str(obj)),
            "description": getattr(obj, "description", ""),
            "schema": getattr(schema, "model_json_schema", lambda: str(schema))(),
        }
    if hasattr(obj, "model_json_schema"):
        return {"__type__": "pydantic", "schema": obj.model_json_schema()}
    return {"__type__": "repr", "value": repr(obj)}


def _serialize_tool(tool: Any) -> str:
    """Stable canonical JSON for a single tool entry."""
    payload = _json_default(tool)
    return json.dumps(payload, sort_keys=True, default=str)


def _normalize_messages(messages: Any) -> list[dict[str, Any]]:
    """Turn a list of messages / ChatPromptValue / single string into a list of plain dicts.

    The output is intentionally a list of ``{"role": ..., "content": ...}``
    dicts, NOT langchain message objects — we hash the rendered form so
    a ``SystemMessage("x")`` and a ``("system", "x")`` tuple hash the same
    way.
    """
    # ChatPromptValue or any object exposing to_messages()
    if hasattr(messages, "to_messages"):
        messages = messages.to_messages()
    elif isinstance(messages, str):
        return [{"role": "human", "content": messages}]

    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return [{"role": "human", "content": str(messages)}]

    out: list[dict[str, Any]] = []
    for msg in messages:
        # Bare tuples like ``("system", "you are...")`` from analyst prompts
        if isinstance(msg, tuple) and len(msg) == 2:
            role, content = msg
            out.append({"role": str(role), "content": _render_content(content)})
            continue
        # Langchain messages
        role = getattr(msg, "type", None) or _infer_role(msg)
        content = getattr(msg, "content", msg)
        tool_calls = getattr(msg, "tool_calls", None) or []
        out.append({
            "role": role or "human",
            "content": _render_content(content),
            "tool_calls": [_serialize_tool_call(tc) for tc in tool_calls],
        })
    return out


def _infer_role(msg: Any) -> str:
    """Fallback role inference for messages without a ``type`` attribute."""
    cls = type(msg).__name__.lower()
    if "system" in cls:
        return "system"
    if "ai" in cls or "assistant" in cls:
        return "ai"
    if "tool" in cls:
        return "tool"
    if "human" in cls or "user" in cls:
        return "human"
    return "human"


def _render_content(content: Any) -> Any:
    """Normalize message content to a JSON-safe form.

    Strings pass through unchanged; list-of-blocks (typed content from
    OpenAI Responses API / Gemini 3) is reduced to its text portion so
    the cache key is stable across SDK versions.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
        return "\n".join(texts)
    return str(content)


def _serialize_tool_call(tc: Any) -> dict[str, Any]:
    """Stable dict for a single tool call (which may be a dict or object)."""
    if isinstance(tc, Mapping):
        return {
            "name": tc.get("name"),
            "args": tc.get("args"),
            "id": tc.get("id"),
        }
    return {
        "name": getattr(tc, "name", None),
        "args": getattr(tc, "args", None),
        "id": getattr(tc, "id", None),
    }


def make_cache_key(
    model: str,
    messages: Any,
    *,
    tools: Any = None,
    tool_choice: Any = None,
    **kwargs: Any,
) -> str:
    """Compute a deterministic sha256 key for an invoke call.

    ``model`` should be the chat model's ``model_name`` (or equivalent).
    Extra ``kwargs`` not in ``_SEMANTIC_KWARGS`` are ignored — the
    response is unaffected by timeouts, callbacks, or transport config.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": _normalize_messages(messages),
    }
    if tools is not None:
        if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes)):
            payload["tools"] = [_serialize_tool(t) for t in tools]
        else:
            payload["tools"] = _serialize_tool(tools)
    if tool_choice is not None:
        payload["tool_choice"] = _serialize_tool(tool_choice)

    for key in sorted(_SEMANTIC_KWARGS):
        if key in kwargs and kwargs[key] is not None:
            payload[key] = kwargs[key]

    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---- Storage -------------------------------------------------------------


@dataclass
class CacheStats:
    """Lightweight counters useful for tests and a future CLI flag."""

    hits: int = 0
    misses: int = 0
    writes: int = 0
    write_failures: int = 0
    expired_skips: int = 0

    def reset(self) -> None:
        self.hits = 0
        self.misses = 0
        self.writes = 0
        self.write_failures = 0
        self.expired_skips = 0


class LLMResponseCache:
    """Disk-backed cache of langchain ``AIMessage`` responses.

    Parameters
    ----------
    cache_dir:
        Directory holding the cache. Created on first write if absent.
    ttl_seconds:
        Optional per-entry TTL. ``None`` means never expire.
    enabled:
        Set to ``False`` to short-circuit ``get``/``put`` into no-ops
        (useful for tests and for the ``LLM_CACHE_ENABLED=false``
        escape hatch in the env overlay).
    """

    def __init__(
        self,
        cache_dir: str | os.PathLike[str],
        *,
        ttl_seconds: Optional[int] = None,
        enabled: bool = True,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self.stats = CacheStats()
        # File-system writes are serialized per-cache to avoid half-written
        # files when two agents invoke the same prompt concurrently.
        self._lock = threading.Lock()

    # ---- public API ----

    def get(self, key: str) -> Optional[Any]:
        """Return a cached AIMessage, or None on miss/expire/disabled.

        Errors are logged and treated as a miss: a corrupted cache entry
        must never block a live API call.
        """
        if not self.enabled:
            self.stats.misses += 1
            return None

        path = self._path_for(key)
        if not path.exists():
            self.stats.misses += 1
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("llm_cache: failed to read %s (%s); treating as miss", path, exc)
            self.stats.misses += 1
            return None

        if self._is_expired(raw):
            self.stats.expired_skips += 1
            self.stats.misses += 1
            return None

        try:
            # ``allowed_objects='messages'`` is the documented sentinel
            # for untrusted chat-only input. Passing a list of class
            # names (or omitting the kwarg) triggers the deprecation
            # warning filtered in tradingagents/__init__.py and would
            # re-surface under ``-W error``.
            message = _load_with_suppressed_beta(raw["payload"])
        except Exception as exc:  # noqa: BLE001 — never block on a bad cache
            logger.warning("llm_cache: failed to deserialize %s (%s); treating as miss", path, exc)
            self.stats.misses += 1
            return None

        self.stats.hits += 1
        return message

    def put(self, key: str, response: Any) -> None:
        """Persist ``response`` under ``key``. Errors are logged, never raised.

        Uses a tempfile + ``os.replace`` so a crash mid-write can never
        leave a half-written file that the next ``get`` would treat as
        valid (json.loads would happily read it).
        """
        if not self.enabled:
            return

        try:
            from langchain_core.load import dumpd
            # ``dumpd`` only takes the object (no allowed_objects kwarg;
            # that's a load-time gate). The output is the same canonical
            # ``{"lc": 1, "type": ..., "kwargs": ...}`` envelope that
            # ``load`` round-trips back into an AIMessage.
            payload = dumpd(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_cache: dumpd failed for key %s (%s); skipping write", key, exc)
            self.stats.write_failures += 1
            return

        envelope = {
            "created_at": time.time(),
            "payload": payload,
        }
        path = self._path_for(key)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    dir=path.parent,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(envelope, f, ensure_ascii=False)
                    os.replace(tmp_name, path)
                except BaseException:
                    # Remove the temp file on any failure so we don't
                    # litter the cache dir.
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise
            except OSError as exc:
                logger.warning("llm_cache: write failed for key %s (%s)", key, exc)
                self.stats.write_failures += 1
                return

        self.stats.writes += 1

    def clear(self) -> int:
        """Delete all cache entries. Returns the count removed.

        Recursively walks the cache directory — the on-disk layout
        shards entries under ``<cache_dir>/<key[:2]>/`` so a top-level
        ``glob("*.json")`` would miss everything.
        """
        if not self.cache_dir.exists():
            return 0
        removed = 0
        for path in self.cache_dir.rglob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    # ---- internals ----

    def _path_for(self, key: str) -> Path:
        # Two-level directory keeps any single folder under ~10k files
        # so a giant cache doesn't bottleneck the filesystem.
        return self.cache_dir / key[:2] / f"{key}.json"

    def _is_expired(self, envelope: Mapping[str, Any]) -> bool:
        if self.ttl_seconds is None:
            return False
        created_at = envelope.get("created_at")
        if not isinstance(created_at, (int, float)):
            return True
        return (time.time() - float(created_at)) > self.ttl_seconds


# ---- Default resolution -------------------------------------------------


_DEFAULT_CACHE: Optional[LLMResponseCache] = None
_DEFAULT_CACHE_LOCK = threading.Lock()


def get_default_cache(
    *,
    data_cache_dir: Optional[str | os.PathLike[str]] = None,
    ttl_seconds: Optional[int] = None,
    enabled: bool = True,
    override: bool = False,
) -> Optional[LLMResponseCache]:
    """Return a process-wide cache, building it lazily from config.

    Returns ``None`` when ``enabled`` is false (callers should treat
    ``None`` as "no caching"). The default location is
    ``<data_cache_dir>/llm_cache`` so the cache is gitignored alongside
    the other TradingAgents caches.

    Pass ``override=True`` to rebuild the singleton (used by tests that
    change ``data_cache_dir``).
    """
    global _DEFAULT_CACHE
    if not enabled:
        return None
    with _DEFAULT_CACHE_LOCK:
        if _DEFAULT_CACHE is not None and not override:
            return _DEFAULT_CACHE
        if not data_cache_dir:
            return None
        cache_path = Path(data_cache_dir) / "llm_cache"
        _DEFAULT_CACHE = LLMResponseCache(
            cache_path,
            ttl_seconds=ttl_seconds,
            enabled=True,
        )
        return _DEFAULT_CACHE


def reset_default_cache() -> None:
    """Drop the process-wide cache. Tests use this to start from a clean slate."""
    global _DEFAULT_CACHE
    with _DEFAULT_CACHE_LOCK:
        _DEFAULT_CACHE = None
