"""Telegram OSINT vendor — sentiment/news source, pull-style.

Uses Telethon ``iter_messages`` against the configured ``telegram_channels``
list. F3's *streaming* adapter uses a separate session (TELEGRAM_SENSING_SESSION)
to avoid Telethon's "second connection on the same session" auth kick.

Required env: ``TELEGRAM_API_ID``, ``TELEGRAM_API_HASH``, optional
``TELEGRAM_OSINT_SESSION`` (default ``iic_osint.session``).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List

from .errors import DataVendorError

try:
    from telethon.sync import TelegramClient
except Exception:  # pragma: no cover — optional dep
    TelegramClient = None  # type: ignore


def _parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def get_telegram_signals(query: str, start_date: str, end_date: str) -> str:
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        raise DataVendorError(
            "Telegram API creds (TELEGRAM_API_ID/TELEGRAM_API_HASH) not set"
        )
    if TelegramClient is None:
        raise DataVendorError("telethon not installed; pip install -e .[osint]")
    session = os.environ.get("TELEGRAM_OSINT_SESSION", "iic_osint.session")

    from tradingagents.default_config import DEFAULT_CONFIG
    channels: List[str] = list(DEFAULT_CONFIG.get("telegram_channels") or [])
    if not channels:
        return f"(no telegram_channels configured for query={query!r})"

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    matches: List[str] = []
    with TelegramClient(session, int(api_id), api_hash) as client:
        for ch in channels:
            try:
                for msg in client.iter_messages(ch, limit=200):
                    if msg.date is None or not (start <= msg.date <= end):
                        continue
                    text = (msg.message or "").strip()
                    if not text:
                        continue
                    if query.lower() in text.lower():
                        matches.append(f"- [{ch} @ {msg.date.isoformat()}]: {text[:300]}")
            except Exception as e:
                matches.append(f"- ({ch} fetch failed: {e})")
    if not matches:
        return f"(no matches for {query!r} across {len(channels)} channels)"
    header = f"## Telegram OSINT — {query} [{start_date} … {end_date}]\n"
    return header + "\n".join(matches[:50])
