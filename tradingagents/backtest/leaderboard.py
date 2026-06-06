"""Read-only leaderboard over backtest_runs.

Open rows: lazy MTM (fetch latest price via price_chain — never written back).
Closed rows: serve metrics straight from the frozen JSON.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import List, Optional

from tradingagents.backtest.prices import Resolution


def build_leaderboard(
    conn: sqlite3.Connection,
    *,
    price_chain: Optional[object] = None,
    persona: Optional[str] = None,
    status_filter: Optional[str] = None,   # "open" | "closed" | None=all
) -> List[dict]:
    """Return per-row leaderboard entries grouped by status.

    Args:
        conn: open SQLite connection.
        price_chain: optional ``get_bars()`` producer for live MTM on open rows.
            When None, open rows report ``mtm_return=None``.
        persona: optional filter by persona_id.
        status_filter: optional restriction by metrics.status.
    """
    sql = "SELECT btr_id, backtest_id, persona_id, ticker, metrics FROM backtest_runs"
    args: list = []
    where: list = []
    if persona is not None:
        where.append("persona_id = ?")
        args.append(persona)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY btr_id ASC"

    rows: List[dict] = []
    for db_row in conn.execute(sql, args):
        m = json.loads(db_row["metrics"])
        status = m.get("status", "unknown")
        if status_filter and status != status_filter:
            continue
        entry = {
            "btr_id": db_row["btr_id"],
            "backtest_id": db_row["backtest_id"],
            "persona_id": db_row["persona_id"],
            "ticker": db_row["ticker"],
            "status": status,
            "decision": m.get("decision"),
            "position": m.get("position"),
            "entry_date": m.get("entry_date"),
            "entry_price": m.get("entry_price"),
            "scheduled_close_date": m.get("scheduled_close_date"),
        }
        if status == "closed":
            entry.update({
                "close_date": m.get("close_date"),
                "exit_price": m.get("exit_price"),
                "total_return": m.get("total_return"),
                "alpha": m.get("alpha"),
                "sharpe": m.get("sharpe"),
                "max_drawdown": m.get("max_drawdown"),
                "win_rate": m.get("win_rate"),
            })
        elif status == "open":
            if price_chain is not None and m.get("entry_price"):
                entry.update(_lazy_mtm(price_chain, db_row["ticker"], m))
            else:
                entry["current_price"] = None
                entry["mtm_return"] = None
                entry["mtm_alpha"] = None
        else:   # errored or unknown
            entry["error"] = m.get("error")
        rows.append(entry)
    return rows


def _lazy_mtm(price_chain, ticker: str, m: dict) -> dict:
    """Best-effort live MTM for one open row. Errors → all-None values."""
    try:
        bars = price_chain.get_bars(
            ticker, date.today(), date.today(),
            Resolution(m.get("resolution", "1d")),
        )
        current_price = bars.bars[-1][1] if bars.bars else None
    except Exception:
        current_price = None
    if current_price is None or m["entry_price"] <= 0:
        return {"current_price": None, "mtm_return": None, "mtm_alpha": None}

    position = m.get("position", 0)
    mtm_return = position * (current_price - m["entry_price"]) / m["entry_price"]

    mtm_alpha = None
    bench_entry = m.get("benchmark_entry_price")
    if bench_entry:
        try:
            bench_bars = price_chain.get_bars(
                m.get("benchmark", "SPY"), date.today(), date.today(),
                Resolution(m.get("resolution", "1d")),
            )
            bench_now = bench_bars.bars[-1][1] if bench_bars.bars else None
        except Exception:
            bench_now = None
        if bench_now and bench_entry > 0:
            mtm_alpha = mtm_return - (bench_now - bench_entry) / bench_entry

    return {
        "current_price": current_price,
        "mtm_return": mtm_return,
        "mtm_alpha": mtm_alpha,
    }
