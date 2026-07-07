"""Shared base model and timestamp rules for all Pro contracts."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

# Bumped whenever a contract changes shape incompatibly. Persisted payloads
# (memory, audit log, backtest caches) carry this so later phases can migrate.
# 0.2: MarketSnapshot grew an optional ``news`` list (additive; 0.1 payloads
#      still validate).
SCHEMA_VERSION = "0.2"


def utc_now() -> datetime:
    """Timezone-aware current time; the only sanctioned "now" for contracts."""
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    """Base for every contract model.

    - ``frozen``: instances are immutable snapshots of what an agent or feed
      said at a point in time; downstream nodes derive new objects via
      ``model_copy(update=...)`` instead of mutating history.
    - ``extra="forbid"``: unknown fields fail validation, so schema drift
      between agents and consumers surfaces immediately.
    - Naive datetimes are rejected everywhere: an ambiguous timestamp in a
      trading system is a lookahead bug waiting to happen. Aware datetimes
      are normalized to UTC.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _require_utc(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("naive datetime not allowed; pass a timezone-aware value")
            return value.astimezone(timezone.utc)
        return value
