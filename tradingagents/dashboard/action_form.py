"""Action form — the one mutation surface in an otherwise read-only dashboard.

Two operations:
  - submit_backtest(brief_id) → run_backtest action, accepted
  - submit_refinement(brief_id, reply_text) → refine_brief action, accepted

The Streamlit page rendered for `?brief_id=…` calls these on form POST.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from tradingagents.persistence import store


def _expires(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def submit_backtest(*, conn: sqlite3.Connection, brief_id: str, config: dict) -> int:
    aid = store.insert_brief_action(
        conn, brief_id=brief_id, action_type="run_backtest",
        action_params={}, expires_at=_expires(config["refinement"]["action_expires_hours"]),
    )
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at=_now())
    return aid


def submit_refinement(
    *, conn: sqlite3.Connection, brief_id: str, reply_text: str, config: dict,
) -> int:
    text = (reply_text or "").strip()
    if not text:
        raise ValueError("refinement reply_text is empty")
    aid = store.insert_brief_action(
        conn, brief_id=brief_id, action_type="refine_brief",
        action_params={"reply_text": text},
        expires_at=_expires(config["refinement"]["action_expires_hours"]),
    )
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at=_now())
    return aid
