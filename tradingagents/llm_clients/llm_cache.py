"""Local file‑based cache for LLM API responses.

On **miss** the full ``AIMessage`` is serialised to a JSON file under
``~/.tradingagents/cache/llm_responses/<sha256>.json``. On **hit** the
stored JSON is deserialised back into an ``AIMessage`` — zero API cost,
zero network latency.

Relationship with DeepSeek's server‑side prefix cache
------------------------------------------------------
DeepSeek maintains a **prefix (KV) cache** on their side: when the
beginning of your message sequence (system prompt + earlier turns)
matches a previous request, they skip re‑computing the attention
prefix — saving roughly 50 % on input tokens *per call*.

This module is **independent and complementary**:

  +---------------------------+---------------------------+
  | This cache                | DeepSeek prefix cache     |
  +---------------------------+---------------------------+
  | Client‑side, file‑based   | Server‑side, transparent  |
  | Stores *output*           | Caches *input* prefix     |
  | Hit → 100 % cost saved    | Hit → ~50 % input saved   |
  | Exact message match       | Prefix match (best effort)|
  +---------------------------+---------------------------+

Both can be active at the same time — the prefix cache saves input
tokens on every miss here, and this cache eliminates full API calls
for repeated analyses of the same (ticker, date, config) combination.

Design notes
------------
* **Cache key** = SHA256 of ``(model, temperature, extra_params, serialised
  messages)``.  *extra_params* captures invocation‑level settings such as
  ``tools``, ``tool_choice``, and ``response_format``, preventing incorrect
  cache hits when those differ despite identical messages.

* **Provider filter** — ``llm_cache_providers`` in ``DEFAULT_CONFIG``
  lets you restrict caching to specific providers (e.g. only DeepSeek,
  skip local Ollama). Empty list = cache all providers.

* **TTL** — configurable (default 24 h). Expired entries are lazily
  evicted on read; ``clear_expired()`` sweeps stale files in bulk.

* **Hit/miss counters** — kept in memory for the lifetime of the cache
  instance, exposed via ``stats()`` for monitoring.

* **Fault‑tolerant** — file‑system and serialisation errors are caught
  and logged, never propagated.  Caching is strictly best‑effort.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

_NON_SERIALISABLE_RESPONSE_META_KEYS = frozenset({"headers", "raw_response"})


def _normalise_input(messages: Any) -> list:
    """Normalise a LangChain invoke input to a flat list of messages.

    Accepts:
    * ``str`` — treated as a single user message.
    * Objects with a ``to_messages`` method (``ChatPromptValue``, ...).
    * Lists of messages (passed through as‑is).
    * Anything else — wrapped in a single‑element list.

    This prevents iteration over a string from producing per‑character
    messages, and handles ``PromptValue`` objects that are not directly
    iterable (e.g. ``ChatPromptValue`` returned by a template).
    """
    if isinstance(messages, str):
        return [messages]
    if not isinstance(messages, list) and hasattr(messages, "to_messages"):
        return messages.to_messages()
    if not isinstance(messages, list):
        return [messages]
    return messages


def _serialise_messages(messages: Any) -> str:
    """Deterministic JSON representation of a LangChain message list.

    Handles ``BaseMessage`` objects, plain dicts, raw strings, and
    ``ChatPromptValue`` via ``_normalise_input()``.
    Keys are sorted so identical logical content yields identical JSON.
    """
    messages = _normalise_input(messages)
    items: list[dict[str, Any]] = []
    for m in messages:
        if hasattr(m, "type") and hasattr(m, "content"):
            entry: dict[str, Any] = {
                "role": m.type,
                "content": m.content if isinstance(m.content, str) else str(m.content),
            }
            tool_calls = getattr(m, "tool_calls", None) or []
            if tool_calls:
                entry["tool_calls"] = [
                    {"name": tc.get("name", ""), "args": tc.get("args", {}), "id": tc.get("id")}
                    for tc in tool_calls
                ]
            items.append(entry)
        elif isinstance(m, dict):
            items.append({"role": m.get("role", ""), "content": str(m.get("content", ""))})
        else:
            items.append({"role": "", "content": str(m)})
    return json.dumps(items, sort_keys=True, ensure_ascii=False)


def _build_cache_key(
    model: str,
    messages: Any,
    temperature: float = 0.0,
    **kwargs: Any,
) -> str:
    """Deterministic SHA256 cache key.

    Incorporates *model*, *temperature*, invocation‑level *kwargs*
    (``tools``, ``tool_choice``, ``response_format``), and the
    serialised message list.  Different tool definitions or response
    formats therefore produce different keys.
    """
    msg_json = _serialise_messages(messages)
    # Collect invocation‑level parameters that affect the response.
    extra_params: dict[str, Any] = {}
    for key in ("tools", "tool_choice", "response_format"):
        if key in kwargs and kwargs[key] is not None:
            extra_params[key] = kwargs[key]
    # Use default=str to guard against non‑serialisable objects.
    try:
        extra_json = json.dumps(extra_params, sort_keys=True, default=str)
    except Exception:
        extra_json = str(extra_params)
    raw = f"{model}|{temperature}|{msg_json}|{extra_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return a JSON‑safe copy of *metadata*, stripping non‑serialisable keys."""
    if not metadata:
        return {}
    return {k: v for k, v in metadata.items()
            if k not in _NON_SERIALISABLE_RESPONSE_META_KEYS}


