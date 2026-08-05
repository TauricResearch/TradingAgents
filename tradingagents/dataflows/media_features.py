"""Point-in-time narrative clustering and information-gain selection.

The collector intentionally stores immutable raw rows.  This module builds a
derived narrative view at read time so clustering improvements never rewrite
historical evidence or require a database migration.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

_STOPWORDS = {
    "a", "about", "after", "against", "all", "an", "and", "are", "as", "at",
    "be", "before", "but", "by", "for", "from", "has", "have", "in", "into",
    "is", "it", "its", "more", "new", "not", "of", "on", "or", "over", "says",
    "than", "that", "the", "their", "this", "to", "up", "was", "will", "with",
}

_SOURCE_FAMILIES = {
    "news": "company_news",
    "globalnews": "global_news",
    "trendnews": "global_news",
    "stocktwits": "retail_social",
    "reddit": "retail_social",
    "x": "public_social",
    "bluesky": "public_social",
    "truthsocial": "public_social",
}


def _row_text(row: dict) -> str:
    return " ".join((row.get("title") or row.get("body") or "").split())


def _tokens(row: dict) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", _row_text(row).lower())
    return frozenset(word for word in words if len(word) > 2 and word not in _STOPWORDS)


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def source_family(source: str) -> str:
    """Map raw providers to signal families that should not be pooled blindly."""
    return _SOURCE_FAMILIES.get((source or "").lower(), "other")


@dataclass(frozen=True)
class EventCluster:
    cluster_id: str
    representative: dict
    members: tuple[dict, ...]
    novelty: float
    score: float
    source_families: tuple[str, ...]
    publishers: tuple[str, ...]
    sentiment_disagreement: bool


def cluster_events(
    rows: list[dict],
    *,
    reference_rows: list[dict] | None = None,
    limit: int = 10,
    similarity_threshold: float = 0.34,
) -> list[EventCluster]:
    """Collapse near-duplicates and rank narratives by information gain.

    ``reference_rows`` must contain only older, point-in-time-eligible rows. It
    is used solely for novelty, never as content presented to the model.
    Ranking rewards novelty, independent publishers, cross-family confirmation,
    and mild repetition while logarithmically capping popularity.
    """
    if limit < 1:
        return []
    usable = [row for row in rows if _tokens(row)]
    usable.sort(key=lambda row: row.get("created_utc") or 0.0, reverse=True)
    groups: list[list[dict]] = []
    group_tokens: list[frozenset[str]] = []
    for row in usable:
        tokens = _tokens(row)
        best_index = None
        best_similarity = 0.0
        for index, existing in enumerate(group_tokens):
            similarity = _similarity(tokens, existing)
            if similarity > best_similarity:
                best_index = index
                best_similarity = similarity
        if best_index is not None and best_similarity >= similarity_threshold:
            groups[best_index].append(row)
            # The union lets differently worded follow-ups join a narrative.
            group_tokens[best_index] = group_tokens[best_index] | tokens
        else:
            groups.append([row])
            group_tokens.append(tokens)

    reference_tokens = [_tokens(row) for row in (reference_rows or []) if _tokens(row)]
    clusters = []
    for members, tokens in zip(groups, group_tokens, strict=True):
        representative = max(
            members,
            key=lambda row: (
                bool(row.get("title")),
                len(_row_text(row)),
                row.get("created_utc") or 0.0,
            ),
        )
        novelty = 1.0 - max(
            (_similarity(tokens, prior) for prior in reference_tokens), default=0.0
        )
        families = tuple(sorted({source_family(row.get("source", "")) for row in members}))
        publishers = tuple(sorted({
            str(row.get("author")).strip()
            for row in members if row.get("author")
        }))
        sentiments = {
            str(row.get("sentiment")).strip().lower()
            for row in members if row.get("sentiment")
        }
        disagreement = "bullish" in sentiments and "bearish" in sentiments
        # Novel narratives lead; diverse independent confirmation breaks ties.
        score = (
            novelty * 5.0
            + min(len(families) - 1, 2) * 1.5
            + min(max(len(publishers) - 1, 0), 3) * 0.6
            + math.log2(len(members) + 1) * 0.5
            + (0.5 if disagreement else 0.0)
        )
        identity = "|".join(sorted(
            f"{row.get('source', '')}:{row.get('external_id', '')}" for row in members
        ))
        clusters.append(EventCluster(
            cluster_id=hashlib.sha256(identity.encode()).hexdigest()[:12],
            representative=representative,
            members=tuple(members),
            novelty=novelty,
            score=score,
            source_families=families,
            publishers=publishers,
            sentiment_disagreement=disagreement,
        ))
    return sorted(
        clusters,
        key=lambda cluster: (
            cluster.score,
            cluster.representative.get("created_utc") or 0.0,
        ),
        reverse=True,
    )[:limit]
