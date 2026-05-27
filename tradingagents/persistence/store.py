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
    queue_job_id: Optional[int] = None,
) -> None:
    conn.execute(
        "INSERT INTO runs (run_id, ticker, persona_id, started_ts, status, "
        "trigger_id, artifact_dir, queue_job_id) VALUES (?, ?, ?, ?, 'running', ?, ?, ?)",
        (run_id, ticker, persona_id, started_ts, trigger_id, artifact_dir,
         queue_job_id),
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
    trigger_event_id: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO briefs (brief_id, mode, scope, generated_ts, content_path, "
        "run_ids, parent_brief_id, trigger_event_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (brief_id, mode, scope, generated_ts, content_path,
         json.dumps(list(run_ids)), parent_brief_id, trigger_event_id),
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


# --------------------------------------------------------------------
# F3 helpers — events / event_ticker / watchlist / tickers / fingerprints
# --------------------------------------------------------------------

import json as _json
from datetime import datetime as _dt, timezone as _tz


def _now_iso() -> str:
    return _dt.now(_tz.utc).isoformat()


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    source: str,
    ingested_ts: str,
    salience: Optional[float],
    raw_path: Optional[str],
    status: str,
    deduped_of: Optional[str],
) -> None:
    conn.execute(
        "INSERT INTO events (event_id, source, ingested_ts, salience, "
        "raw_path, deduped_of, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, source, ingested_ts, salience, raw_path, deduped_of, status),
    )
    conn.commit()


def insert_event_ticker(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    ticker: str,
    confidence: Optional[float],
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_ticker (event_id, ticker, confidence) "
        "VALUES (?, ?, ?)",
        (event_id, ticker, confidence),
    )
    conn.commit()


