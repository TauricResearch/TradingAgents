"""Flat JSONL audit log for TradingAgents runs.

Distinct from ``TradingMemoryLog`` (in ``memory.py``), which keeps an
append-only markdown log of decisions and computes realized return /
reflection on the next same-ticker run. The audit log is a separate,
simpler sink: one JSON object per confirmed run, on its own line, written
to a single flat file so cross-ticker review with ``jq`` is trivial.

Every confirmed run — CLI or programmatic, initial or re-check — appends
one record. Practice / dry runs are filtered out upstream (see the CLI's
"persist this run?" confirmation), so the audit log only contains runs
the user explicitly chose to keep.

The Step 3 re-check workflow reads from this log to retrieve the most
recent ``initial`` entry for a ticker, so the Portfolio Manager can be
shown the original thesis as context.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    """Append-only JSONL audit log of confirmed runs.

    File format: each line is a self-contained JSON object. Append is the
    only write op, so concurrent CLI runs in different terminals will not
    corrupt each other (POSIX guarantees atomic small appends).
    """

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        self._path: Path | None = None
        raw = cfg.get("audit_log_path")
        if raw:
            self._path = Path(raw).expanduser()
            self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path | None:
        """Resolved path, or ``None`` when the log is disabled."""
        return self._path

    def append(
        self,
        *,
        ticker: str,
        trade_date: str,
        run_purpose: str,
        position_size_gbp: float | None,
        llm_provider: str | None,
        deep_think_llm: str | None,
        quick_think_llm: str | None,
        decision_payload: dict[str, Any],
    ) -> None:
        """Append one record. No-ops when the log is disabled.

        ``decision_payload`` is the full per-run state dict the existing
        ``_log_state`` writer builds — investment_plan, trader_investment_plan,
        final_trade_decision, all four analyst reports, and both debate
        histories. Storing the whole thing makes Step 3's re-check workflow
        cheap (no separate state-log lookup) and keeps every confirmed run
        self-contained for later jq-style review.
        """
        if self._path is None:
            return
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "trade_date": str(trade_date),
            "run_purpose": run_purpose,
            "position_size_gbp": position_size_gbp,
            "llm_provider": llm_provider,
            "deep_think_llm": deep_think_llm,
            "quick_think_llm": quick_think_llm,
            "decision": decision_payload,
        }
        # Append in one write so a concurrent reader cannot see a torn line.
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)

    def load_all(self) -> list[dict[str, Any]]:
        """Read every record. Malformed lines are skipped silently.

        Returned in file order (oldest first). Cheap for the sizes this log
        is expected to reach (one record per analysis run); reach for a
        streaming reader only if/when the file grows past a few MB.
        """
        if self._path is None or not self._path.exists():
            return []
        out: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    # Don't let a corrupted line break re-check retrieval.
                    continue
        return out

    def latest_initial_for_ticker(self, ticker: str) -> dict[str, Any] | None:
        """Return the most recent ``run_purpose=='initial'`` record for ``ticker``.

        Used by the re-check workflow (Step 3) to fetch the original
        investment_plan / investment_thesis so the Portfolio Manager can
        evaluate whether the original reasoning still holds.
        """
        match: dict[str, Any] | None = None
        for record in self.load_all():
            if record.get("ticker") != ticker:
                continue
            if record.get("run_purpose") != "initial":
                continue
            # File order is chronological; keep overwriting to land on the latest.
            match = record
        return match
