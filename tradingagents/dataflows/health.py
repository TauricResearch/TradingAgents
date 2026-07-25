"""Capability-scoped circuit breaker for data providers.

The registry intentionally has no knowledge of provider implementations. The
router records outcomes under a ``(vendor, market, capability)`` key so an
unhealthy quote endpoint cannot suppress an otherwise healthy news or
fundamentals endpoint from the same provider.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

RATE_LIMIT_COOLDOWN_SECONDS = 60.0
TRANSIENT_FAILURE_COOLDOWN_SECONDS = 20.0


@dataclass(frozen=True)
class VendorHealthKey:
    vendor: str
    market: str
    capability: str


@dataclass(frozen=True)
class Cooldown:
    key: VendorHealthKey
    reason: str
    retry_at: float

    def remaining_seconds(self, now: float) -> float:
        return max(0.0, self.retry_at - now)


class VendorHealthRegistry:
    """In-process provider cooldown state with an injectable monotonic clock."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._cooldowns: dict[VendorHealthKey, Cooldown] = {}

    def cooldown_for(
        self,
        *,
        vendor: str,
        market: str,
        capability: str,
    ) -> Cooldown | None:
        key = VendorHealthKey(vendor, market, capability)
        cooldown = self._cooldowns.get(key)
        if cooldown is None:
            return None
        if cooldown.retry_at <= self._clock():
            self._cooldowns.pop(key, None)
            return None
        return cooldown

    def record_failure(
        self,
        *,
        vendor: str,
        market: str,
        capability: str,
        cooldown_seconds: float,
        reason: str,
    ) -> None:
        if cooldown_seconds <= 0:
            return
        key = VendorHealthKey(vendor, market, capability)
        self._cooldowns[key] = Cooldown(
            key=key,
            reason=reason,
            retry_at=self._clock() + cooldown_seconds,
        )

    def record_success(self, *, vendor: str, market: str, capability: str) -> None:
        self._cooldowns.pop(VendorHealthKey(vendor, market, capability), None)

    def clear(self) -> None:
        self._cooldowns.clear()


# Process-global health registry instance (cooldown state shared by the router
# and the vendor-error recording helpers). Kept here so vendor_errors.py can
# import it without depending on the routing core.
_vendor_health = VendorHealthRegistry()


def set_vendor_health_registry(registry: VendorHealthRegistry) -> None:
    """Replace health state (dependency injection for deterministic tests)."""
    global _vendor_health
    _vendor_health = registry


def clear_vendor_health() -> None:
    """Clear in-process cooldowns without changing provider configuration."""
    _vendor_health.clear()
