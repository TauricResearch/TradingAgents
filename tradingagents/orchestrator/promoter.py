"""F4 promoter — polls events for trigger candidates and enqueues jobs.

Runs as `iic-promoter.service`. Defensive retry-internal: never raises out
of the main loop except on truly unrecoverable errors.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from tradingagents.persistence import store
from tradingagents.persistence.db import connect
from tradingagents.orchestrator.candidates import fetch_candidates, fetch_candidates_grouped
from tradingagents.orchestrator.guards import QueueBackpressure, QueueRateGuard


log = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def run_once(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    batch_size: int,
    cooldown_min: int,
    backpressure: Optional[QueueBackpressure] = None,
    rate_guard: Optional[QueueRateGuard] = None,
    secretary=None,
    approval_gate_enabled: bool = False,
    pending_ttl_hours: int = 24,
) -> int:
    """Perform one poll cycle. With the approval gate enabled, composes one
    light alert per event (no study enqueued). Returns the count of light
    alerts (gate) or jobs (legacy) created."""
    if backpressure is not None and not backpressure.gate(conn):
        return 0
    if rate_guard is not None and not rate_guard.gate(conn):
        return 0

    if approval_gate_enabled:
        if secretary is None:
            raise ValueError("run_once: approval_gate_enabled requires a secretary")
        groups = fetch_candidates_grouped(
            conn, salience_threshold=salience_threshold,
            ticker_conf_threshold=ticker_conf_threshold, limit=batch_size,
        )
        # Intra-batch dedup: the candidate query reflects the suppression table
        # as it was when the fetch ran, but each compose writes new same-day
        # suppressions mid-loop that the already-fetched batch can't see. Without
        # an in-pass guard, several events naming the same ticker in one batch
        # each spawn a light alert before suppression takes hold (cross-cycle
        # dedup works; intra-batch did not). Track tickers alerted THIS pass and
        # strip them from later events so a ticker fires at most once per pass.
        seen_tickers: set = set()
        composed = 0
        for g in groups:
            fresh = [t for t in g["tickers"] if t not in seen_tickers]
            if not fresh:
                continue
            try:
                secretary.compose_event_alert_light(
                    event_id=g["event_id"], tickers=fresh,
                    ttl_hours=pending_ttl_hours, deliver=True,
                )
                seen_tickers.update(fresh)
                composed += 1
                log.info("light alert composed event_id=%s tickers=%s",
                         g["event_id"], fresh)
            except Exception:
                log.exception("light alert failed event_id=%s; continuing",
                              g["event_id"])
        return composed

    # ----- Legacy auto-enqueue path (approval gate disabled) -----
    candidates = fetch_candidates(
        conn,
        salience_threshold=salience_threshold,
        ticker_conf_threshold=ticker_conf_threshold,
        limit=batch_size,
    )
    if not candidates:
        return 0

    enqueued = 0
    for ev in candidates:
        until_ts = (_now_utc() + timedelta(minutes=cooldown_min)).isoformat()
        try:
            with conn:    # one atomic tx per event
                conn.execute(
                    "INSERT INTO queue_jobs (job_type, payload, state, "
                    "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', ?, ?)",
                    (
                        "event_alert",
                        json.dumps({"event_id": ev["event_id"],
                                    "ticker": ev["ticker"]}),
                        _now_utc().isoformat(),
                        ev["event_id"],
                    ),
                )
                store.upsert_suppression(
                    conn,
                    key=f"event_alert:{ev['ticker']}",
                    until_ts=until_ts,
                    reason=f"alert_cooldown event_id={ev['event_id']}",
                    created_by="promoter",
                )
            enqueued += 1
            log.info("enqueued event_alert event_id=%s ticker=%s",
                     ev["event_id"], ev["ticker"])
        except sqlite3.OperationalError:
            log.exception("db error enqueueing event_id=%s; backing off",
                          ev["event_id"])
            time.sleep(2)
    return enqueued


def main(config: Optional[dict] = None) -> None:
    """systemd entry point. Defensive: never exits except on KeyboardInterrupt."""
    from tradingagents.default_config import DEFAULT_CONFIG
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    conn = connect(cfg["iic_db_path"])
    backpressure = QueueBackpressure(
        enabled=cfg["trigger_backpressure_enabled"],
        max_pending=cfg["trigger_backpressure_max_pending"],
    )
    rate_guard = QueueRateGuard(
        enabled=cfg["trigger_daily_rate_enabled"],
        max_per_day=cfg["trigger_daily_rate_max_jobs"],
    )

    gate_enabled = cfg["alert_approval_gate_enabled"]
    secretary = None
    if gate_enabled:
        from tradingagents.llm_clients.factory import create_llm_client
        from tradingagents.secretary.service import Secretary
        llm = create_llm_client(
            provider=cfg["llm_provider"], model=cfg["quick_think_llm"],
            base_url=cfg.get("backend_url"),
        ).get_llm()
        secretary = Secretary(conn=conn, data_dir=cfg["iic_data_dir"], llm=llm)

    log.info("promoter starting: poll=%ss cooldown=%sm guards: bp=%s rate=%s",
             cfg["promoter_poll_interval_s"], cfg["alert_cooldown_min"],
             backpressure.enabled, rate_guard.enabled)

    while True:
        try:
            run_once(
                conn,
                salience_threshold=cfg["alert_salience_threshold"],
                ticker_conf_threshold=cfg["alert_ticker_confidence_threshold"],
                batch_size=cfg["promoter_batch_size"],
                cooldown_min=cfg["alert_cooldown_min"],
                backpressure=backpressure,
                rate_guard=rate_guard,
                secretary=secretary,
                approval_gate_enabled=gate_enabled,
                pending_ttl_hours=cfg["alert_pending_ttl_hours"],
            )
        except KeyboardInterrupt:
            log.info("promoter shutting down on KeyboardInterrupt")
            raise
        except Exception:
            log.exception("promoter loop failure; sleeping 5s and continuing")
            time.sleep(5)
        time.sleep(cfg["promoter_poll_interval_s"])


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