def _aimessage_to_dict(msg: AIMessage) -> dict[str, Any]:
    """Serialise an ``AIMessage`` to a JSON‑safe dict."""
    return {
        "content": msg.content,
        "additional_kwargs": msg.additional_kwargs,
        "response_metadata": _safe_metadata(msg.response_metadata),
        "tool_calls": [
            {"name": tc.get("name", ""), "args": tc.get("args", {}),
             "id": tc.get("id"), "type": tc.get("type")}
            for tc in (msg.tool_calls or [])
        ],
        "invalid_tool_calls": [
            {"name": itc.get("name", ""), "args": itc.get("args", {}),
             "id": itc.get("id"), "type": itc.get("type"), "text": itc.get("text", "")}
            for itc in (msg.invalid_tool_calls or [])
        ],
        "id": msg.id,
        "usage_metadata": msg.usage_metadata,
    }


def _dict_to_aimessage(data: dict[str, Any]) -> AIMessage:
    """Reconstruct an ``AIMessage`` from a dict produced by ``_aimessage_to_dict``."""
    return AIMessage(
        content=data.get("content", ""),
        additional_kwargs=data.get("additional_kwargs", {}),
        response_metadata=data.get("response_metadata", {}),
        tool_calls=data.get("tool_calls", []),
        invalid_tool_calls=data.get("invalid_tool_calls", []),
        id=data.get("id"),
        usage_metadata=data.get("usage_metadata"),
    )


# ---------------------------------------------------------------------------
# Cache class
# ---------------------------------------------------------------------------


class LLMResponseCache:
    """Persistent local cache for LLM responses.

    Thread‑safe for reads; concurrent writes to the same key are safe
    because the last writer wins (acceptable for this use case).

    **All file‑system and serialisation errors are caught internally.**
    Caching is strictly best‑effort — a broken cache never crashes the
    main LLM invocation.

    Parameters
    ----------
    cache_dir:
        Root directory for cached response files. The actual files live
        under ``{cache_dir}/llm_responses/``.
    ttl_hours:
        Number of hours before an entry is considered stale.
    """

    def __init__(self, cache_dir: str, ttl_hours: int = 24) -> None:
        self._root = Path(cache_dir) / "llm_responses"
        self._root.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_hours * 3600
        self.hits: int = 0
        self.misses: int = 0

    # -- public properties --------------------------------------------------

    @property
    def cache_dir(self) -> str:
        """Absolute path to the cache directory on disk."""
        return str(self._root)

    @property
    def ttl_hours(self) -> int:
        """Configured TTL in whole hours."""
        return self._ttl_seconds // 3600

    # -- public API ---------------------------------------------------------

    def get(self, key: str) -> Optional[AIMessage]:
        """Look up *key*.

        Returns the cached ``AIMessage`` or ``None`` on miss/expiry/corruption
        or file‑system error.  Stale and corrupt entries are silently deleted.
        """
        path = self._root / f"{key}.json"
        try:
            if not path.exists():
                self.misses += 1
                return None

            age = time.time() - path.stat().st_mtime
            if age > self._ttl_seconds:
                try:
                    path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("Failed to delete expired cache file %s: %s", path, e)
                logger.debug("Cache entry %s expired (age=%.1fs)", key, age)
                self.misses += 1
                return None

            data = json.loads(path.read_text(encoding="utf-8"))
            msg = _dict_to_aimessage(data)
            self.hits += 1
            logger.debug("Cache HIT  for key=%s (%.0f min old)", key, age / 60)
            return msg
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Cache entry %s is corrupt (%s); removing", key, exc)
            try:
                path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to delete corrupt cache file %s: %s", path, e)
            self.misses += 1
            return None
        except OSError as exc:
            logger.warning("File system error reading cache entry %s: %s", key, exc)
            self.misses += 1
            return None

    def set(self, key: str, response: AIMessage) -> None:
        """Store *response* under *key*.

        All errors (serialisation failures, disk full, permission denied)
        are caught and logged — caching is best‑effort, never fatal.
        """
        try:
            path = self._root / f"{key}.json"
            data = _aimessage_to_dict(response)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            size_kb = path.stat().st_size / 1024
            logger.debug("Cache SET  for key=%s (%.1f kB)", key, size_kb)
        except Exception as exc:
            logger.warning("Failed to write cache entry for key %s: %s", key, exc)

    def clear_expired(self) -> int:
        """Delete all expired cache entries. Returns count of removed files."""
        now = time.time()
        removed = 0
        for f in self._root.glob("*.json"):
            if now - f.stat().st_mtime > self._ttl_seconds:
                try:
                    f.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
        if removed:
            logger.info("Cleared %d expired LLM cache entries", removed)
        return removed

    def clear_all(self) -> int:
        """Delete **all** cache entries regardless of age. Returns count removed."""
        removed = 0
        for f in self._root.glob("*.json"):
            try:
                f.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
        if removed:
            logger.info("Cleared all %d LLM cache entries", removed)
        self.hits = 0
        self.misses = 0
        return removed

    def stats(self) -> dict[str, Any]:
        """Return cache statistics.

        Returns
        -------
        dict with keys:
            * ``entry_count`` — number of cached files on disk
            * ``total_size_bytes`` — aggregated file size
            * ``oldest_hours`` — age of the oldest cache entry
            * ``hits`` — in‑memory hit count
            * ``misses`` — in‑memory miss count
            * ``hit_rate`` — ``hits / (hits + misses)`` or 0 if no requests
            * ``ttl_hours`` — configured TTL
            * ``cache_dir`` — on‑disk location
        """
        entries = list(self._root.glob("*.json"))
        entry_count = len(entries)
        total_bytes = sum(f.stat().st_size for f in entries)
        oldest = min((f.stat().st_mtime for f in entries), default=None)
        total_requests = self.hits + self.misses
        return {
            "entry_count": entry_count,
            "total_size_bytes": total_bytes,
            "oldest_hours": (time.time() - oldest) / 3600 if oldest else 0.0,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total_requests if total_requests > 0 else 0.0,
            "ttl_hours": self.ttl_hours,
            "cache_dir": self.cache_dir,
        }


