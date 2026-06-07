"""Data quality metadata for India data blocks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal


Confidence = Literal["high", "medium", "low", "unavailable"]


@dataclass(frozen=True)
class DataQuality:
    source: str
    as_of: str
    coverage: str
    staleness: str
    confidence: Confidence
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def unavailable(cls, source: str, reason: str) -> "DataQuality":
        return cls(
            source=source,
            as_of=datetime.now(timezone.utc).isoformat(),
            coverage="unavailable",
            staleness="unknown",
            confidence="unavailable",
            warnings=[reason],
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        warnings = "; ".join(self.warnings) if self.warnings else "None"
        return (
            f"Source: {self.source}\n"
            f"As of: {self.as_of}\n"
            f"Coverage: {self.coverage}\n"
            f"Staleness: {self.staleness}\n"
            f"Confidence: {self.confidence}\n"
            f"Warnings: {warnings}"
        )


def unavailable_response(source: str, symbol: str, reason: str) -> str:
    quality = DataQuality.unavailable(source, reason)
    return (
        f"UNAVAILABLE: {reason}\n\n"
        f"Symbol: {symbol}\n\n"
        "Data quality:\n"
        f"{quality.to_markdown()}\n\n"
        "Do not estimate or fabricate this data. Use local files under "
        "`data/india/manual/` or `data/india/filings/` when available."
    )
