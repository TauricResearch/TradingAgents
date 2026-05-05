from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


REPORT_SOURCE_SPECS = (
    ("market_report", "market", "Market analyst report"),
    ("news_report", "news", "News analyst report"),
    ("sentiment_report", "sentiment", "Sentiment analyst report"),
    ("fundamentals_report", "fundamentals", "Fundamentals analyst report"),
    ("macro_report", "macro", "Macro analyst report"),
)

_COMMON_FIELDS = ("source_id", "source_type", "label", "summary", "state_key", "skill")


def _summary(text: str, limit: int = 360) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        if source_id in seen:
            continue
        seen.add(source_id)
        deduped.append(source)
    return deduped


def _merge_unique_str_lists(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, str) or not item.strip() or item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


def _summary_from_value(value: Any, limit: int = 260) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else repr(value)
    return _summary(text, limit=limit)


def normalize_source_object(source: dict[str, Any]) -> dict[str, Any]:
    source_id = source.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        return {}
    source_type = source.get("source_type") if isinstance(source.get("source_type"), str) else "unknown"
    label = source.get("label") if isinstance(source.get("label"), str) else source_type.replace("_", " ").title()
    summary = source.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = label
    normalized = {
        "source_id": source_id,
        "source_type": source_type,
        "label": label,
        "summary": summary,
        "citeable": bool(source.get("citeable", True)),
        "citable_id": source_id if bool(source.get("citeable", True)) else None,
    }
    for key in _COMMON_FIELDS:
        value = source.get(key)
        if value is not None and key not in normalized:
            normalized[key] = value
    normalized["claim_ids"] = _merge_unique_str_lists(source.get("claim_ids"))
    normalized["source_ids"] = _merge_unique_str_lists(source.get("source_ids"))
    normalized["claim_source_ids"] = _merge_unique_str_lists(source.get("claim_source_ids"))
    if isinstance(source.get("bytes"), int):
        normalized["bytes"] = source["bytes"]
    elif "summary" in normalized:
        normalized["bytes"] = len(str(normalized["summary"]).encode("utf-8"))
    return normalized


