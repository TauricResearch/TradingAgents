"""Telegram messages, or log lines when no bot is configured."""

from __future__ import annotations

import logging

import requests

from trader.settings import Settings

logger = logging.getLogger(__name__)

_LIMIT = 4000  # Telegram rejects messages over 4096 characters


class Notifier:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.token = settings.telegram_token
        self.chat_id = settings.telegram_chat_id
        self.session = session or requests.Session()

    def send(self, text: str) -> bool:
        """Log ``text`` and send it to the chat; True when Telegram took it.

        Never raises: losing a message must not stop the trading it reports on.
        """
        logger.info("notify: %s", text)
        if not (self.token and self.chat_id):
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            for chunk in _chunks(text):
                response = self.session.post(
                    url, json={"chat_id": self.chat_id, "text": chunk}, timeout=10
                )
                response.raise_for_status()
        except requests.RequestException as exc:
            # The request URL carries the bot token, so the error's message is not logged.
            status = getattr(exc.response, "status_code", None)
            logger.error("telegram send failed: %s %s", type(exc).__name__, status or "")
            return False
        return True


def _chunks(text: str) -> list[str]:
    """Split ``text`` at line breaks into pieces under Telegram's limit."""
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > _LIMIT:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    # A single line longer than the limit is cut where it must be.
    return [c[i:i + _LIMIT] for c in chunks for i in range(0, len(c), _LIMIT)]
