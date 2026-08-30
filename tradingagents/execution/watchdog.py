"""Versus-like AI SRE watchdog — learns normal, alerts only on novelty."""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from typing import Any, Callable

logger = logging.getLogger(__name__)

_SECRET_KEYS = (
    "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "FRED_API_KEY",
    "BYMA_TOKEN", "ALPHA_VANTAGE_API_KEY",
)
_REDACT_RE = re.compile(r"(" + "|".join(re.escape(k) for k in _SECRET_KEYS) + r")\s*[:=]\s*['\"]?[^'\"\s,}]+['\"]?", re.IGNORECASE)


def redact(text: str) -> str:
    if not text:
        return text
    return _REDACT_RE.sub(lambda m: m.group(1) + "=***", text)


class ExecutionWatchdog:
    """Learns baseline (p95 latency, error rate, endpoint success) and alerts on anomaly."""

    def __init__(self, window_size: int = 200, max_calls_per_hour: int = 100, anomaly_z: float = 2.5, error_rate_threshold: float = 0.3, callback: Callable[[str, dict], None] | None = None) -> None:
        self.window_size = window_size
        self.max_calls_per_hour = max_calls_per_hour
        self.anomaly_z = anomaly_z
        self.error_rate_threshold = error_rate_threshold
        self.callback = callback
        self._window: deque[dict[str, Any]] = deque(maxlen=window_size)
        self._timestamps: deque[float] = deque()
        self._cache: dict[str, Any] = {}
        self._alerted = False

    def record_call(self, latency_ms: float, success: bool, endpoint: str) -> dict | None:
        """Record call; returns cached entry if pattern seen, else None. Always learns baseline."""
        now = time.time()
        while self._timestamps and now - self._timestamps[0] > 3600:
            self._timestamps.popleft()
        self._timestamps.append(now)
        cache_key = f"{endpoint}:{success}:{int(latency_ms // 100)}"
        cached = self._cache.get(cache_key)
        entry = {"latency_ms": float(latency_ms), "success": bool(success), "endpoint": redact(endpoint), "ts": now}
        self._window.append(entry)
        if len(self._timestamps) > self.max_calls_per_hour:
            self._route(redact(f"Rate limit exceeded: {len(self._timestamps)}/hour (limit {self.max_calls_per_hour})"), self._snapshot(alert=False))
        self._cache[cache_key] = entry
        if len(self._cache) > 512:
            self._cache.pop(next(iter(self._cache)))
        return cached

    def should_alert(self) -> bool:
        if len(self._window) < 20:
            return False
        lat = [e["latency_ms"] for e in self._window]
        mean = sum(lat) / len(lat)
        var = sum((x - mean) ** 2 for x in lat) / len(lat)
        std = var ** 0.5
        p95 = sorted(lat)[int(len(lat) * 0.95)]
        err = sum(1 for e in self._window if not e["success"]) / len(self._window)
        latest = self._window[-1]
        latency_anomaly = std > 1e-6 and (latest["latency_ms"] - mean) / std > self.anomaly_z
        p95_anomaly = latest["latency_ms"] > p95 * 2 and latest["latency_ms"] > mean + 2 * std
        error_anomaly = err > self.error_rate_threshold and not latest["success"]
        rate_anomaly = len(self._timestamps) > self.max_calls_per_hour
        is_anomaly = latency_anomaly or p95_anomaly or error_anomaly or rate_anomaly
        if is_anomaly and not self._alerted:
            self._alerted = True
            snap = self._snapshot(alert=True)
            self._route(redact(f"Watchdog anomaly: {snap}"), snap)
            return True
        if not is_anomaly:
            self._alerted = False
        return False

    def get_status(self) -> dict:
        snap = self._snapshot(alert=False)
        if len(self._window) >= 20:
            snap["alert"] = self.should_alert()
        return snap

    def _snapshot(self, alert: bool = False) -> dict:
        if not self._window:
            return {"window": 0, "p95_ms": 0, "error_rate": 0, "calls_per_hour": len(self._timestamps), "alert": alert}
        lat = sorted(e["latency_ms"] for e in self._window)
        p95 = lat[int(len(lat) * 0.95)]
        mean = sum(lat) / len(lat)
        err = sum(1 for e in self._window if not e["success"]) / len(self._window)
        by_ep: dict[str, dict] = defaultdict(lambda: {"ok": 0, "fail": 0})
        for e in self._window:
            g = by_ep[e["endpoint"]]
            g["ok" if e["success"] else "fail"] += 1
        ep_rates = {k: round(v["ok"] / (v["ok"] + v["fail"]), 3) for k, v in by_ep.items()}
        return {"window": len(self._window), "p95_ms": round(float(p95), 2), "mean_ms": round(float(mean), 2), "error_rate": round(float(err), 3), "endpoint_success_rate": ep_rates, "calls_per_hour": len(self._timestamps), "cache_size": len(self._cache), "alert": alert}

    def _route(self, msg: str, ctx: dict) -> None:
        if self.callback:
            try:
                self.callback(msg, ctx)
            except Exception as exc:
                logger.warning("watchdog callback failed: %s", exc)
        else:
            logger.warning("%s", redact(msg))
