"""F3 triage consumer — pulls from Redis, dedupes, scores, persists.

This module exposes:
  - ``Triage``: the per-envelope pipeline (``process_one``) and consumer loop.
  - ``main()``: systemd entry point.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional, Sequence

import redis.asyncio as aioredis

from tradingagents.persistence.store import (
    insert_event, insert_event_ticker,
)
from tradingagents.sensing.dedupe import DedupeStage1, DedupeStage2
from tradingagents.sensing.envelope import Envelope
from tradingagents.sensing.salience import SalienceScorer, SalienceResult
from tradingagents.sensing.ticker_validator import TickerValidator
from tradingagents.sensing.watchlist import auto_promote


log = logging.getLogger(__name__)


@dataclass
class TriageResult:
    event_id: str
    status: str               # "triaged" | "duplicate"
    salience: Optional[float] = None
    deduped_of: Optional[str] = None
    matched_tickers: Sequence[str] = ()


class Triage:
    """Owns the per-envelope pipeline and the consume loop.

    Constructed once per triage process; one instance is shared across
    all asyncio consumers.
    """

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        redis: aioredis.Redis,
        embedder,                                          # Embedder
        llm_call: Callable[[str], "str | Awaitable[str]"],
        data_dir: str,
        cosine_threshold: float = 0.92,
        window_hours: int = 24,
        fingerprint_ttl_hours: int = 72,
        salience_threshold: float = 0.7,
        confidence_threshold: float = 0.8,
        salience_cache_ttl_seconds: int = 86400,
        ttl_days: int = 7,
    ) -> None:
        self._conn = conn
        self._redis = redis
        self._data_dir = data_dir
        self._ds1 = DedupeStage1(conn=conn, redis=redis,
                                  fingerprint_ttl_hours=fingerprint_ttl_hours)
        self._ds2 = DedupeStage2(conn=conn, embedder=embedder,
                                  cosine_threshold=cosine_threshold,
                                  window_hours=window_hours)
        self._scorer = SalienceScorer(redis=redis, llm_call=llm_call,
                                       cache_ttl_seconds=salience_cache_ttl_seconds)
        self._validator = TickerValidator(conn=conn)
        self._salience_threshold = salience_threshold
        self._confidence_threshold = confidence_threshold
        self._ttl_days = ttl_days
        # In-process cached active watchlist; refreshed by the loop every N s.
        self._watchlist: list[str] = []

    # ------------------------------------------------------------------
    def _new_event_id(self) -> str:
        return uuid.uuid4().hex

    def _canonical_raw_path(self, event_id: str, src_staging_path: str) -> str:
        canonical_dir = Path(self._data_dir) / "events"
        canonical_dir.mkdir(parents=True, exist_ok=True)
        dst = canonical_dir / f"{event_id}.json"
        try:
            shutil.move(src_staging_path, dst)
        except FileNotFoundError:
            # Staging file gone (test envelopes may not write one); leave path absent.
            return ""
        return str(dst)

    def set_active_watchlist(self, tickers: Sequence[str]) -> None:
        self._watchlist = list(tickers)

    # ------------------------------------------------------------------
    async def process_one(self, env: Envelope) -> TriageResult:
        """Run the full pipeline on one envelope. Always writes a row."""
        # Stage 1: hash / external_id dedupe.
        hit1 = await self._ds1.check(env)
        if hit1:
            ev_id = self._new_event_id()
            insert_event(
                self._conn, event_id=ev_id, source=env.source,
                ingested_ts=env.ingested_ts, salience=None,
                raw_path=self._canonical_raw_path(ev_id, env.raw_path),
                status="duplicate", deduped_of=hit1,
            )
            return TriageResult(event_id=ev_id, status="duplicate",
                                deduped_of=hit1)

        # Stage 2: embedding cosine.
        hit2 = self._ds2.check(env.text)
        if hit2:
            ev_id = self._new_event_id()
            insert_event(
                self._conn, event_id=ev_id, source=env.source,
                ingested_ts=env.ingested_ts, salience=None,
                raw_path=self._canonical_raw_path(ev_id, env.raw_path),
                status="duplicate", deduped_of=hit2,
            )
            return TriageResult(event_id=ev_id, status="duplicate",
                                deduped_of=hit2)

        # Score salience.
        score: SalienceResult = await self._scorer.score(
            env=env, watchlist=self._watchlist, macro_context="",
        )

        # Resolve tickers: union(source_tags.tickers, mentioned_tickers) → validate.
        candidate = list(env.source_tags.get("tickers", [])) + \
                    [m.ticker for m in score.mentioned_tickers]
        validated = self._validator.filter(candidate)

        # Write event.
        ev_id = self._new_event_id()
        insert_event(
            self._conn, event_id=ev_id, source=env.source,
            ingested_ts=env.ingested_ts, salience=score.salience,
            raw_path=self._canonical_raw_path(ev_id, env.raw_path),
            status="triaged", deduped_of=None,
        )
        # Record fingerprints + embedding (only on non-duplicates).
        await self._ds1.record(env, event_id=ev_id)
        self._ds2.record(text=env.text, event_id=ev_id)

        # Per-ticker rows + watchlist gate.
        conf_by_ticker = {m.ticker: m.confidence for m in score.mentioned_tickers}
        for t in validated:
            conf = conf_by_ticker.get(t, 0.5)  # source-tag tickers default to 0.5
            insert_event_ticker(self._conn, event_id=ev_id, ticker=t,
                                 confidence=conf)
            auto_promote(
                self._conn, ticker=t, event_id=ev_id,
                salience=score.salience, confidence=conf,
                salience_threshold=self._salience_threshold,
                confidence_threshold=self._confidence_threshold,
                ttl_days=self._ttl_days,
            )

        return TriageResult(event_id=ev_id, status="triaged",
                            salience=score.salience,
                            matched_tickers=score.matched_tickers)
