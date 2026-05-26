"""Hybrid persona memory.

- ``PersonaMemoryStore`` is the ONLY interface for writing or reading persona
  memories. Construction takes a ``persona_id`` and a ``component``; every
  query is automatically filtered by both. There is no API that returns
  cross-persona rows. The class-level invariant — enforced in __init__ — is
  that ``persona_id`` is a non-empty, non-wildcard string.
- ``OutcomeLog`` is the shared cross-persona pool. Reads are NOT scoped to
  any persona by design; this is how personas learn from each other's
  outcomes (see ADR-NEW-2 in the program design).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional


_RESERVED_PERSONA_IDS = {"", "*", "all", "any"}


class PersonaMemoryStore:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        persona_id: str,
        component: str,
    ) -> None:
        if not persona_id or persona_id in _RESERVED_PERSONA_IDS:
            raise ValueError(
                f"persona_id must be a concrete persona name; got {persona_id!r}"
            )
        if not component:
            raise ValueError("component must be a non-empty string")
        self._conn = conn
        self._persona_id = persona_id
        self._component = component

    def add_memory(
        self,
        *,
        situation_md: str,
        outcome: Optional[str] = None,
        vec_id: Optional[int] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO memories (persona_id, component, situation_md, outcome, "
            "vec_id, created_ts) VALUES (?, ?, ?, ?, ?, ?)",
            (self._persona_id, self._component, situation_md, outcome, vec_id, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent(self, limit: int = 5) -> List[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM memories WHERE persona_id = ? AND component = ? "
            "ORDER BY created_ts DESC LIMIT ?",
            (self._persona_id, self._component, limit),
        ))


class OutcomeLog:
    """Shared cross-persona outcome pool. Reads are intentionally unscoped."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(
        self,
        *,
        run_id: str,
        ticker: str,
        decision: str,
        outcome_md: str,
        pnl_proxy: Optional[float] = None,
        vec_id: Optional[int] = None,
        tags: Optional[dict] = None,
    ) -> int:
        import json
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO outcome_log (run_id, ticker, decision, outcome_md, "
            "pnl_proxy, vec_id, tags, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, ticker, decision, outcome_md, pnl_proxy, vec_id,
             json.dumps(tags) if tags else None, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent_for_ticker(self, ticker: str, limit: int = 10) -> List[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM outcome_log WHERE ticker = ? ORDER BY created_ts DESC LIMIT ?",
            (ticker, limit),
        ))
