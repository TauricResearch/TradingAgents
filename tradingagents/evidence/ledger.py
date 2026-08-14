"""In-memory evidence ledger for deterministic tool outputs."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tradingagents.evidence.models import EvidenceItem


def stable_json_hash(value: Any) -> str:
    """Return a deterministic short SHA256 hash for normalized data."""
    encoded = json.dumps(
        _normalize_for_json(value),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12].upper()


class EvidenceLedger:
    """Runtime-only ledger for evidence items and aliases."""

    def __init__(self, items: list[EvidenceItem] | None = None):
        self._items: dict[str, EvidenceItem] = {}
        self._aliases: dict[str, str] = {}
        for item in items or []:
            self._store(item)

    def register(
        self,
        source: str,
        title: str,
        as_of_date: str,
        payload: Any,
        aliases: list[str] | None = None,
        evidence_id: str | None = None,
    ) -> EvidenceItem:
        if evidence_id is None:
            evidence_id = self._make_evidence_id(source, title, as_of_date, payload)
        item = EvidenceItem(
            evidence_id=evidence_id,
            source=source,
            title=title,
            as_of_date=as_of_date,
            payload=payload,
            aliases=list(aliases or []),
        )
        return self._store(item)

    def resolve(self, ref: str) -> str | None:
        if ref in self._items:
            return ref
        return self._aliases.get(ref)

    def has(self, ref: str) -> bool:
        return self.resolve(ref) is not None

    def list_items(self) -> list[EvidenceItem]:
        return [item.model_copy(deep=True) for item in self._items.values()]

    def to_dict(self) -> dict[str, Any]:
        return {"items": [_item_snapshot(item) for item in self.list_items()]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvidenceLedger:
        return cls([EvidenceItem(**item) for item in value.get("items", [])])

    def _store(self, item: EvidenceItem) -> EvidenceItem:
        candidate = item.model_copy(deep=True)
        existing = self._items.get(candidate.evidence_id)
        if existing is not None:
            if _item_snapshot(existing) != _item_snapshot(candidate):
                raise ValueError(
                    f"Evidence id {candidate.evidence_id} already exists with different content"
                )
            return existing.model_copy(deep=True)

        mapped_id = self._aliases.get(candidate.evidence_id)
        if mapped_id is not None and mapped_id != candidate.evidence_id:
            raise ValueError(
                f"Evidence id {candidate.evidence_id} already exists as alias for {mapped_id}"
            )

        for alias in candidate.aliases:
            if alias in self._items and alias != candidate.evidence_id:
                raise ValueError(
                    f"Evidence alias {alias} already exists as an evidence id"
                )
            mapped_id = self._aliases.get(alias)
            if mapped_id is not None and mapped_id != candidate.evidence_id:
                raise ValueError(
                    f"Evidence alias {alias} already maps to {mapped_id}"
                )

        self._items[candidate.evidence_id] = candidate.model_copy(deep=True)
        for alias in candidate.aliases:
            self._aliases[alias] = candidate.evidence_id
        return candidate.model_copy(deep=True)

    @staticmethod
    def _make_evidence_id(source: str, title: str, as_of_date: str, payload: Any) -> str:
        digest = stable_json_hash(
            {
                "source": source,
                "title": title,
                "as_of_date": as_of_date,
                "payload": payload,
            }
        )
        return f"EVD-{digest}"


def _item_snapshot(item: EvidenceItem) -> dict[str, Any]:
    return _normalize_for_json(item.model_dump())


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, Mapping):
        return {
            str(_normalize_for_json(key)): _normalize_for_json(item_value)
            for key, item_value in value.items()
        }
    if isinstance(value, (set, frozenset)):
        try:
            sorted_items = sorted(value)
        except TypeError:
            sorted_items = list(value)
        return [_normalize_for_json(item) for item in sorted_items]
    if isinstance(value, tuple):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, list):
        return [_normalize_for_json(item) for item in value]
    return value
