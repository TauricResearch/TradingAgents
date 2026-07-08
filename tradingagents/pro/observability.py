"""Observability: structured logs, metrics, and LLM cost tracking.

Dependency-free by design: JSON logs via stdlib logging, a small metrics
registry with Prometheus text exposition (scrapeable without
prometheus_client), and a cost tracker that wraps the Pro LLM interface.

Token counts are *estimates* (chars/4) because the structured-output
interface does not expose provider usage metadata; treat the cost figure
as a budget gauge, not an invoice. Wiring provider-reported usage is a
straightforward upgrade once a single provider is pinned in production.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field

from tradingagents.contracts import utc_now


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            entry.update(extra)
        return json.dumps(entry, default=str)


def configure_structured_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class MetricsRegistry:
    """Counters and gauges with Prometheus text exposition."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        rendered = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{rendered}}}"

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = value

    def counter(self, name: str, **labels: str) -> float:
        return self._counters.get(self._key(name, labels), 0.0)

    def gauge(self, name: str, **labels: str) -> float:
        return self._gauges.get(self._key(name, labels), 0.0)

    def render_prometheus(self) -> str:
        lines = []
        with self._lock:
            for key, value in sorted(self._counters.items()):
                lines.append(f"{key} {value}")
            for key, value in sorted(self._gauges.items()):
                lines.append(f"{key} {value}")
        return "\n".join(lines) + "\n"


@dataclass
class ModelPrice:
    input_per_mtok: float = 3.0  # USD per million tokens; override per deployment
    output_per_mtok: float = 15.0


@dataclass
class CostReport:
    calls: int = 0
    est_input_tokens: int = 0
    est_output_tokens: int = 0
    est_cost_usd: float = 0.0
    by_schema: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "est_input_tokens": self.est_input_tokens,
            "est_output_tokens": self.est_output_tokens,
            "est_cost_usd": round(self.est_cost_usd, 4),
            "by_schema": dict(self.by_schema),
        }


class _TrackedRunnable:
    def __init__(self, tracker: CostTrackingLLM, schema, inner):
        self._tracker = tracker
        self._schema = schema
        self._inner = inner

    def invoke(self, prompt: str):
        result = self._inner.invoke(prompt)
        self._tracker._record(self._schema.__name__, prompt, result)
        return result


class CostTrackingLLM:
    """Transparent wrapper over the Pro LLM interface; stacks under/over
    CachingLLM freely (both speak with_structured_output)."""

    def __init__(self, inner, price: ModelPrice | None = None,
                 metrics: MetricsRegistry | None = None):
        self.inner = inner
        self.price = price or ModelPrice()
        self.metrics = metrics
        self.report = CostReport()
        self._lock = threading.Lock()

    def with_structured_output(self, schema):
        return _TrackedRunnable(self, schema, self.inner.with_structured_output(schema))

    def _record(self, schema_name: str, prompt: str, result) -> None:
        input_tokens = max(1, len(prompt) // 4)
        output_chars = len(result.model_dump_json()) if result is not None else 0
        output_tokens = max(0, output_chars // 4)
        cost = (
            input_tokens * self.price.input_per_mtok
            + output_tokens * self.price.output_per_mtok
        ) / 1_000_000
        with self._lock:
            self.report.calls += 1
            self.report.est_input_tokens += input_tokens
            self.report.est_output_tokens += output_tokens
            self.report.est_cost_usd += cost
            self.report.by_schema[schema_name] = (
                self.report.by_schema.get(schema_name, 0) + 1
            )
        if self.metrics is not None:
            self.metrics.inc("llm_calls_total", schema=schema_name)
            self.metrics.set_gauge("llm_est_cost_usd", self.report.est_cost_usd)
