"""Append-only JSONL store of agent decisions produced by a backtest.

This is the artifact boundary between the expensive half of a backtest and the
cheap half. The runner appends one record per decision point; everything
downstream (portfolio simulation, metrics, baselines, the scorecard) reads the
store back. Re-scoring a finished backtest under a different weight map or cost
model therefore costs nothing — no LLM calls, no network.

Two properties make the store safe to build a resumable runner on:

* **Append-only.** A record is written with a single ``write()`` of one line
  terminated by ``\\n``. A crash mid-run can leave a torn final line but cannot
  corrupt earlier records, and :meth:`DecisionStore.records` skips unparseable
  lines rather than failing the whole run.
* **Keyed by run signature.** Each record carries the graph-shape signature it
  was produced under (analyst selection, debate/risk depth, models). Changing
  the config starts a fresh set of keys instead of silently mixing two
  experiments into one equity curve.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Bumped when the record layout changes incompatibly. Records written under a
# different version are ignored by ``records()`` rather than silently mixed in.
SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class DecisionRecord:
    """One agent decision at one point in time, plus what it cost to produce.

    ``rating`` is a 5-tier rating, the ``REVIEW`` sentinel (#1170), or ``None``
    when the run raised — in which case ``error`` holds the message. Failed
    records are kept deliberately: they are visible in the scorecard as coverage
    gaps, and they do not block a later resume from retrying that date.

    ``cost_usd`` is ``None`` when the model has no entry in the price table, so
    an unpriced model reports token counts without inventing a dollar figure.
    """

    ticker: str
    date: str
    signature: str
    rating: str | None = None
    decision: str = ""
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None
    wall_seconds: float = 0.0
    error: str | None = None
    schema_version: int = SCHEMA_VERSION
    created_at: str = field(default_factory=_utc_now)

    @property
    def ok(self) -> bool:
        """Whether this record carries a usable decision."""
        return self.error is None and self.rating is not None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.ticker, self.date, self.signature)


class DecisionStore:
    """Append-only JSONL file of :class:`DecisionRecord`, with an in-memory index.

    The index holds only the keys of *successful* records. A decision point that
    previously failed is therefore not considered present, so resuming a
    backtest retries it instead of leaving a permanent hole. A date that fails
    every time keeps failing visibly rather than silently disappearing.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Serialises appends: the runner writes from one thread per ticker, and
        # interleaved partial writes would corrupt the line-per-record layout
        # that makes the store recoverable.
        self._write_lock = threading.Lock()
        self._succeeded: set[tuple[str, str, str]] = {
            r.key for r in self.records() if r.ok
        }

    @property
    def path(self) -> Path:
        return self._path

    def has(self, ticker: str, date: str, signature: str) -> bool:
        """Whether a successful decision already exists for this point."""
        return (ticker, date, signature) in self._succeeded

    def append(self, record: DecisionRecord) -> None:
        """Append one record, updating the success index."""
        line = json.dumps(asdict(record), ensure_ascii=False)
        with self._write_lock:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            if record.ok:
                self._succeeded.add(record.key)

    def records(self, signature: str | None = None) -> list[DecisionRecord]:
        """Load records, optionally filtered to one run signature.

        Unparseable lines (a torn final write from a crashed run) and records
        from a different schema version are skipped with a warning, so an
        interrupted backtest stays resumable instead of unreadable.
        """
        if not self._path.exists():
            return []

        out: list[DecisionRecord] = []
        with open(self._path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping unparseable decision record at %s:%d "
                        "(likely a torn write from an interrupted run)",
                        self._path, lineno,
                    )
                    continue
                if payload.get("schema_version") != SCHEMA_VERSION:
                    logger.warning(
                        "Skipping decision record at %s:%d written under schema "
                        "version %r (this build expects %d)",
                        self._path, lineno, payload.get("schema_version"), SCHEMA_VERSION,
                    )
                    continue
                try:
                    out.append(DecisionRecord(**payload))
                except TypeError:
                    logger.warning(
                        "Skipping decision record at %s:%d with unexpected fields",
                        self._path, lineno,
                    )
                    continue

        if signature is not None:
            out = [r for r in out if r.signature == signature]
        return out

    def decisions(self, signature: str | None = None) -> list[DecisionRecord]:
        """Successful records only, sorted by (ticker, date).

        This is what the portfolio simulator consumes. Sorting here means the
        simulator can assume chronological order regardless of the order the
        runner happened to produce records in (tickers run concurrently).
        """
        usable = [r for r in self.records(signature) if r.ok]
        return sorted(usable, key=lambda r: (r.ticker, r.date))

    def failures(self, signature: str | None = None) -> list[DecisionRecord]:
        """Records that raised, for the scorecard's coverage section."""
        return [r for r in self.records(signature) if not r.ok]

    def tickers(self, signature: str | None = None) -> list[str]:
        return sorted({r.ticker for r in self.decisions(signature)})
