"""Stateless maturation pass — the engine behind ``forge backtest sweep``
and ``forge backtest watch``.

Queries open backtest_runs whose scheduled_close_date <= today, runs the
maturation logic inline using the BacktestHarness for each backtest_id,
returns counts. Errored rows are left alone by default to avoid retry
storms.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Dict

from tradingagents.backtest.harness import BacktestHarness


def run_maturation_pass(
    conn: sqlite3.Connection,
    *,
    price_chain: object,
    data_dir: str = "",
    today: date | None = None,
) -> Dict[str, int]:
    """Mature every open backtest_runs row whose scheduled_close_date <= today.

    Returns a counter dict with keys ``closed``, ``skipped``, ``errored``.
    """
    if today is None:
        today = date.today()

    closed = 0
    skipped = 0
    errored = 0

    # Group by backtest_id so we can reuse one harness per backtest.
    bt_ids = [
        row["backtest_id"] for row in conn.execute(
            "SELECT DISTINCT backtest_id FROM backtest_runs ORDER BY backtest_id"
        )
    ]

    for backtest_id in bt_ids:
        rows = list(conn.execute(
            "SELECT btr_id, persona_id, ticker, metrics FROM backtest_runs "
            "WHERE backtest_id = ?",
            (backtest_id,),
        ))
        per_bt_due: list = []
        for r in rows:
            m = json.loads(r["metrics"])
            status = m.get("status")
            if status == "errored":
                continue  # don't retry by default
            if status != "open":
                continue
            sched = m.get("scheduled_close_date")
            if not sched or date.fromisoformat(sched) > today:
                skipped += 1
                continue
            per_bt_due.append((r, m))

        if not per_bt_due:
            continue

        # Build a harness against this conn/chain; reuse for all rows in this backtest.
        # graph_runner is unused during maturation (no fresh graph calls).
        harness = BacktestHarness(
            conn=conn, data_dir=data_dir,
            graph_runner=_NullGraphRunner(),
            price_chain=price_chain,
        )
        end_date = max(
            date.fromisoformat(m["scheduled_close_date"]) for (_, m) in per_bt_due
        )
        try:
            harness._mature_all_open(backtest_id=backtest_id, end_date=end_date)
        except Exception:
            errored += len(per_bt_due)
            continue
        # Re-read to count closed vs errored after the pass
        rows_after = list(conn.execute(
            "SELECT metrics FROM backtest_runs WHERE backtest_id = ?",
            (backtest_id,),
        ))
        for r in rows_after:
            m = json.loads(r["metrics"])
            # Only count rows that were due in this pass
            sched = m.get("scheduled_close_date")
            if not sched or date.fromisoformat(sched) > today:
                continue
            if m.get("status") == "closed":
                closed += 1
            elif m.get("status") == "errored" and m.get("close_date") is None:
                # Was already errored before this pass — skip counting
                pass

        # If the whole backtest's runs are now closed, update parent status.
        any_open = any(
            json.loads(r["metrics"]).get("status") == "open"
            for r in rows_after
        )
        if not any_open:
            conn.execute(
                "UPDATE backtests SET status='closed' WHERE backtest_id=?",
                (backtest_id,),
            )
            conn.commit()

    return {"closed": closed, "skipped": skipped, "errored": errored}


class _NullGraphRunner:
    """A graph runner that must never be invoked (maturation doesn't run the graph)."""
    def run(self, **kwargs):
        raise RuntimeError(
            "_NullGraphRunner.run() called — maturation must not invoke the graph"
        )
