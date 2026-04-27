"""Small JSON-backed circuit breaker for deterministic agent failures."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class CircuitBreakerOpen(RuntimeError):
    """Raised when a node has exceeded its configured failure threshold."""


class CircuitBreaker:
    """Track recent per-node failures in a stable JSON state file."""

    def __init__(
        self,
        *,
        state_path: str | Path,
        threshold: int,
        window_sec: float,
        enabled: bool = True,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self.threshold = max(1, int(threshold))
        self.window_sec = float(window_sec)
        self.enabled = bool(enabled)
        self._clock = clock or time.time

    def assert_available(self, node_name: str) -> None:
        """Raise when *node_name* is open within the rolling window."""
        if not self.enabled:
            return
        count = self.failure_count(node_name)
        if count < self.threshold:
            return
        raise CircuitBreakerOpen(
            f"{node_name} circuit breaker is open after {count} failures within "
            f"{self.window_sec:.0f}s; alert operators and pause auto-runs before retrying."
        )

    def failure_count(self, node_name: str) -> int:
        """Return active failure count after pruning expired entries."""
        if not self.enabled:
            return 0
        state = self._load_state()
        failures = self._active_failures(state, node_name)
        state.setdefault("nodes", {})[node_name] = failures
        self._save_state(state)
        return len(failures)

    def record_failure(self, node_name: str, reason: str) -> None:
        """Append a failure reason for *node_name* and raise when threshold is crossed."""
        if not self.enabled:
            return
        state = self._load_state()
        failures = self._active_failures(state, node_name)
        failures.append({"ts": self._clock(), "reason": str(reason)[:500]})
        state.setdefault("nodes", {})[node_name] = failures
        self._save_state(state)
        if len(failures) >= self.threshold:
            raise CircuitBreakerOpen(
                f"{node_name} circuit breaker is open after {len(failures)} failures within "
                f"{self.window_sec:.0f}s; alert operators and pause auto-runs before retrying."
            )

    def record_success(self, node_name: str) -> None:
        """Retain failure history; the rolling window alone closes the breaker."""
        if not self.enabled:
            return
        self.failure_count(node_name)

    def _active_failures(self, state: dict[str, Any], node_name: str) -> list[dict[str, Any]]:
        cutoff = self._clock() - self.window_sec
        nodes = state.setdefault("nodes", {})
        raw_failures = nodes.get(node_name, [])
        if not isinstance(raw_failures, list):
            return []
        active: list[dict[str, Any]] = []
        for failure in raw_failures:
            if not isinstance(failure, dict):
                continue
            try:
                ts = float(failure.get("ts"))
            except (TypeError, ValueError):
                continue
            if ts >= cutoff:
                active.append({"ts": ts, "reason": str(failure.get("reason") or "")[:500]})
        return active

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"nodes": {}}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"circuit breaker state is invalid JSON: {self.state_path}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"circuit breaker state must be a JSON object: {self.state_path}")
        payload.setdefault("nodes", {})
        if not isinstance(payload["nodes"], dict):
            raise RuntimeError(f"circuit breaker nodes state must be an object: {self.state_path}")
        return payload

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.state_path)


def circuit_breaker_state_path(config: dict[str, Any]) -> Path:
    configured = str(config.get("circuit_breaker_state_path") or "").strip()
    if configured:
        return Path(configured)
    results_dir = Path(str(config.get("results_dir") or "reports"))
    return results_dir / "runtime" / "circuit_breakers.json"


def circuit_breaker_from_config(
    config: dict[str, Any],
    *,
    clock: Callable[[], float] | None = None,
) -> CircuitBreaker:
    return CircuitBreaker(
        state_path=circuit_breaker_state_path(config),
        threshold=int(config.get("circuit_breaker_threshold") or 3),
        window_sec=float(config.get("circuit_breaker_window_sec") or 86_400),
        enabled=bool(config.get("circuit_breaker_enabled", True)),
        clock=clock,
    )
