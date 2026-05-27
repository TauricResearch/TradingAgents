"""Telegram sensing adapter — Telethon NewMessage streaming.

Uses a SEPARATE session from the F0 OSINT pull path. Two session files
exist because Telethon kicks a second concurrent connection on the same
session.

Cursor: JSON dict mapping channel username → max message_id seen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import List

import redis.asyncio as aioredis

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "telegram"


async def _on_message(event, *, redis, conn, stream: str, staging_root: str) -> None:
    msg = event.message
    text = (msg.message or "").strip()
    if not text:
        return
    channel = getattr(event.chat, "username", None) or "unknown"
    cs = CursorStore(conn)
    cursors = json.loads(cs.get(NAME) or "{}")
    cursors[channel] = max(int(cursors.get(channel, 0)), int(msg.id))
    env = Envelope(
        source=NAME,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id=f"tg:{channel}:{msg.id}",
        text=text,
        source_tags={"channel": channel,
                     "msg_date": msg.date.isoformat()},
        raw_path="",
    )
    writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                             stream=stream, staging_root=staging_root)
    await writer.write(env, raw_payload={"channel": channel,
                                          "message_id": msg.id,
                                          "text": text},
                       cursor=json.dumps(cursors))


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        log.error("TELEGRAM_API_ID/HASH not set; exiting 1")
        raise SystemExit(1)
    session = os.environ.get("TELEGRAM_SENSING_SESSION", "iic_sensing.session")

    from telethon import TelegramClient, events  # lazy import

    channels: List[str] = list(C.get("telegram_channels") or [])
    if not channels:
        log.warning("telegram_channels config empty; nothing to listen to")

    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")

    client = TelegramClient(session, int(api_id), api_hash)

    @client.on(events.NewMessage(chats=channels))
    async def handler(event):
        try:
            await _on_message(event, redis=redis, conn=conn,
                              stream=C["sensing_ingest_stream"],
                              staging_root=staging)
        except Exception:
            log.exception("telegram handler crashed (event dropped, will continue)")

    log.info("telegram sensing adapter started; channels=%s", channels)
    client.start()  # interactive prompt only if session is brand-new
    client.run_until_disconnected()


if __name__ == "__main__":
    _main()
