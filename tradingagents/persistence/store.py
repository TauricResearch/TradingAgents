"""Insert/query helpers over the SQLite store.

Each function takes an open ``sqlite3.Connection`` and commits before returning.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional


# --------------------------------------------------------------------
# runs
# --------------------------------------------------------------------

def insert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    persona_id: Optional[str],
    started_ts: str,
    artifact_dir: str,
    trigger_id: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO runs (run_id, ticker, persona_id, started_ts, status, "
        "trigger_id, artifact_dir) VALUES (?, ?, ?, ?, 'running', ?, ?)",
        (run_id, ticker, persona_id, started_ts, trigger_id, artifact_dir),
    )
    conn.commit()


def finalize_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ended_ts: str,
    status: str,
    decision: Optional[str] = None,
    confidence: Optional[float] = None,
) -> None:
    conn.execute(
        "UPDATE runs SET ended_ts = ?, status = ?, decision = ?, confidence = ? "
        "WHERE run_id = ?",
        (ended_ts, status, decision, confidence, run_id),
    )
    conn.commit()


# --------------------------------------------------------------------
# costs
# --------------------------------------------------------------------

def record_cost(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    provider: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
    usd_estimate: Optional[float] = None,
) -> None:
    conn.execute(
        "INSERT INTO costs (run_id, provider, model, in_tokens, out_tokens, "
        "usd_estimate) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, provider, model, in_tokens, out_tokens, usd_estimate),
    )
    conn.commit()
