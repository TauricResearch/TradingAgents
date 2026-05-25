"""Telegram OSINT vendor — sentiment/news source, not market data.

Reads recent messages from a curated list of channels (configured via
``telegram_channels`` in DEFAULT_CONFIG) using a local Telethon user
session. Raise :class:`DataVendorError` on missing creds / auth failure so
``route_to_vendor`` falls back gracefully.

Required env: ``TELEGRAM_API_ID``, ``TELEGRAM_API_HASH``,
``TELEGRAM_SESSION`` (path or session string).

NOTE: This is a skeleton. The Telethon iteration / digest formatting is
left as TODO so the dependency isn't required until you actually configure
it. With no creds set, the function raises DataVendorError and the analyst
falls back to non-OSINT inputs.
"""

import os

from .errors import DataVendorError


def get_telegram_signals(query: str, start_date: str, end_date: str) -> str:
    """Recent messages from curated channels matching ``query`` in the window."""
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        raise DataVendorError("Telegram API creds (TELEGRAM_API_ID/TELEGRAM_API_HASH) not set")
    raise DataVendorError("telegram_osint.get_telegram_signals: implementation pending")
