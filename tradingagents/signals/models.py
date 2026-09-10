from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class NormalizedSignal(BaseModel):
    """A normalized signal produced by an external signal provider."""

    source: str = Field(
        ...,
        description="The provider or source that produced the signal.",
    )
    symbol: str = Field(
        ...,
        description="The symbol associated with the signal.",
    )
    signal_type: str = Field(
        ...,
        description="The type of signal, such as sentiment or momentum.",
    )
    score: float = Field(
        ...,
        description="The normalized score produced by the provider.",
    )
    timestamp: datetime = Field(
        ...,
        description="The UTC timestamp of the signal.",
    )
    confidence: float | None = Field(
        default=None,
        description="Optional confidence reported by the provider.",
    )
    provider_signal_id: str | None = Field(
        default=None,
        description=(
            "Optional provider-specific identifier for "
            "traceability and deduplication."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional provider-specific metadata or evidence.",
    )

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp_to_utc(cls, value: datetime) -> datetime:
        """Require a timezone-aware timestamp and normalize it to UTC."""
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")

        return value.astimezone(timezone.utc)