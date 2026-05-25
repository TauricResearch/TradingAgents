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


# --------------------------------------------------------------------
# briefs
# --------------------------------------------------------------------

def insert_brief(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    mode: str,
    scope: str,
    generated_ts: str,
    content_path: str,
    run_ids: Iterable[str],
    parent_brief_id: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO briefs (brief_id, mode, scope, generated_ts, content_path, "
        "run_ids, parent_brief_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (brief_id, mode, scope, generated_ts, content_path,
         json.dumps(list(run_ids)), parent_brief_id),
    )
    conn.commit()


# --------------------------------------------------------------------
# brief_actions
# --------------------------------------------------------------------

def insert_brief_action(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    action_type: str,
    action_params: dict,
    expires_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO brief_actions (brief_id, action_type, action_params, "
        "state, expires_at) VALUES (?, ?, ?, 'pending', ?)",
        (brief_id, action_type, json.dumps(action_params), expires_at),
    )
    conn.commit()
    return cur.lastrowid
