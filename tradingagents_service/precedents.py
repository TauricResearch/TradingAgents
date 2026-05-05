from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class PrecedentDocument:
    run_id: str
    ticker: str
    trade_date: str
    content_text: str
    content_hash: str
    embedding: list[float]
    metadata: dict[str, Any]
    embedding_model: str = "hashed-bow-v1"


def tokenize(text: str) -> list[str]:
    return [match.group(0) for match in _TOKEN_RE.finditer((text or "").lower())]


def stable_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_embedding(text: str, *, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        weight_seed = int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF
        weight = 0.5 + weight_seed
        vector[bucket] += weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))


def build_precedent_document(
    *,
    run_id: str,
    ticker: str,
    trade_date: str,
    content_text: str,
    metadata: dict[str, Any] | None = None,
    embedding_model: str = "hashed-bow-v1",
) -> PrecedentDocument:
    normalized_metadata = metadata or {}
    content_hash = stable_hash(content_text)
    embedding = build_embedding(content_text)
    return PrecedentDocument(
        run_id=run_id,
        ticker=ticker,
        trade_date=trade_date,
        content_text=content_text,
        content_hash=content_hash,
        embedding=embedding,
        metadata=normalized_metadata,
        embedding_model=embedding_model,
    )


def precedent_document_to_dict(document: PrecedentDocument) -> dict[str, Any]:
    return asdict(document)


def build_precedent_query_text(*, run: Any, output: Any | None, quality: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    parts.append(f"ticker: {getattr(run, 'ticker', '')}")
    parts.append(f"trade_date: {getattr(run, 'trade_date', '')}")
    parts.append(f"provider: {getattr(run, 'provider', '')}")
    parts.append(f"model: {getattr(run, 'model', '')}")
    if output is not None:
        parts.append(f"final_rating: {getattr(output, 'final_rating', '')}")
        parts.append(f"decision_markdown: {getattr(output, 'decision_markdown', '')}")
    if quality:
        parts.append(json.dumps(quality, sort_keys=True, default=str))
    return "\n".join(str(part) for part in parts if part)
