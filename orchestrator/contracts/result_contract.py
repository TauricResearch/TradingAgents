from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator.contracts.config_schema import CONTRACT_VERSION
from orchestrator.contracts.error_taxonomy import reason_code_value


def _normalize_metadata(
    metadata: Optional[dict[str, Any]],
    *,
    reason_code: Optional[str] = None,
) -> dict[str, Any]:
    normalized = dict(metadata or {})
    normalized.setdefault("contract_version", CONTRACT_VERSION)
    if reason_code:
        normalized.setdefault("reason_code", reason_code)
    return normalized


@dataclass
class Signal:
    ticker: str
    direction: int
    confidence: float
    source: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION
    reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        if self.reason_code is not None:
            self.reason_code = reason_code_value(self.reason_code)
        self.metadata = _normalize_metadata(self.metadata, reason_code=self.reason_code)
        self.reason_code = self.reason_code or self.metadata.get("reason_code")
        self.metadata.setdefault("source", self.source)

    @property
    def degraded(self) -> bool:
        return self.reason_code is not None or bool(self.metadata.get("error"))


@dataclass
class FinalSignal:
    ticker: str
    direction: int
    confidence: float
    quant_signal: Optional[Signal]
    llm_signal: Optional[Signal]
    timestamp: datetime
    degrade_reason_codes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        self.degrade_reason_codes = tuple(
            dict.fromkeys(code for code in self.degrade_reason_codes if code)
        )
        self.metadata = _normalize_metadata(self.metadata)
        if self.degrade_reason_codes:
            self.metadata.setdefault(
                "degrade_reason_codes",
                list(self.degrade_reason_codes),
            )

    @property
    def degraded(self) -> bool:
        return bool(self.degrade_reason_codes)


def build_error_signal(
    *,
    ticker: str,
    source: str,
    reason_code: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> Signal:
    payload = dict(metadata or {})
    payload["error"] = message
    return Signal(
        ticker=ticker,
        direction=0,
        confidence=0.0,
        source=source,
        timestamp=timestamp or datetime.now(timezone.utc),
        metadata=payload,
        reason_code=reason_code,
    )


def signal_reason_code(signal: Optional[Signal]) -> Optional[str]:
    if signal is None:
        return None
    return signal.reason_code or signal.metadata.get("reason_code")


class CombinedSignalFailure(ValueError):
    """Structured failure for cases where no merged signal can be produced."""

    def __init__(
        self,
        message: str,
        *,
        reason_codes: tuple[str, ...] = (),
        source_diagnostics: Optional[dict[str, Any]] = None,
        data_quality: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.reason_codes = tuple(reason_codes)
        self.source_diagnostics = dict(source_diagnostics or {})
        self.data_quality = dict(data_quality) if data_quality is not None else None
