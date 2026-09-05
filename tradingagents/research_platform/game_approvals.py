"""Normalized game approvals and conservative listed-company matching."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GameApprovalKind(str, Enum):
    DOMESTIC = "domestic"
    IMPORTED = "imported"


class GameCompanyMatchStatus(str, Enum):
    MATCHED = "matched"
    REVIEW_REQUIRED = "review_required"
    UNMATCHED = "unmatched"


class GameApprovalRecord(BaseModel):
    """One normalized approval published by the NPPA."""

    model_config = ConfigDict(frozen=True)

    approval_id: str = Field(min_length=1)
    kind: GameApprovalKind
    game_name: str = Field(min_length=1)
    application_category: str | None = None
    publishing_entity: str = Field(min_length=1)
    operating_entity: str = Field(min_length=1)
    approval_number: str = Field(min_length=1)
    isbn: str | None = None
    approval_date: date
    source_url: str = Field(min_length=1)
    available_as_of: date
    retrieved_at: datetime


class GameApprovalMatch(BaseModel):
    """Approval plus an exact, review-required, or unmatched company decision."""

    model_config = ConfigDict(frozen=True)

    approval: GameApprovalRecord
    status: GameCompanyMatchStatus
    symbol: str | None = None
    matched_entity_name: str | None = None
    relationship_source_url: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)


class GameApprovalDigest(BaseModel):
    """Point-in-time approval view for one covered company."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of_date: date
    approvals: list[GameApprovalMatch] = Field(default_factory=list)
    matched_count: int = Field(default=0, ge=0)
    latest_approval_date: date | None = None


# Only legal entities supported by an official company source are eligible for
# automatic attribution. Brand-like names outside this map are held for review.
_ENTITY_SYMBOLS = {
    "002602": {
        "\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8",
        "\u76db\u8da3\u4fe1\u606f\u6280\u672f\uff08\u4e0a\u6d77\uff09\u6709\u9650\u516c\u53f8",
    },
    "002624": {
        "\u5b8c\u7f8e\u4e16\u754c\uff08\u5317\u4eac\uff09\u8f6f\u4ef6\u79d1\u6280\u53d1\u5c55\u6709\u9650\u516c\u53f8",
        "\u5b8c\u7f8e\u4e16\u754c\uff08\u91cd\u5e86\uff09\u4e92\u52a8\u79d1\u6280\u6709\u9650\u516c\u53f8",
        "\u4e0a\u6d77\u5b8c\u7f8e\u65f6\u7a7a\u8f6f\u4ef6\u6709\u9650\u516c\u53f8",
        "\u6210\u90fd\u5b8c\u7f8e\u5929\u667a\u6e38\u79d1\u6280\u6709\u9650\u516c\u53f8",
        "\u82cf\u5dde\u5e7b\u5854\u7f51\u7edc\u79d1\u6280\u6709\u9650\u516c\u53f8",
        "\u5317\u4eac\u5b8c\u7f8e\u8d64\u91d1\u79d1\u6280\u6709\u9650\u516c\u53f8",
    },
}
_REVIEW_TOKENS = {
    "002602": ("\u76db\u8da3", "\u6570\u9f99", "\u70b9\u70b9\u4e92\u52a8"),
    "002624": ("\u5b8c\u7f8e\u4e16\u754c", "\u5b8c\u7f8e\u65f6\u7a7a", "\u5e7b\u5854"),
}
_RELATIONSHIP_SOURCES = {
    "002602": "https://static.cninfo.com.cn/finalpage/2023-12-14/1218603909.PDF",
    "002624": "https://www.wanmei.com/safestatic/20210816privacy.html",
}


def make_approval_id(kind: GameApprovalKind, approval_number: str, game_name: str) -> str:
    """Build a stable source-independent identifier."""

    value = "|".join((kind.value, _normalize(approval_number), _normalize(game_name)))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def match_game_approval(record: GameApprovalRecord) -> GameApprovalMatch:
    """Attribute an approval only when a publisher/operator legal name is exact."""

    entities = (record.publishing_entity, record.operating_entity)
    exact: dict[str, str] = {}
    for entity in entities:
        normalized = _normalize(entity)
        for symbol, aliases in _ENTITY_SYMBOLS.items():
            if normalized in {_normalize(alias) for alias in aliases}:
                exact[symbol] = entity

    if len(exact) == 1:
        symbol, entity = next(iter(exact.items()))
        return GameApprovalMatch(
            approval=record,
            status=GameCompanyMatchStatus.MATCHED,
            symbol=symbol,
            matched_entity_name=entity,
            relationship_source_url=_RELATIONSHIP_SOURCES[symbol],
            confidence=1.0,
            reason="Exact legal-entity match from the curated company relationship map.",
        )
    if len(exact) > 1:
        return GameApprovalMatch(
            approval=record,
            status=GameCompanyMatchStatus.REVIEW_REQUIRED,
            confidence=0.0,
            reason="Publisher and operator map to different covered companies.",
        )

    review_symbols = {
        symbol
        for symbol, tokens in _REVIEW_TOKENS.items()
        if any(token in entity for token in tokens for entity in entities)
    }
    if review_symbols:
        return GameApprovalMatch(
            approval=record,
            status=GameCompanyMatchStatus.REVIEW_REQUIRED,
            confidence=0.0,
            reason="A covered-company brand token matched, but the legal entity was not exact.",
        )
    return GameApprovalMatch(
        approval=record,
        status=GameCompanyMatchStatus.UNMATCHED,
        confidence=0.0,
        reason="No covered legal entity matched.",
    )


class JsonGameApprovalStore:
    """Atomic local JSONL store for official approval records."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "game_approvals" / "approvals.jsonl"

    def save(self, records: Sequence[GameApprovalRecord]) -> None:
        existing = {item.approval_id: item for item in self.list()}
        existing.update({item.approval_id: item for item in records})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".jsonl.tmp")
        ordered = sorted(existing.values(), key=lambda item: (item.approval_date, item.approval_id))
        temporary.write_text(
            "".join(f"{item.model_dump_json()}\n" for item in ordered), encoding="utf-8"
        )
        temporary.replace(self.path)

    def list(
        self,
        *,
        start: date = date.min,
        end: date = date.max,
        as_of_date: date | None = None,
        kinds: Iterable[GameApprovalKind] | None = None,
    ) -> list[GameApprovalRecord]:
        if not self.path.exists():
            return []
        allowed = set(kinds) if kinds is not None else None
        records = [
            GameApprovalRecord.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            item
            for item in records
            if start <= item.approval_date <= end
            and (as_of_date is None or item.available_as_of <= as_of_date)
            and (allowed is None or item.kind in allowed)
        ]

    def digest(self, symbol: str, *, as_of_date: date | None = None) -> GameApprovalDigest:
        normalized_symbol = symbol.strip().upper()
        reference_date = as_of_date or date.today()
        matches = [
            match
            for record in self.list(as_of_date=reference_date)
            if (match := match_game_approval(record)).symbol == normalized_symbol
        ]
        matches.sort(key=lambda item: item.approval.approval_date, reverse=True)
        return GameApprovalDigest(
            symbol=normalized_symbol,
            as_of_date=reference_date,
            approvals=matches,
            matched_count=len(matches),
            latest_approval_date=(matches[0].approval.approval_date if matches else None),
        )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"[\s\u3000]", "", normalized).casefold()