# ---------------------------------------------------------------------------
# Module‑level convenience helpers
#
# Config is read from ``tradingagents.default_config.DEFAULT_CONFIG``, which
# respects the standard ``TRADINGAGENTS_*`` env‑var override chain.
# ---------------------------------------------------------------------------

_cache: Optional[LLMResponseCache] = None
"""Module‑level singleton. Initialised lazily on first use."""

_config: Optional[dict] = None
"""Module‑level config cache. Initialised lazily to avoid circular imports."""


def _get_config() -> dict[str, Any]:
    global _config
    if _config is None:
        from tradingagents.default_config import DEFAULT_CONFIG
        _config = DEFAULT_CONFIG
    return _config


def _get_cache() -> Optional[LLMResponseCache]:
    """Return the singleton cache instance, or ``None`` if caching is disabled."""
    global _cache
    cfg = _get_config()
    if not cfg.get("llm_cache_enabled", True):
        return None

    if _cache is None:
        cache_dir = cfg.get(
            "data_cache_dir",
            os.path.join(os.path.expanduser("~"), ".tradingagents", "cache"),
        )
        ttl_hours = cfg.get("llm_cache_ttl_hours", 24)
        _cache = LLMResponseCache(cache_dir, ttl_hours=ttl_hours)
    return _cache


def should_cache_provider(provider_name: str) -> bool:
    """Return ``True`` when *provider_name* should use the cache."""
    cfg = _get_config()
    allowed: list[str] = cfg.get("llm_cache_providers", [])
    if not allowed:
        return True
    return provider_name.lower() in [p.lower() for p in allowed]


def check_cache(
    provider_name: str,
    model: str,
    messages: Any,
    **kwargs: Any,
) -> Optional[AIMessage]:
    """Look up a cached response.

    *messages* is the raw ``invoke`` input (list, string, PromptValue, …).
    *kwargs* carries invocation‑level parameters (temperature, tools,
    response_format, …) that are folded into the cache key.

    Returns the cached ``AIMessage`` or ``None``.
    """
    cache = _get_cache()
    if cache is None or not should_cache_provider(provider_name):
        return None
    key = _build_cache_key(model, messages, **kwargs)
    return cache.get(key)


def store_cache(
    provider_name: str,
    model: str,
    messages: Any,
    response: AIMessage,
    **kwargs: Any,
) -> None:
    """Store an LLM response in the cache. Silently no‑ops when disabled."""
    cache = _get_cache()
    if cache is None or not should_cache_provider(provider_name):
        return
    key = _build_cache_key(model, messages, **kwargs)
    cache.set(key, response)