def normalize_source_objects(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        return []
    normalized = [normalize_source_object(source) for source in sources if isinstance(source, dict)]
    return [source for source in normalized if source]


def build_report_source_objects(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for key, source_type, label in REPORT_SOURCE_SPECS:
        content = final_state.get(key)
        if not isinstance(content, str) or not content.strip():
            continue
        source_id = f"SRC-{source_type.upper()}-1"
        sources.append(
            {
                "source_id": source_id,
                "source_type": source_type,
                "label": label,
                "state_key": key,
                "summary": _summary(content),
                "bytes": len(content.encode("utf-8")),
                "citeable": True,
            }
        )
    return sources


def build_raw_tool_source_objects(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    raw_outputs = final_state.get("raw_tool_outputs")
    if not isinstance(raw_outputs, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in raw_outputs:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        sources.append(
            {
                "source_id": source_id,
                "source_type": "raw_tool_output",
                "label": f"Raw tool output: {item.get('tool_name', 'unknown')}",
                "summary": _summary_from_value(item.get("output", item.get("content", ""))),
                "tool_name": item.get("tool_name", "unknown"),
                "output_sha256": item.get("output_sha256"),
                "bytes": item.get("bytes")
                or len(_summary_from_value(item.get("output", item.get("content", "")), limit=4000).encode("utf-8")),
                "citeable": True,
            }
        )
    return sources


def enrich_source_registry_with_claims(
    source_registry: dict[str, Any] | None,
    claim_objects: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    registry = deepcopy(source_registry) if isinstance(source_registry, dict) else {}
    sources = normalize_source_objects(registry.get("source_objects"))
    source_index = {
        source["source_id"]: dict(source)
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    claims = claim_objects if isinstance(claim_objects, list) else []

    claim_ids: list[str] = []
    claim_source_ids: list[str] = []
    source_claim_index: dict[str, list[str]] = {source_id: [] for source_id in source_index}
    seen_claim_source_ids: set[str] = set()

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id")
        if isinstance(claim_id, str) and claim_id.strip():
            claim_ids.append(claim_id)
        for source_id in claim.get("source_ids", []):
            if not isinstance(source_id, str) or not source_id.strip():
                continue
            if source_id not in seen_claim_source_ids:
                seen_claim_source_ids.add(source_id)
                claim_source_ids.append(source_id)
            source_claim_index.setdefault(source_id, [])
            if isinstance(claim_id, str) and claim_id.strip() and claim_id not in source_claim_index[source_id]:
                source_claim_index[source_id].append(claim_id)
            if source_id in source_index:
                source_index[source_id]["claim_ids"] = _merge_unique_str_lists(
                    source_index[source_id].get("claim_ids"),
                    [claim_id] if isinstance(claim_id, str) else [],
                )
                source_index[source_id]["claim_source_ids"] = _merge_unique_str_lists(
                    source_index[source_id].get("claim_source_ids"),
                    claim.get("source_ids"),
                )

    registry["source_index"] = source_index
    registry["source_objects"] = [source_index[source["source_id"]] for source in sources if source["source_id"] in source_index]
    registry["source_ids"] = list(source_index)
    registry["citable_source_ids"] = [
        source_id for source_id, source in source_index.items() if source.get("citeable", True)
    ]
    registry["claim_ids"] = claim_ids
    registry["claim_source_ids"] = claim_source_ids
    registry["source_claim_index"] = {key: value for key, value in source_claim_index.items() if value}
    registry["source_summary"] = {
        **(registry.get("source_summary") if isinstance(registry.get("source_summary"), dict) else {}),
        "source_count": len(registry["source_objects"]),
        "citable_source_count": sum(1 for source in registry["source_objects"] if source.get("citeable", True)),
        "claim_count": len(claim_ids),
        "claim_source_count": len(claim_source_ids),
    }
    return registry


def build_source_registry(
    final_state: dict[str, Any],
    extra_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources = normalize_source_objects(final_state.get("source_objects"))
    sources.extend(build_report_source_objects(final_state))
    sources.extend(build_raw_tool_source_objects(final_state))
    if extra_sources:
        sources.extend(normalize_source_objects(extra_sources))

    claim_graph = final_state.get("claim_graph")
    if isinstance(claim_graph, dict):
        sources.extend(normalize_source_objects(claim_graph.get("source_objects")))

    deduped = _dedupe_sources(sources)
    source_index = {source["source_id"]: source for source in deduped}
    registry = {
        "source_objects": deduped,
        "source_index": source_index,
        "source_ids": list(source_index),
        "citable_source_ids": [source_id for source_id, source in source_index.items() if source.get("citeable", True)],
        "report_source_ids": [
            source["source_id"]
            for source in deduped
            if source.get("source_type") in {spec[1] for spec in REPORT_SOURCE_SPECS}
        ],
        "claim_source_ids": [
            source["source_id"]
            for source in deduped
            if str(source.get("source_type", "")).startswith("claim_")
        ],
        "source_summary": {
            "source_count": len(deduped),
            "citable_source_count": sum(1 for source in deduped if source.get("citeable", True)),
        },
    }
    claim_graph = final_state.get("claim_graph")
    if isinstance(claim_graph, dict):
        return enrich_source_registry_with_claims(registry, claim_graph.get("claim_objects"))
    return registry


def validate_source_citations(source_registry: dict[str, Any], cited_ids: list[str]) -> list[str]:
    source_index = source_registry.get("source_index")
    if not isinstance(source_index, dict):
        source_index = {}
    invalid: list[str] = []
    for source_id in cited_ids:
        if source_id not in source_index:
            invalid.append(source_id)
    return invalid
