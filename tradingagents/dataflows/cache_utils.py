"""Small text-cache helpers for date-scoped dataflow fetchers.

The cache is intentionally plain text and key-based: news/fundamentals tools
return strings that are later injected into LLM prompts, so preserving the exact
string makes historical reruns more reproducible and avoids unnecessary vendor
quota use.  Callers should cache successful, deterministic payloads only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

from .config import get_config
from .utils import safe_ticker_component


def _safe_component(value: str, *, max_len: int = 80) -> str:
    """Return a filesystem-safe cache path component for arbitrary inputs."""
    if value and len(value) <= 32:
        try:
            return safe_ticker_component(value, max_len=32)
        except ValueError:
            pass
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    cleaned = "".join(ch if ch.isalnum() or ch in "._-^=+" else "_" for ch in value)
    cleaned = cleaned.strip("._-")[: max_len - 17]
    return f"{cleaned or 'key'}-{digest}"


def cache_path(namespace: str, *parts: str) -> Path:
    base = Path(get_config()["data_cache_dir"]) / "text_cache" / namespace
    safe_parts = [_safe_component(str(part)) for part in parts]
    return base.joinpath(*safe_parts).with_suffix(".txt")


def read_text_cache(namespace: str, *parts: str) -> Optional[str]:
    path = cache_path(namespace, *parts)
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except OSError:
        return None
    return None


def write_text_cache(namespace: str, value: str, *parts: str) -> str:
    path = cache_path(namespace, *parts)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except OSError:
        # Cache is an optimization; never fail a data tool because disk cache
        # cannot be written.
        pass
    return value


def cache_text(namespace: str, parts: tuple[str, ...], fetch: Callable[[], str]) -> str:
    cached = read_text_cache(namespace, *parts)
    if cached is not None:
        return cached
    value = fetch()
    # Avoid pinning transient vendor failures into reproducible cache.
    if isinstance(value, str) and not value.lstrip().lower().startswith("error"):
        write_text_cache(namespace, value, *parts)
    return value
