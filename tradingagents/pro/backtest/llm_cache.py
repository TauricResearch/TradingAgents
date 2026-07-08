"""CachingLLM: deterministic record/replay for pipeline LLM calls.

Backtests run the *same* pipeline as live, but 60+ LLM calls per decision
across hundreds of decisions is real money. This wrapper caches structured
responses keyed by (schema, sha256(prompt)) with optional JSONL
persistence.

Modes:
- "auto":   cache hit or call-and-store (default; incremental runs)
- "record": always call the inner LLM and store (refresh a cache)
- "replay": cache-only; a miss raises — a "backtest" silently mixing fresh
            LLM output with replayed output is not reproducible

Fidelity tradeoff (ADR-0023): a cache hit requires a byte-identical prompt,
so any change to prompts, roster, data rendering, or the snapshot content
produces misses. Replayed runs are exactly reproducible; they measure the
pipeline as it was recorded and cannot react to novel wording.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CacheMiss(KeyError):
    pass


class _CachingRunnable:
    def __init__(self, cache: CachingLLM, schema, inner_runnable):
        self._cache = cache
        self._schema = schema
        self._inner = inner_runnable

    def invoke(self, prompt: str):
        return self._cache._invoke(self._schema, self._inner, prompt)


class CachingLLM:
    def __init__(self, inner=None, mode: str = "auto", path: str | Path | None = None):
        if mode not in ("auto", "record", "replay"):
            raise ValueError(f"mode must be auto|record|replay, got {mode!r}")
        if mode != "replay" and inner is None:
            raise ValueError("auto/record modes need an inner llm")
        self.inner = inner
        self.mode = mode
        self.path = Path(path) if path else None
        self.hits = 0
        self.misses = 0
        self._store: dict[str, dict] = {}
        if self.path and self.path.exists():
            with self.path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._store[entry["key"]] = entry

    @staticmethod
    def _key(schema, prompt: str) -> str:
        digest = hashlib.sha256(f"{schema.__name__}\x00{prompt}".encode()).hexdigest()
        return f"{schema.__name__}:{digest}"

    def with_structured_output(self, schema):
        inner_runnable = (
            self.inner.with_structured_output(schema) if self.inner is not None else None
        )
        return _CachingRunnable(self, schema, inner_runnable)

    def _invoke(self, schema, inner_runnable, prompt: str):
        key = self._key(schema, prompt)
        if self.mode != "record" and key in self._store:
            self.hits += 1
            return schema.model_validate(self._store[key]["payload"])
        if self.mode == "replay":
            raise CacheMiss(
                f"replay cache miss for {schema.__name__}; prompts have drifted "
                "from the recorded run (see ADR-0023)"
            )
        self.misses += 1
        result = inner_runnable.invoke(prompt)
        if result is not None:
            entry = {
                "key": key,
                "schema": schema.__name__,
                "payload": result.model_dump(mode="json"),
            }
            self._store[key] = entry
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry) + "\n")
        return result
