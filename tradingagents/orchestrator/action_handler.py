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
import json

from tradingagents.persistence import store
from tradingagents.secretary.refinement import classify_and_extract
from tradingagents.secretary.service import RefinementDepthExceeded


log = logging.getLogger(__name__)


class _BriefScopedGraphRunner:
    def run(self, **_: Any) -> tuple[str, str]:
        raise RuntimeError("brief-scoped backtests reuse existing runs")


def _brief_run_ids(brief: dict | None) -> list[str]:
    if not brief:
        return []
    run_ids = brief.get("run_ids")
    if isinstance(run_ids, str):
        try:
            return list(json.loads(run_ids))
        except json.JSONDecodeError:
            return []
    if isinstance(run_ids, list):
        return run_ids
    return []


def _backtestable_full_brief(brief: dict | None) -> bool:
    return bool(
        brief
        and brief.get("mode") == "event_alert"
        and _brief_run_ids(brief)
    )


def dispatch_backtest_from_brief(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    params: dict,
    config: dict | None = None,
    graph_runner: Any | None = None,
    price_chain: Any | None = None,
) -> int:
    """Run the restored F2 brief-scoped harness for a full study brief."""
    brief = store.load_brief(conn, brief_id)
    if not _backtestable_full_brief(brief):
        raise ValueError(
            "run_backtest requires a full event_alert brief with persisted runs"
        )

    if config is None:
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG
    if price_chain is None:
        from tradingagents.backtest.prices import PriceFallbackChain
        from tradingagents.backtest.sources.yfinance_source import YFinanceSource

        price_chain = PriceFallbackChain([YFinanceSource()])

    from tradingagents.backtest.harness import BacktestHarness
    from tradingagents.backtest.prices import Resolution

    backtest_config = config.get("backtest", {})
    resolution = Resolution(params.get("resolution", backtest_config.get("resolution", "1d")))
    window_days = int(params.get("window_days", backtest_config.get("window_days", 30)))
    benchmark = params.get("benchmark", backtest_config.get("benchmark", "SPY"))
    harness = BacktestHarness(
        conn=conn,
        data_dir=config["iic_data_dir"],
        graph_runner=graph_runner or _BriefScopedGraphRunner(),
        price_chain=price_chain,
        resolution=resolution,
        benchmark=benchmark,
    )
    return harness.run_brief_scoped(brief_id=brief_id, window_days=window_days)


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
    params = row["action_params"]
    if isinstance(params, str):
        params = json.loads(params)

    if row["action_type"] == "run_backtest":
        if not _backtestable_full_brief(store.load_brief(conn, row["brief_id"])):
            store.mark_action_error(
                conn,
                action_id=row["action_id"],
                error="run_backtest requires a full event_alert brief with persisted runs",
            )
            return
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
        from datetime import datetime, timezone

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
            store.mark_action_error(
                conn,
                action_id=row["action_id"],
                error=(
                    f"missing event_id/ticker event_id={event_id!r} "
                    f"ticker={ticker!r}"
                ),
            )
            return
        with conn:
            cur = conn.execute(
                "INSERT INTO queue_jobs (job_type, payload, state, "
                "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', "
                "datetime('now'), ?)",
                ("event_alert",
                 json.dumps({
                     "event_id": event_id,
                     "ticker": ticker,
                     "action_id": row["action_id"],
                     "parent_brief_id": row["brief_id"],
                 }),
                 event_id),
            )
            job_id = cur.lastrowid
        store.mark_action_dispatched(
            conn,
            action_id=row["action_id"],
            result_job_id=job_id,
            dispatched_ts=datetime.now(timezone.utc).isoformat(),
        )
    else:
        log.warning("action_handler: unknown action_type %r", row["action_type"])
