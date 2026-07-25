"""Deterministic contracts for the cost-aware news-analysis pipeline.

The module deliberately does not call an LLM or a vendor.  It is the stable
boundary used by collectors and agents: Layer 0 removes obvious low-value
items, Layer 1 produces a compact batch payload for a small model, and Layer 2
creates an explicit, cacheable request only when deeper review is justified.
No private model reasoning is accepted or persisted by these contracts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SentimentCode = Literal["+", "-", "0", "?"]
Layer2Reason = Literal["evidence_thin", "source_divergence", "material_conflict"]

_LISTICLE_RE = re.compile(r"\b(?:top|best|worst|most)\s+\d+\b|\d+\s*(?:只|大|个).{0,12}(?:股票|公司)", re.I)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Layer0Decision:
    item_id: str
    accepted: bool
    reason: str


@dataclass(frozen=True)
class Layer1Batch:
    """A provider-neutral compact batch request.

    ``payload`` intentionally contains source metadata and snippets only.  It
    never carries chain-of-thought instructions or requests a rationale.
    """

    item_ids: tuple[str, ...]
    payload: str


@dataclass(frozen=True)
class Layer1Sentiment:
    item_id: str
    sentiment: SentimentCode
    confidence: float | None = None


@dataclass(frozen=True)
class Layer2Trigger:
    should_run: bool
    reasons: tuple[Layer2Reason, ...]
    cache_key: str | None


class DeepAnalysisCache:
    """Small in-memory cache boundary for sanitized Layer 2 conclusions.

    Callers may replace this with a durable artifact store.  The value is a
    reviewable final conclusion, not raw model transcripts or private thought.
    """

    def __init__(self) -> None:
        self._values: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        value = self._values.get(key)
        return dict(value) if value is not None else None

    def put(self, key: str, conclusion: Mapping[str, Any]) -> None:
        self._values[key] = _public_conclusion(conclusion)


class FileDeepAnalysisCache:
    """A small durable cache for the *public* Layer 2 conclusion.

    Each cache entry is content-addressed by :func:`decide_layer2`.  We write
    only a sanitized JSON object: prompts, raw provider responses and private
    model reasoning are never cache inputs.  A corrupt entry is treated as a
    cache miss so an interrupted local write cannot block news analysis.
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path_for(key)
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return None
        return _public_conclusion(value) if isinstance(value, Mapping) else None

    def put(self, key: str, conclusion: Mapping[str, Any]) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        sanitized = _public_conclusion(conclusion)
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(sanitized, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            os.replace(temporary, path)
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _path_for(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("Layer 2 cache key must be a SHA-256 hex digest")
        return self._directory / f"{key}.json"


def layer0_filter(items: Sequence[Mapping[str, Any]]) -> list[Layer0Decision]:
    """Apply explainable spam/listicle/duplicate filters before any model use."""
    seen_titles: set[str] = set()
    decisions: list[Layer0Decision] = []
    for index, item in enumerate(items):
        item_id = _item_id(item, index)
        title = _normalise_text(item.get("title"))
        excerpt = _normalise_text(item.get("content") or item.get("summary"))
        if not title:
            decisions.append(Layer0Decision(item_id, False, "missing_title"))
        elif _LISTICLE_RE.search(title):
            decisions.append(Layer0Decision(item_id, False, "listicle"))
        elif len(excerpt) < 24:
            decisions.append(Layer0Decision(item_id, False, "insufficient_excerpt"))
        elif title.casefold() in seen_titles:
            decisions.append(Layer0Decision(item_id, False, "duplicate_title"))
        else:
            seen_titles.add(title.casefold())
            decisions.append(Layer0Decision(item_id, True, "accepted"))
    return decisions


def build_layer1_batch(
    items: Sequence[Mapping[str, Any]], decisions: Sequence[Layer0Decision], *, max_items: int = 50
) -> Layer1Batch:
    """Encode up to 50 accepted articles with single-character sentiment output.

    Compact schema: ``[{"i":"id","t":"title","u":"uri","x":"excerpt"}]``.
    The Layer 1 model must return ``[{"i":"id","s":"+|-|0|?","c":0..1}]``.
    """
    accepted = {decision.item_id for decision in decisions if decision.accepted}
    compact: list[dict[str, str]] = []
    for index, item in enumerate(items):
        item_id = _item_id(item, index)
        if item_id not in accepted:
            continue
        compact.append(
            {
                "i": item_id,
                "t": _normalise_text(item.get("title"))[:180],
                "u": str(item.get("url") or "")[:300],
                "x": _normalise_text(item.get("content") or item.get("summary"))[:500],
            }
        )
        if len(compact) >= max_items:
            break
    return Layer1Batch(
        item_ids=tuple(row["i"] for row in compact),
        payload=json.dumps(compact, ensure_ascii=False, separators=(",", ":")),
    )


def parse_layer1_sentiment(raw: str | Sequence[Mapping[str, Any]], batch: Layer1Batch) -> list[Layer1Sentiment]:
    """Validate compact Layer 1 output; malformed rows become ``?`` safely."""
    parsed = json.loads(raw) if isinstance(raw, str) else list(raw)
    if not isinstance(parsed, list):
        raise ValueError("Layer 1 output must be a JSON list")
    allowed = set(batch.item_ids)
    by_id: dict[str, Layer1Sentiment] = {}
    for row in parsed:
        if not isinstance(row, Mapping):
            continue
        item_id = str(row.get("i") or "")
        if item_id not in allowed or item_id in by_id:
            continue
        sentiment = str(row.get("s") or "?")
        code: SentimentCode = sentiment if sentiment in {"+", "-", "0", "?"} else "?"
        confidence = _confidence(row.get("c"))
        by_id[item_id] = Layer1Sentiment(item_id, code, confidence)
    return [by_id.get(item_id, Layer1Sentiment(item_id, "?")) for item_id in batch.item_ids]


def decide_layer2(
    *,
    evidence_status: str,
    source_alignment: str | None = None,
    conflict_count: int = 0,
    conflict_severity: str | None = None,
    subject: str = "",
    data_as_of: str = "",
) -> Layer2Trigger:
    """Return a deterministic Layer 2 trigger and a content-addressed cache key."""
    reasons: list[Layer2Reason] = []
    if evidence_status.casefold() not in {"pass", "verified", "sufficient"}:
        reasons.append("evidence_thin")
    if source_alignment in {"Wide divergence", "Mixed"}:
        reasons.append("source_divergence")
    if conflict_count > 0 and (conflict_severity or "").casefold() in {"high", "critical"}:
        reasons.append("material_conflict")
    if not reasons:
        return Layer2Trigger(False, (), None)
    payload = {
        "subject": subject,
        "data_as_of": data_as_of,
        "evidence_status": evidence_status.casefold(),
        "source_alignment": source_alignment or "",
        "conflict_count": max(0, int(conflict_count)),
        "conflict_severity": (conflict_severity or "").casefold(),
        "reasons": reasons,
    }
    cache_key = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return Layer2Trigger(True, tuple(reasons), cache_key)


def _item_id(item: Mapping[str, Any], index: int) -> str:
    value = str(item.get("id") or item.get("url") or f"item-{index}")
    return value[:512]


def _normalise_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 <= parsed <= 1.0 else None


def _public_conclusion(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively reject private-reasoning fields at the cache boundary."""
    blocked = {"thinking", "reasoning", "chain_of_thought", "raw_response", "prompt", "analysis"}

    def sanitize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                str(key): sanitize(child)
                for key, child in item.items()
                if str(key).casefold() not in blocked
            }
        if isinstance(item, (list, tuple)):
            return [sanitize(child) for child in item]
        return item

    return sanitize(value)
