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
    rows = conn.execute(
        "SELECT ticker FROM watchlist "
        "WHERE ttl_until IS NULL OR ttl_until > datetime('now')"
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
