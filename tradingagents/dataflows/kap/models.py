"""Stable application models decoupled from kap-client's wire models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

KapStatus = Literal[
    "ok",
    "not_bist",
    "company_not_found",
    "rate_limited",
    "timeout",
    "unavailable",
]


@dataclass(frozen=True)
class KapAttachment:
    filename: str
    url: str


@dataclass(frozen=True)
class KapDisclosure:
    published_at: datetime
    company: str
    ticker: str
    subject: str
    disclosure_type: str
    url: str
    has_attachment: bool
    is_corrective: bool
    disclosure_id: int
    summary: str = ""
    attachments: tuple[KapAttachment, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat(timespec="minutes")
        data["attachments"] = [asdict(item) for item in self.attachments]
        return data


@dataclass(frozen=True)
class KapDisclosureResult:
    status: KapStatus
    ticker: str
    kap_ticker: str | None
    start_date: str
    end_date: str
    message: str
    disclosures: tuple[KapDisclosure, ...] = field(default_factory=tuple)
    total_found: int = 0

    @property
    def available(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "ticker": self.ticker,
            "kap_ticker": self.kap_ticker,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "message": self.message,
            "total_found": self.total_found,
            "returned_count": len(self.disclosures),
            "disclosures": [item.to_dict() for item in self.disclosures],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))
