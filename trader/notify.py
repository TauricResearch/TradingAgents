"""Telegram messages, or log lines when no bot is configured. What Telegram does not
take can wait in a ledger for the next try (``Outbox``)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import requests

from trader.ledger import Ledger
from trader.settings import Settings

logger = logging.getLogger(__name__)

_LIMIT = 4000  # Telegram rejects messages over 4096 characters
OUTBOX_LIMIT = 50  # the most messages an outbox keeps; the oldest give way, the log has them all


class Notifier:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.token = settings.telegram_token
        self.chat_id = settings.telegram_chat_id
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        """Whether there is a chat to send to; without one, ``send`` only logs."""
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        """Log ``text`` and send it to the chat; True when Telegram took it.

        Never raises: losing a message must not stop the trading it reports on.
        """
        logger.info("notify: %s", text)
        if not self.configured:
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


class Labeled:
    """A notifier that heads each message with ``【label】``: the accounts that share the
    chat, one of them with real money (ADR 0010), are told apart at a glance. Every
    account's messages are labeled (``trader.message`` names the paper accounts'). A
    message split into several goes out with the label on its first piece."""

    def __init__(self, notifier: Notifier, label: str):
        self.notifier = notifier
        self.label = label

    @property
    def configured(self) -> bool:
        return self.notifier.configured

    def send(self, text: str) -> bool:
        return self.notifier.send(f"【{self.label}】{text}")


def labeled(notifier: Notifier | Labeled, label: str) -> Labeled:
    """``notifier`` labeled with ``label``; one that already is comes back as it is."""
    if isinstance(notifier, Labeled) and notifier.label == label:
        return notifier
    return Labeled(notifier, label)


class Outbox:
    """A notifier that keeps what it fails to send in a ledger (meta ``key``), for
    ``flush`` to send the next time, ahead of anything new: Telegram down or refusing
    loses no message. Each is kept with when it failed and the ``kind`` it was sent with,
    oldest first, at most OUTBOX_LIMIT of them; how many gave way to newer ones is
    counted. A notifier with no chat configured has nowhere to send and keeps nothing."""

    def __init__(
        self, notifier: Notifier | Labeled, ledger: Ledger, key: str, now_ms: Callable[[], int]
    ):
        self.notifier = notifier
        self.ledger = ledger
        self.key = key
        self.now_ms = now_ms

    def send(self, text: str, kind: str | None = None) -> bool:
        """Send ``text``, or keep it; True when Telegram took it."""
        if self.notifier.send(text):
            return True
        if self.notifier.configured:
            kept = self._kept()
            kept["messages"].append({"text": text, "at": self.now_ms(), "kind": kind})
            excess = len(kept["messages"]) - OUTBOX_LIMIT
            if excess > 0:
                del kept["messages"][:excess]
                kept["dropped"] += excess
            self.ledger.set(self.key, kept)
        return False

    def holds(self, kind: str) -> bool:
        """Whether a message sent with ``kind`` is waiting to go out."""
        return any(m["kind"] == kind for m in self._kept()["messages"])

    def flush(self) -> list[str]:
        """Send what was kept, oldest first, each saying when it should have gone out,
        until Telegram fails again; the rest stays. Returns the kinds of those sent."""
        kept = self._kept()
        if not kept["messages"] and not kept["dropped"]:
            return []
        sent: list[str] = []
        if kept["dropped"]:
            if not self.notifier.send(
                f"有 {kept['dropped']} 条更早的消息当时没发出去，也没留着补发：全文在运行日志里"
            ):
                return sent
            kept["dropped"] = 0
        while kept["messages"]:
            message = kept["messages"][0]
            when = datetime.fromtimestamp(message["at"] / 1000, UTC).strftime("%m-%d %H:%M")
            if not self.notifier.send(f"{message['text']}\n（补发：{when} UTC 没发出去）"):
                break
            kept["messages"].pop(0)
            if message["kind"]:
                sent.append(message["kind"])
        self.ledger.set(self.key, kept)
        return sent

    def _kept(self) -> dict:
        return self.ledger.get(self.key) or {"messages": [], "dropped": 0}
