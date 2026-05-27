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


# ----------------------------------------------------------------------
# Consume loop + dead-letter sweep + systemd entry point
# ----------------------------------------------------------------------

async def dead_letter_sweep(
    r: aioredis.Redis,
    *,
    src_stream: str,
    group: str,
    dead_stream: str,
    max_deliveries: int,
) -> int:
    """Move PEL entries with delivery_count >= max_deliveries to ``dead_stream``.

    Returns # of messages moved. Safe to call repeatedly.
    """
    pending = await r.xpending_range(src_stream, group,
                                      min="-", max="+", count=200)
    moved = 0
    for p in pending:
        # max_deliveries is the threshold "this many failed attempts means dead";
        # so times_delivered < max_deliveries → keep trying, otherwise → move.
        if int(p["times_delivered"]) < max_deliveries:
            continue
        msg_id = p["message_id"]
        # Read the message to copy it.
        items = await r.xrange(src_stream, min=msg_id, max=msg_id)
        if not items:
            await r.xack(src_stream, group, msg_id)
            continue
        _, fields = items[0]
        await r.xadd(dead_stream, fields)
        await r.xack(src_stream, group, msg_id)
        moved += 1
    return moved


def _decode_fields(raw_fields):
    """Normalize bytes-or-str fields to a flat str dict."""
    out = {}
    for k, v in raw_fields.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8")
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        out[k] = v
    return out


# Attach to Triage as methods.
async def _consume_once(self, *, group: str, consumer: str, stream: str,
                         block_ms: int, batch: int) -> int:
    """Read one XREADGROUP batch and process each envelope.

    Successful envelopes are XACKed. Failures leave the message on the
    Pending Entries List, where dead_letter_sweep picks them up after
    max_deliveries retries.
    """
    try:
        result = await self._redis.xreadgroup(
            groupname=group, consumername=consumer,
            streams={stream: ">"}, count=batch, block=block_ms,
        )
    except Exception:
        log.exception("XREADGROUP failed"); return 0
    if not result:
        return 0
    handled = 0
    for _stream_name, entries in result:
        for env_id, raw_fields in entries:
            try:
                fields = _decode_fields(raw_fields)
                env = Envelope.from_redis_fields(fields)
                await self.process_one(env)
                await self._redis.xack(stream, group, env_id)
                handled += 1
            except Exception:
                log.exception("triage failed for %s; leaving on PEL", env_id)
    return handled


async def _consume_forever(self, *, group: str, consumer: str, stream: str,
                            block_ms: int, batch: int) -> None:
    while True:
        try:
            await self.consume_once(group=group, consumer=consumer,
                                     stream=stream, block_ms=block_ms,
                                     batch=batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("consume_forever iteration crashed")
            await asyncio.sleep(1)


Triage.consume_once = _consume_once             # type: ignore[attr-defined]
Triage.consume_forever = _consume_forever       # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Systemd entry point
# ----------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.persistence.store import get_active_watchlist
    from tradingagents.sensing.embeddings import SentenceTransformerEmbedder
    from tradingagents.sensing.redis_client import make_redis, ensure_consumer_group

    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])

    # Build the LLM caller from the existing factory.
    from tradingagents.llm_clients.factory import create_llm_client
    quick_client = create_llm_client(
        provider=C["llm_provider"], model=C["quick_think_llm"],
        base_url=C.get("backend_url"),
    )
    llm = quick_client.get_llm()
    def call_llm(prompt: str) -> str:
        # LangChain chat models expose .invoke for str-or-message input.
        out = llm.invoke(prompt)
        return getattr(out, "content", str(out))

    t = Triage(
        conn=conn, redis=redis,
        embedder=SentenceTransformerEmbedder(C["sensing_embedder_model"]),
        llm_call=call_llm,
        data_dir=C["iic_data_dir"],
        cosine_threshold=C["sensing_dedupe_cosine_threshold"],
        window_hours=C["sensing_dedupe_window_hours"],
        fingerprint_ttl_hours=C["sensing_fingerprint_ttl_hours"],
        salience_threshold=C["sensing_watchlist_salience_threshold"],
        confidence_threshold=C["sensing_watchlist_confidence_threshold"],
        salience_cache_ttl_seconds=C["sensing_salience_cache_ttl_seconds"],
        ttl_days=C["sensing_watchlist_ttl_days"],
    )

    async def run() -> None:
        await ensure_consumer_group(
            redis, stream=C["sensing_ingest_stream"], group=C["sensing_consumer_group"],
        )
        # Watchlist refresher: every N seconds, refresh in-process cache.
        async def refresher():
            while True:
                try:
                    t.set_active_watchlist(get_active_watchlist(conn))
                except Exception:
                    log.exception("watchlist refresh failed")
                await asyncio.sleep(C["sensing_watchlist_refresh_seconds"])

        # Dead-letter sweep every minute.
        async def reaper():
            while True:
                try:
                    await dead_letter_sweep(
                        redis,
                        src_stream=C["sensing_ingest_stream"],
                        group=C["sensing_consumer_group"],
                        dead_stream=C["sensing_dead_stream"],
                        max_deliveries=C["sensing_triage_max_failures"],
                    )
                except Exception:
                    log.exception("dead-letter sweep failed")
                await asyncio.sleep(60)

        # N consumers + refresher + reaper.
        tasks = [refresher(), reaper()]
        for i in range(C["sensing_triage_consumers"]):
            tasks.append(t.consume_forever(
                group=C["sensing_consumer_group"],
                consumer=f"c{i}",
                stream=C["sensing_ingest_stream"],
                block_ms=5000, batch=10,
            ))
        await asyncio.gather(*tasks)

    asyncio.run(run())


if __name__ == "__main__":
    _main()
