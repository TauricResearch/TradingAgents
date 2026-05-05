from __future__ import annotations

import re
from typing import Any


REPORT_SOURCE_SPECS = (
    ("market_report", "market", "Market analyst report"),
    ("news_report", "news", "News analyst report"),
    ("sentiment_report", "sentiment", "Sentiment analyst report"),
    ("fundamentals_report", "fundamentals", "Fundamentals analyst report"),
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
    }
    for key in _COMMON_FIELDS:
        value = source.get(key)
        if value is not None and key not in normalized:
            normalized[key] = value
    if isinstance(source.get("claim_ids"), list):
        normalized["claim_ids"] = [item for item in source["claim_ids"] if isinstance(item, str) and item.strip()]
    if isinstance(source.get("source_ids"), list):
        normalized["source_ids"] = [item for item in source["source_ids"] if isinstance(item, str) and item.strip()]
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


def build_source_registry(
    final_state: dict[str, Any],
    extra_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources = normalize_source_objects(final_state.get("source_objects"))
    if not sources:
        sources = build_report_source_objects(final_state)
    if extra_sources:
        sources.extend(normalize_source_objects(extra_sources))

    claim_graph = final_state.get("claim_graph")
    if isinstance(claim_graph, dict):
        sources.extend(normalize_source_objects(claim_graph.get("source_objects")))

    deduped = _dedupe_sources(sources)
    source_index = {source["source_id"]: source for source in deduped}
    return {
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


def validate_source_citations(source_registry: dict[str, Any], cited_ids: list[str]) -> list[str]:
    source_index = source_registry.get("source_index")
    if not isinstance(source_index, dict):
        source_index = {}
    invalid: list[str] = []
    for source_id in cited_ids:
        if source_id not in source_index:
            invalid.append(source_id)
    return invalid

