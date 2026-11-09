"""Metric registry (§9): the run's ledger of verified and refused figures.

Before a number may influence the Research Manager, the Trader or the
Portfolio Manager it must be confrontable with something authoritative. That
"something" is this registry: every metric the engine computed during a run,
keyed by name, carrying its ``MetricRecord``.

Two behaviours make it useful rather than decorative:

**Refusals are kept.** A P/B of 1.35x that contradicts 570.89/385.70 stays in
the registry as a ``MISMATCH`` record. The final report can then show the
rejected claim next to the computed value instead of dropping it, and the
audit can prove the system noticed.

**Silence is not verification.** Looking up a metric the engine never
computed returns ``None``. A claim about it is unverifiable, which blocks —
the fail-closed default. A registry that answered "no record, so probably
fine" would be worse than having none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tradingagents.dataflows.math.metric_record import MetricRecord


@dataclass
class MetricRegistry:
    """Every metric computed in one run, with its audit record."""

    run_id: str = ""
    _records: dict[str, MetricRecord] = field(default_factory=dict)

    def register(self, record: MetricRecord) -> MetricRecord:
        """Store a metric, keeping a refusal rather than discarding it.

        A later ``VERIFIED`` record replaces an earlier refusal for the same
        metric: recomputing with better inputs is legitimate progress, and
        the newest computation is the one that describes the run. The
        reverse — a new refusal replacing a verification — also wins, because
        the last thing the engine knows is what it stands behind.
        """
        self._records[record.metric] = record
        return record

    def register_all(self, records: list[MetricRecord]) -> None:
        for record in records:
            self.register(record)

    def get(self, name: str) -> MetricRecord | None:
        """The record for ``name``, or ``None`` when never computed."""
        return self._records.get(name)

    def value(self, name: str) -> Any:
        """The verified value for ``name``, or ``None``.

        Returns ``None`` for a metric that exists but was refused: a caller
        cannot accidentally act on a contradicted figure by reading it here.
        """
        record = self._records.get(name)
        if record is None or not record.is_usable:
            return None
        return record.value

    @property
    def usable(self) -> list[MetricRecord]:
        return [r for r in self._records.values() if r.is_usable]

    @property
    def blocking(self) -> list[MetricRecord]:
        return [r for r in self._records.values() if r.blocks_decision]

    @property
    def blocks_decision(self) -> bool:
        return bool(self.blocking)

    def verification_map(self) -> dict[str, Any]:
        """Metric name -> verified value, for the claims checker.

        Only usable metrics appear. A claim about a refused metric therefore
        finds nothing to match and is reported unverifiable instead of being
        checked against a number the engine already rejected.
        """
        return {name: record.value for name, record
                in self._records.items() if record.is_usable}

    def summary(self) -> dict:
        """The §13 audit shape: every metric, plus the run's verdict."""
        return {
            "run_id": self.run_id,
            "metrics": [r.summary() for r in self._records.values()],
            "blocking_metrics": [r.metric for r in self.blocking],
            "status": "BLOCKED" if self.blocks_decision else (
                "OK" if self._records else None),
        }
