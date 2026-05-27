"""Envelope: the single message shape on the ``ingest:raw`` Redis stream.

Adapters construct ``Envelope`` instances and call ``redis.xadd(stream, env.to_redis_fields())``.
The triage consumer reverses with ``Envelope.from_redis_fields(fields)``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_fingerprint(text: str) -> str:
    """Whitespace-collapsed, lowercased text for SHA-256 dedup hashing.

    Identical wording with different whitespace / casing must hash equal.
    """
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


@dataclass(frozen=True)
class Envelope:
    source: str            # "polygon_news", "telegram", "x", "rss", "gdelt", "macro"
    ingested_ts: str       # ISO-8601 UTC, e.g. "2026-05-26T14:33:21.123Z"
    external_id: str       # source-supplied stable ID; empty string if unavailable
    text: str              # normalized full text the LLM and embedder see
    source_tags: Dict[str, Any]  # e.g. {"tickers": ["AAPL"], "category": "earnings"}
    raw_path: str          # filesystem path under data/events/staging/...

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, blob: str) -> "Envelope":
        return cls(**json.loads(blob))

    def to_redis_fields(self) -> Dict[str, str]:
        # One field carries the whole JSON. Keeps XADD payload simple and avoids
        # collisions with Redis-reserved field names.
        return {"data": self.to_json()}

    @classmethod
    def from_redis_fields(cls, fields: Dict[str, str]) -> "Envelope":
        # Redis returns bytes when decode_responses=False; tolerate both.
        data = fields.get("data") or fields.get(b"data")
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return cls.from_json(data)
