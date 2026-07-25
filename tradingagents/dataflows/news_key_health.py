"""Secret-safe rotation and health tracking for keyed news providers.

Provider-level health alone cannot distinguish a throttled key from a healthy
second key at the same provider.  This module deliberately stores only a
stable, non-reversible identifier for each key; callers retain the raw key
only long enough to make the HTTP request.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

RATE_LIMIT_COOLDOWN_SECONDS = 60.0
TRANSIENT_FAILURE_COOLDOWN_SECONDS = 20.0


def key_id(value: str) -> str:
    """Return a stable identifier suitable for logs and health state.

    A digest, rather than a prefix or suffix, prevents an accidental progress
    event, exception, or artifact from exposing any part of an API credential.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class KeyCooldown:
    provider: str
    identifier: str
    reason: str
    retry_at: float

    def active(self, now: float) -> bool:
        return self.retry_at > now


class NewsProviderKeyPool:
    """Round-robin healthy keys for one provider with per-key cooldowns."""

    def __init__(self, provider: str, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.provider = provider
        self._clock = clock
        self._keys: tuple[str, ...] = ()
        self._next_index = 0
        self._cooldowns: dict[str, KeyCooldown] = {}

    def configure(self, keys: Iterable[str]) -> None:
        """Install an ordered, de-duplicated key list.

        The environment can change in a long-running local process.  Replacing
        the list resets round-robin state and removes health records for keys
        that no longer exist; health for retained keys is intentionally kept.
        """
        unique: list[str] = []
        seen: set[str] = set()
        for key in keys:
            candidate = str(key).strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            unique.append(candidate)
        next_keys = tuple(unique)
        if next_keys == self._keys:
            return
        retained = {key_id(key) for key in next_keys}
        self._cooldowns = {
            identifier: cooldown
            for identifier, cooldown in self._cooldowns.items()
            if identifier in retained
        }
        self._keys = next_keys
        self._next_index = 0

    def acquire(self) -> str | None:
        """Return the next healthy key, or ``None`` when none can be used."""
        if not self._keys:
            return None
        now = self._clock()
        for offset in range(len(self._keys)):
            index = (self._next_index + offset) % len(self._keys)
            candidate = self._keys[index]
            identifier = key_id(candidate)
            cooldown = self._cooldowns.get(identifier)
            if cooldown is not None and cooldown.active(now):
                continue
            if cooldown is not None:
                self._cooldowns.pop(identifier, None)
            self._next_index = (index + 1) % len(self._keys)
            return candidate
        return None

    def record_failure(self, key: str, *, cooldown_seconds: float, reason: str) -> None:
        if cooldown_seconds <= 0:
            return
        identifier = key_id(key)
        self._cooldowns[identifier] = KeyCooldown(
            provider=self.provider,
            identifier=identifier,
            reason=reason,
            retry_at=self._clock() + cooldown_seconds,
        )

    def record_success(self, key: str) -> None:
        self._cooldowns.pop(key_id(key), None)

    def clear(self) -> None:
        self._keys = ()
        self._next_index = 0
        self._cooldowns.clear()

    def status(self) -> tuple[KeyCooldown, ...]:
        """Expose non-secret cooldown facts for diagnostics and tests."""
        now = self._clock()
        return tuple(
            cooldown
            for cooldown in self._cooldowns.values()
            if cooldown.active(now)
        )
