"""Validate LLM-extracted tickers against the reference table.

Unknown / inactive symbols are dropped — this is the hallucination guard
for D5 of the spec. The reference set is cached in-process; call
`refresh()` to re-read after seeding.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, List, Set


class TickerValidator:
    def __init__(self, *, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cache: Set[str] | None = None

    def refresh(self) -> None:
        """Force re-read on next filter() call."""
        self._cache = None

    def _set(self) -> Set[str]:
        if self._cache is None:
            from tradingagents.persistence.store import get_tickers_set
            self._cache = get_tickers_set(self._conn)
        return self._cache

    def filter(self, tickers: Iterable[str]) -> List[str]:
        ref = self._set()
        # Preserve order; drop unknowns; de-dupe.
        seen: Set[str] = set()
        out: List[str] = []
        for t in tickers:
            t = t.upper().strip()
            if t in ref and t not in seen:
                out.append(t)
                seen.add(t)
        return out
