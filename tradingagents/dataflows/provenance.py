"""Structured provenance metadata for text returned by data tools."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

PROVENANCE_SCHEMA_VERSION = "data-provenance-v1"


@dataclass(frozen=True)
class DataProvenance:
    method: str
    category: str
    source: str | None
    status: str
    quality: str
    analysis_cutoff: str | None
    fetched_at: str
    data_as_of: str | None = None
    point_in_time: str = "unknown"
    attempted_sources: list[dict[str, str]] = field(default_factory=list)
    schema_version: str = PROVENANCE_SCHEMA_VERSION


@dataclass(frozen=True)
class DataResult:
    """Provider payload plus bounded, non-secret provenance metadata."""

    content: Any
    provenance: DataProvenance

    def metadata(self) -> dict[str, Any]:
        return asdict(self.provenance)

    def render(self) -> str:
        metadata = self.metadata()
        source = metadata["source"] or "unavailable"
        cutoff = metadata["analysis_cutoff"] or "not_provided"
        as_of = metadata["data_as_of"] or "not_reported"
        header = (
            "DATA_PROVENANCE: "
            f"source={source}; status={metadata['status']}; quality={metadata['quality']}; "
            f"data_as_of={as_of}; analysis_cutoff={cutoff}; "
            f"fetched_at={metadata['fetched_at']}; point_in_time={metadata['point_in_time']}"
        )
        machine = "<!-- TA_DATA_PROVENANCE: " + json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
        ) + " -->"
        if isinstance(self.content, str):
            body = self.content
        else:
            body = json.dumps(self.content, default=str, sort_keys=True)
        return f"{machine}\n{header}\n\n{body}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
