"""Telegram Bot API client — no Streamlit dependency.

One shared bot. Token in ``.env`` as ``TELEGRAM_BOT_TOKEN``. Users hand-paste
their personal ``chat_id`` (from @userinfobot) into the webui prefs.

If your host can't reach ``api.telegram.org`` directly (e.g. mainland-China
networks), set ``HTTPS_PROXY`` / ``HTTP_PROXY`` in the environment before
running — ``requests`` honours them automatically.
"""
from __future__ import annotations

import os
import time
from typing import Tuple

import requests

API_URL_TMPL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG_LEN = 4096
DEFAULT_TIMEOUT_SEC = 30
RETRY_DELAY_SEC = 5


def _split(text: str, limit: int = MAX_MSG_LEN) -> list[str]:
    """Split a long message on paragraph boundaries to stay under Telegram's limit."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remainder = text
    while len(remainder) > limit:
        # Prefer a blank-line break, then a single newline, then a hard cut.
        cut = remainder.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = remainder.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remainder[:cut].rstrip())
        remainder = remainder[cut:].lstrip()
    if remainder:
        parts.append(remainder)
    return parts


def send_telegram(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str | None = "Markdown",
    disable_web_page_preview: bool = True,
    disable_notification: bool = False,
    token: str | None = None,
) -> Tuple[bool, str]:
    """Send a message to a Telegram chat. Returns (ok, detail).

    Splits long messages into multiple sends. Retries once on transient HTTP
    failures. ``parse_mode="Markdown"`` is the legacy markdown the Bot API
    supports natively (use "MarkdownV2" if you escape ``_*[]()~``…). Pass
    ``parse_mode=None`` to send literal text (safe for LLM output that may
    contain stray ``*`` or ``_`` characters).

    ``disable_notification=True`` makes the message silent (no sound / vibration,
    only a red badge). Useful for follow-up messages after a notification one.
    """
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        return False, "TELEGRAM_BOT_TOKEN is not set"
    if not chat_id:
        return False, "empty chat_id"

    url = API_URL_TMPL.format(token=bot_token)
    parts = _split(text)
    last_detail = ""
    for idx, part in enumerate(parts):
        payload: dict = {
            "chat_id": str(chat_id),
            "text": part,
            "disable_web_page_preview": disable_web_page_preview,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        for attempt in (1, 2):
            try:
                r = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT_SEC)
                if r.status_code == 200:
                    last_detail = "ok"
                    break
                # 429 = rate-limited; obey retry_after if Telegram tells us
                if r.status_code == 429:
                    retry = r.json().get("parameters", {}).get("retry_after", RETRY_DELAY_SEC)
                    time.sleep(min(int(retry), 60))
                    continue
                last_detail = f"HTTP {r.status_code}: {r.text[:200]}"
                if attempt == 2:
                    return False, f"part {idx + 1}/{len(parts)} failed: {last_detail}"
                time.sleep(RETRY_DELAY_SEC)
            except requests.RequestException as e:
                last_detail = f"{type(e).__name__}: {e}"
                if attempt == 2:
                    return False, f"part {idx + 1}/{len(parts)} failed: {last_detail}"
                time.sleep(RETRY_DELAY_SEC)
        else:
            return False, last_detail
    return True, "ok"


__all__ = ["send_telegram"]
