"""Cross-source news consistency detection.

Clusters news items by event and flags items confirmed by multiple vendors.
Uses LLM semantic clustering when available, with n-gram Jaccard fallback.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from tradingagents.observability.provenance import (
    current_provenance_observer,
    direct_data_scope,
)

from .config import get_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM factory helper
# ---------------------------------------------------------------------------


def create_llm_from_config() -> Any | None:
    """Create a lightweight LLM instance from the current config.

    Returns ``None`` when the provider is unconfigured or creation fails
    (e.g. missing API key).  Callers should fall back to non-LLM heuristics.
    """
    cfg = get_config()
    provider = cfg.get("llm_provider")
    model = cfg.get("quick_think_llm")
    if not provider or not model:
        return None

    try:
        from tradingagents.llm_clients import create_llm_client

        observer = current_provenance_observer()
        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=cfg.get("backend_url"),
            **({"callbacks": [observer]} if observer is not None else {}),
        )
        return client.get_llm()
    except Exception as exc:
        logger.debug("Failed to create LLM for consistency check: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Event clustering
# ---------------------------------------------------------------------------


def cluster_news_by_event(
    items: list[dict[str, Any]],
    llm: Any | None = None,
) -> list[list[int]]:
    """Group *items* by the real-world event they describe.

    Returns a list of clusters, where each cluster is a list of item indices.
    When *llm* is provided, uses a single batch LLM call for semantic
    clustering; otherwise falls back to n-gram Jaccard similarity.
    """
    if len(items) <= 1:
        return [[i] for i in range(len(items))]

    if llm is not None:
        try:
            return _cluster_via_llm(items, llm)
        except Exception as exc:
            logger.warning("LLM clustering failed, falling back to n-gram: %s", exc)

    return _cluster_via_ngram(items, items, 0.3)


def _cluster_via_llm(
    items: list[dict[str, Any]],
    llm: Any,
) -> list[list[int]]:
    """Cluster items using a single batch LLM call."""
    lines = []
    for idx, item in enumerate(items):
        source = item.get("source", "?")
        title = (item.get("title") or "Untitled").replace("\n", " ")[:120]
        lines.append(f"{idx}. [{source}] {title}")

    numbered_list = "\n".join(lines)
    prompt = (
        "You are a news deduplication assistant. Below is a list of news headlines "
        "from different sources. Group the headlines that describe the SAME real-world "
        "event into clusters.\n\n"
        f"Headlines:\n{numbered_list}\n\n"
        "Return ONLY a JSON array of arrays, where each inner array contains the "
        "indices of headlines about the same event. Example: [[0, 3], [1, 2], [4]]\n"
        "Do NOT include any explanation — only the JSON."
    )

    with direct_data_scope("consistency.clustering"):
        response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    clusters = _parse_cluster_json(content, len(items))

    # Validate: every index must appear exactly once
    all_indices = {i for cluster in clusters for i in cluster}
    expected = set(range(len(items)))
    if all_indices != expected:
        raise ValueError(f"LLM returned incomplete clusters: got {all_indices}, expected {expected}")

    return clusters


def _parse_cluster_json(text: str, n_items: int) -> list[list[int]]:
    """Parse LLM response into a list of clusters."""
    # Extract JSON from possible markdown code fences
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in LLM response: {text[:200]}")

    raw = json.loads(match.group(0))

    clusters: list[list[int]] = []
    seen: set[int] = set()
    for group in raw:
        if not isinstance(group, list):
            continue
        indices = []
        for idx in group:
            idx_int = int(idx)
            if 0 <= idx_int < n_items and idx_int not in seen:
                indices.append(idx_int)
                seen.add(idx_int)
        if indices:
            clusters.append(sorted(indices))

    # Add any missing indices as singletons
    for i in range(n_items):
        if i not in seen:
            clusters.append([i])

    return clusters


# ---------------------------------------------------------------------------
# n-gram Jaccard fallback
# ---------------------------------------------------------------------------


def _cluster_via_ngram(
    items: list[dict[str, Any]],
    _unused: Any,
    threshold: float,
) -> list[list[int]]:
    """Cluster items using n-gram Jaccard similarity (no LLM required)."""
    n = len(items)
    titles = [_normalise_title(item.get("title") or "") for item in items]
    ngram_sets = [_title_ngrams(t, 3) for t in titles]

    # Union-Find for clustering
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            # Same source → no need to cluster
            src_i = items[i].get("source", "")
            src_j = items[j].get("source", "")
            if src_i and src_j and src_i == src_j:
                continue
            if _jaccard(ngram_sets[i], ngram_sets[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return [sorted(indices) for indices in groups.values()]


def _normalise_title(title: str) -> str:
    """Lowercase, strip punctuation and excess whitespace."""
    text = title.lower().strip()
    text = re.sub(r"[^\w一-鿿]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_ngrams(title: str, n: int) -> set[str]:
    """Character n-grams of *title*."""
    if len(title) < n:
        return {title}
    return {title[i : i + n] for i in range(len(title) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Attach cross-source info
# ---------------------------------------------------------------------------


def attach_cross_source_info(
    items: list[dict[str, Any]],
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    """Cluster items by event and annotate each with cross-source metadata.

    Mutates *items* in-place and returns it for chaining.
    """
    cfg = get_config()
    if not cfg.get("consistency_enabled", True):
        return items

    clusters = cluster_news_by_event(items, llm)

    for cluster_id, indices in enumerate(clusters):
        vendors = {items[i].get("source", "unknown") for i in indices}
        count = len(vendors)
        tag = "confirmed" if count >= 2 else "single_source"
        for i in indices:
            items[i]["event_cluster_id"] = cluster_id
            items[i]["cross_source_count"] = count
            items[i]["cross_source_vendors"] = sorted(vendors)
            items[i]["cross_source_tag"] = tag

    return items


def cross_source_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    """Return counts of confirmed vs single-source items."""
    confirmed = sum(1 for it in items if it.get("cross_source_tag") == "confirmed")
    return {
        "confirmed": confirmed,
        "single_source": len(items) - confirmed,
    }
