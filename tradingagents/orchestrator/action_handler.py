"""Action handler — single consumer of brief_actions.

One tick:
  1. Sweep: pending rows past expires_at → expired
  2. Dispatch: accepted rows without a result yet
     - run_backtest → dispatch_backtest(brief_id, params) → returns backtest_id
     - refine_brief → classify_and_extract + secretary.compose_refinement
                    → returns new brief_id

The handler holds no in-memory state; idempotent by construction.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Callable

from tradingagents.persistence import store
from tradingagents.secretary.refinement import classify_and_extract
from tradingagents.secretary.service import RefinementDepthExceeded


log = logging.getLogger(__name__)


def tick(
    *,
    conn: sqlite3.Connection,
    secretary: Any,
    dispatch_backtest: Callable[[str, dict], int],
) -> None:
    n = store.expire_lapsed_actions(conn)
    if n:
        log.info("action_handler: expired %d lapsed actions", n)

    for row in store.fetch_accepted_undispatched(conn):
        try:
            _dispatch_one(conn, row, secretary, dispatch_backtest)
        except RefinementDepthExceeded as exc:
            log.warning("refinement depth exceeded for action %s: %s",
                        row["action_id"], exc)
        except Exception:  # noqa: BLE001
            log.exception("action_handler: dispatch failed for action %s", row["action_id"])


def _dispatch_one(
    conn: sqlite3.Connection,
    row: dict,
    secretary: Any,
    dispatch_backtest: Callable[[str, dict], int],
) -> None:
    import json as _j
    params = row["action_params"]
    if isinstance(params, str):
        params = _j.loads(params)

    if row["action_type"] == "run_backtest":
        backtest_id = dispatch_backtest(row["brief_id"], params)
        store.mark_action_done(conn, action_id=row["action_id"],
                               result_backtest_id=backtest_id)

    elif row["action_type"] == "refine_brief":
        reply_text = params.get("reply_text", "")
        parent = store.load_brief(conn, row["brief_id"])
        overrides = classify_and_extract(
            reply_text=reply_text, parent_brief=parent or {}, llm=secretary._llm,
        )
        new_brief_id = secretary.compose_refinement(
            parent_brief_id=row["brief_id"], overrides=overrides, reply_text=reply_text,
        )
        store.mark_action_done(conn, action_id=row["action_id"],
                               result_brief_id=new_brief_id)
    elif row["action_type"] == "run_full_study":
        ticker = params.get("ticker")
        light = store.load_brief(conn, row["brief_id"])
        event_id = (light or {}).get("trigger_event_id")
        if not event_id or not ticker:
            # Missing linkage (brief deleted / no trigger_event_id / no ticker):
            # do NOT enqueue a malformed job, and do NOT mark the action done —
            # leave it accepted-undispatched so the failure is visible and
            # recoverable rather than silently sunk into a guaranteed-fail job.
            log.error("run_full_study action %s missing event_id/ticker "
                      "(event_id=%r ticker=%r); skipping enqueue",
                      row["action_id"], event_id, ticker)
            return
        with conn:
            conn.execute(
                "INSERT INTO queue_jobs (job_type, payload, state, "
                "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', "
                "datetime('now'), ?)",
                ("event_alert",
                 _j.dumps({"event_id": event_id, "ticker": ticker}),
                 event_id),
            )
        # Sentinel: set result_brief_id to the PARENT light brief so this
        # accepted action is filtered out of fetch_accepted_undispatched and
        # never re-enqueues. NOTE (audit-trail caveat): unlike refine_brief —
        # where result_brief_id points at the produced CHILD brief — here it
        # points at the parent light brief (the full brief does not exist yet
        # at enqueue time). A dedicated dispatched_ts/result_job_id column would
        # be cleaner; tracked as a follow-up for F4+F5 audit work.
        store.mark_action_done(conn, action_id=row["action_id"],
                               result_brief_id=row["brief_id"])
    else:
        log.warning("action_handler: unknown action_type %r", row["action_type"])
