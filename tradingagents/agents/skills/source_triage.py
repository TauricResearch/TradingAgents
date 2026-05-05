from __future__ import annotations

from typing import Any


def build_source_triage(source_registry: dict[str, Any]) -> dict[str, Any]:
    sources = source_registry.get("source_objects") if isinstance(source_registry, dict) else []
    sources = sources if isinstance(sources, list) else []
    return {
        "source_count": len(sources),
        "citable_source_ids": list(source_registry.get("citable_source_ids") or []) if isinstance(source_registry, dict) else [],
        "note": "Prefer citeable structured sources over broad narrative claims.",
    }