def upsert_watchlist(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    ttl_until: Optional[str],
    tags: Iterable[str],
) -> None:
    """Insert or update a watchlist row.

    - On insert, sets ``added_ts = now()`` and ``last_briefed = now()``.
    - On update, preserves ``added_ts``; refreshes ``last_briefed`` and ``ttl_until``;
      merges tag set.
    """
    now = _now_iso()
    incoming_tags = sorted(set(tags))
    existing = conn.execute(
        "SELECT added_ts, tags FROM watchlist WHERE ticker = ?", (ticker,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO watchlist (ticker, added_ts, last_briefed, ttl_until, tags) "
            "VALUES (?, ?, ?, ?, ?)",
            (ticker, now, now, ttl_until, _json.dumps(incoming_tags)),
        )
    else:
        prior_tags = _json.loads(existing["tags"]) if existing["tags"] else []
        merged = sorted(set(prior_tags) | set(incoming_tags))
        conn.execute(
            "UPDATE watchlist SET last_briefed = ?, ttl_until = ?, tags = ? "
            "WHERE ticker = ?",
            (now, ttl_until, _json.dumps(merged), ticker),
        )
    conn.commit()


def get_active_watchlist(conn: sqlite3.Connection) -> list[str]:
    """Tickers that are either user-curated (ttl_until IS NULL) or not yet expired."""
    # datetime() normalizes ISO `T` + `+00:00` to SQLite's `YYYY-MM-DD HH:MM:SS`
    # form so same-day comparisons work (raw string compare silently fails when
    # one side has `T` and the other has a space).
    rows = conn.execute(
        "SELECT ticker FROM watchlist "
        "WHERE ttl_until IS NULL OR datetime(ttl_until) > datetime('now')"
    )
    return [r["ticker"] for r in rows]


def upsert_ticker(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    exchange: str,
    name: str,
    aliases: Iterable[str],
    active: bool,
) -> None:
    conn.execute(
        "INSERT INTO tickers (ticker, exchange, name, aliases, active, updated_ts) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(ticker) DO UPDATE SET "
        "exchange = excluded.exchange, "
        "name = excluded.name, "
        "aliases = excluded.aliases, "
        "active = excluded.active, "
        "updated_ts = excluded.updated_ts",
        (ticker, exchange, name, _json.dumps(list(aliases)),
         1 if active else 0, _now_iso()),
    )
    conn.commit()


def get_tickers_set(conn: sqlite3.Connection) -> set[str]:
    """All currently-active tickers — used by ticker validator."""
    rows = conn.execute("SELECT ticker FROM tickers WHERE active = 1")
    return {r["ticker"] for r in rows}


def insert_event_fingerprint(
    conn: sqlite3.Connection,
    *,
    fingerprint: str,
    kind: str,
    event_id: str,
    source: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_fingerprints "
        "(fingerprint, kind, event_id, source, created_ts) VALUES (?, ?, ?, ?, ?)",
        (fingerprint, kind, event_id, source, _now_iso()),
    )
    conn.commit()


def insert_event_embedding(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    vec_id: int,
) -> None:
    conn.execute(
        "INSERT INTO event_embeddings (event_id, vec_id, created_ts) "
        "VALUES (?, ?, ?)",
        (event_id, vec_id, _now_iso()),
    )
    conn.commit()


# --------------------------------------------------------------------
# F4 helpers — events lookup / suppression / briefs lookup
# --------------------------------------------------------------------

def get_event(
    conn: sqlite3.Connection, *, event_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()


def upsert_suppression(
    conn: sqlite3.Connection,
    *,
    key: str,
    until_ts: str,
    reason: Optional[str],
    created_by: str,
) -> None:
    conn.execute(
        "INSERT INTO suppression (key, until_ts, reason, created_by) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET "
        "until_ts = excluded.until_ts, "
        "reason = excluded.reason, "
        "created_by = excluded.created_by",
        (key, until_ts, reason, created_by),
    )
    conn.commit()


def get_brief(
    conn: sqlite3.Connection, *, brief_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()


# --------------------------------------------------------------------
# F5 deliveries + brief_actions helpers
# --------------------------------------------------------------------

def insert_delivery(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    channel: str,
    status: str,
    sent_ts: Optional[str],
    channel_ref: Optional[str],
    skip_reason: Optional[str],
) -> int:
    cur = conn.execute(
        "INSERT INTO deliveries (brief_id, channel, status, sent_ts, channel_ref, skip_reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (brief_id, channel, status, sent_ts, channel_ref, skip_reason),
    )
    conn.commit()
    return cur.lastrowid


def resolve_brief_id_by_channel_ref(
    conn: sqlite3.Connection, *, channel: str, channel_ref: str,
) -> Optional[str]:
    row = conn.execute(
        "SELECT brief_id FROM deliveries WHERE channel = ? AND channel_ref = ? "
        "ORDER BY delivery_id DESC LIMIT 1",
        (channel, channel_ref),
    ).fetchone()
    return row[0] if row else None


def fetch_actions(conn: sqlite3.Connection, *, state: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM brief_actions WHERE state = ? ORDER BY action_id",
        (state,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_accepted_undispatched(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM brief_actions "
        "WHERE state = 'accepted' "
        "  AND result_backtest_id IS NULL "
        "  AND result_brief_id IS NULL "
        "ORDER BY action_id"
    ).fetchall()
    return [dict(r) for r in rows]


def update_action_state(
    conn: sqlite3.Connection, *, action_id: int, state: str, responded_at: Optional[str] = None,
) -> None:
    conn.execute(
        "UPDATE brief_actions SET state = ?, responded_at = ? WHERE action_id = ?",
        (state, responded_at, action_id),
    )
    conn.commit()


def mark_action_done(
    conn: sqlite3.Connection,
    *,
    action_id: int,
    result_backtest_id: Optional[int] = None,
    result_brief_id: Optional[str] = None,
) -> None:
    conn.execute(
        "UPDATE brief_actions SET result_backtest_id = ?, result_brief_id = ? "
        "WHERE action_id = ?",
        (result_backtest_id, result_brief_id, action_id),
    )
    conn.commit()


def expire_lapsed_actions(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "UPDATE brief_actions SET state = 'expired' "
        "WHERE state = 'pending' AND expires_at < datetime('now')"
    )
    conn.commit()
    return cur.rowcount


def load_brief(conn: sqlite3.Connection, brief_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    return dict(row) if row else None


def update_brief_refine_metadata(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    refine_depth: int,
    refine_overrides: dict,
) -> None:
    conn.execute(
        "UPDATE briefs SET refine_depth = ?, refine_overrides = ? WHERE brief_id = ?",
        (refine_depth, json.dumps(refine_overrides), brief_id),
    )
    conn.commit()
