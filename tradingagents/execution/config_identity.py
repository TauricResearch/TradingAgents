"""Secret-free semantic configuration identity shared by execution and resume."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from tradingagents.observability.redaction import (
    RedactionRecord,
    remove_credentials_recursive,
)

LOCATION_ONLY_CONFIG_KEYS = frozenset(
    {"project_dir", "results_dir", "data_cache_dir", "memory_log_path"}
)


class SemanticConfigError(ValueError):
    """A configuration cannot be represented as a safe semantic identity."""


@dataclass(frozen=True)
class SemanticConfigProjection:
    value: dict[str, Any]
    removed_credentials: tuple[RedactionRecord, ...]


def normalize_endpoint_identity(value: Any) -> dict[str, Any] | None:
    """Return endpoint semantics without user-info, query, or fragment."""
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = urlsplit(str(value).strip())
        port = parsed.port
    except ValueError as exc:
        raise SemanticConfigError("backend_url contains an invalid port") from exc
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        raise SemanticConfigError("backend_url must include scheme and host")
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": parsed.path or "/",
    }


def project_effective_config(
    effective_config: Mapping[str, Any],
) -> SemanticConfigProjection:
    """Remove credentials/location-only roots and validate canonical JSON."""
    stripped = remove_credentials_recursive(effective_config)
    if not isinstance(stripped.value, Mapping):
        raise SemanticConfigError("effective_config must be a mapping")
    pruned = prune_removed_credential_shells(effective_config, stripped.value)
    prepared = {
        key: value
        for key, value in pruned.items()
        if key not in LOCATION_ONLY_CONFIG_KEYS
    }
    if "backend_url" in prepared:
        prepared["backend_url"] = normalize_endpoint_identity(prepared["backend_url"])
    try:
        json.dumps(
            prepared,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise SemanticConfigError(
            "effective_config is not canonical JSON data"
        ) from exc
    return SemanticConfigProjection(prepared, stripped.manifest)


def prepare_effective_config(effective_config: Mapping[str, Any]) -> dict[str, Any]:
    return project_effective_config(effective_config).value


def prune_removed_credential_shells(original: Any, stripped: Any) -> Any:
    """Remove containers that exist only because credential leaves were removed."""
    if isinstance(stripped, Mapping) and isinstance(original, Mapping):
        output = {}
        for key, child in stripped.items():
            original_child = original.get(key)
            pruned = prune_removed_credential_shells(original_child, child)
            was_nonempty_container = isinstance(
                original_child, (Mapping, list, tuple)
            ) and bool(original_child)
            is_empty_container = isinstance(pruned, (Mapping, list, tuple)) and not pruned
            if was_nonempty_container and is_empty_container:
                continue
            output[key] = pruned
        return output
    if isinstance(stripped, list) and isinstance(original, (list, tuple)):
        output = []
        for original_child, child in zip(original, stripped, strict=True):
            pruned = prune_removed_credential_shells(original_child, child)
            if (
                isinstance(original_child, (Mapping, list, tuple))
                and bool(original_child)
                and isinstance(pruned, (Mapping, list, tuple))
                and not pruned
            ):
                continue
            output.append(pruned)
        return output
    return stripped
