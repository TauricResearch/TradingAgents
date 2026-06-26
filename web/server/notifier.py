"""
Telegram notifier for the dashboard indicators panel.

Sends HTML-formatted messages to a Telegram chat whenever one or more
indicators are triggered. Uses python-telegram-bot v21+ (async).

Why HTML and not MarkdownV2?
  MarkdownV2 requires escaping ~30 special characters everywhere, including
  inside the plain-text parts of the message. Getting this wrong silently
  breaks rendering. HTML only requires escaping &, <, and > — much safer.

Setup
-----
1. Message @BotFather on Telegram → /newbot → copy the token.
2. Message @userinfobot on Telegram → copy your chat ID.
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file.
"""

from __future__ import annotations

import html
import logging
import os
from datetime import UTC, datetime
from typing import Any

from telegram import Bot

_TELEGRAM_AVAILABLE = not os.environ.get("TESTING")


def _require_telegram() -> None:
    if not _TELEGRAM_AVAILABLE:
        raise ImportError("telegram is not available in test environment")

logger = logging.getLogger(__name__)


class IndicatorResult:
    """
    Wrapper for indicator check results to provide a consistent interface
    for the notifier.
    """

    def __init__(
        self,
        name: str,
        triggered: bool,
        value: Any,
        threshold: Any,
        message: str,
        checked_at: datetime | None = None,
    ) -> None:
        self.name = name
        self.triggered = triggered
        self.value = value
        self.threshold = threshold
        self.message = message
        self.checked_at = checked_at or datetime.now(tz=UTC)

    def to_telegram_line(self) -> tuple[str, str, bool]:
        """Return a (name, message, triggered) tuple for the notifier."""
        return self.name, self.message, self.triggered


class TelegramNotifier:
    """
    Sends HTML-formatted indicator summaries to a Telegram chat.

    Parameters
    ----------
    token:   Bot token from BotFather. Falls back to TELEGRAM_BOT_TOKEN env var.
    chat_id: Target chat / user ID. Falls back to TELEGRAM_CHAT_ID env var.
    """

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | int | None = None,
    ) -> None:
        self._token: str = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id: str = str(chat_id) if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")
        if not self._token or not self._chat_id:
            raise ValueError(
                "Telegram notifier requires both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
                "to be set in .env or passed as constructor arguments"
            )
        self._bot = Bot(token=self._token)

    async def send_results(self, results: list[IndicatorResult]) -> None:
        """
        Send a Telegram message summarising all indicator results.

        Only called when at least one indicator is triggered.
        """
        text = build_results_message(results)
        await self._send(text)
        logger.info("Telegram notification sent (%d triggered).", sum(r.triggered for r in results))

    async def send_heartbeat(self, results: list[IndicatorResult]) -> None:
        """
        Send a daily summary regardless of trigger state.

        Useful for confirming the bot is alive. All results are shown.
        """
        text = build_heartbeat_message(results)
        await self._send(text)
        logger.info("Telegram heartbeat sent.")

    async def _send(self, text: str) -> None:
        """Send text to the configured chat, with actionable error messages."""
        from telegram.error import Forbidden, InvalidToken

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
            )
        except Forbidden as exc:
            raise RuntimeError(
                f"Telegram Forbidden: {exc}\n\n"
                "Your TELEGRAM_CHAT_ID is wrong — it points to a bot, not your user account.\n"
                "To get your personal chat ID:\n"
                "  1. Open Telegram and search for @userinfobot\n"
                "  2. Send it any message (e.g. /start)\n"
                "  3. It replies with your numeric user ID — paste that into .env as "
                f"TELEGRAM_CHAT_ID\n"
                f"  Current value: {self._chat_id}"
            ) from exc
        except InvalidToken as exc:
            raise RuntimeError(
                f"Telegram InvalidToken: {exc}\n\n"
                "Your TELEGRAM_BOT_TOKEN is invalid.\n"
                "To get a valid token:\n"
                "  1. Open Telegram and search for @BotFather\n"
                "  2. Send /mybots → select your bot → API Token\n"
                "  3. Paste the token into .env as TELEGRAM_BOT_TOKEN"
            ) from exc

    async def send_message_to(self, chat_id: int, text: str) -> None:
        """Send arbitrary HTML text to a specific chat ID.

        This is useful for replying directly to an incoming user command
        (e.g., the `/fetch` handler) instead of always using the configured
        `TELEGRAM_CHAT_ID`.
        """
        from telegram.error import Forbidden, InvalidToken

        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Forbidden as exc:
            raise RuntimeError(f"Telegram Forbidden when sending to {chat_id}: {exc}") from exc
        except InvalidToken as exc:
            raise RuntimeError(f"Telegram InvalidToken: {exc}") from exc

    async def send_results_to(self, chat_id: int, results: list[IndicatorResult]) -> None:
        text = build_results_message(results)
        await self.send_message_to(chat_id, text)

    async def send_heartbeat_to(self, chat_id: int, results: list[IndicatorResult]) -> None:
        text = build_heartbeat_message(results)
        await self.send_message_to(chat_id, text)


def _build_message(
    results: list[IndicatorResult],
    *,
    triggered_count: int = 0,
    heartbeat: bool = False,
) -> str:
    """
    Build an HTML-formatted Telegram message from a list of IndicatorResults.

    HTML escaping is applied to all dynamic strings so special characters in
    indicator names or messages never break the parse mode.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    if heartbeat:
        header = f"📊 <b>TradingAgents Indicators — Heartbeat</b>\n<i>{_e(now)}</i>\n"
    else:
        count_word = f"{triggered_count} signal{'s' if triggered_count != 1 else ''}"
        header = f"🚨 <b>TradingAgents Indicators — {_e(count_word)} triggered!</b>\n<i>{_e(now)}</i>\n"

    lines = [header]
    for r in results:
        name, message, triggered = r.to_telegram_line()
        icon = "✅" if triggered else "⬜"
        lines.append(f"{icon} <b>{_e(name)}</b> — {_e(message)}")

    lines.append("")
    lines.append("<i>Automated indicator alert. Not financial advice.</i>")
    return "\n".join(lines)


def build_results_message(results: list[IndicatorResult]) -> str:
    """Build the standard indicator results message for a Telegram chat."""
    return _build_message(results, triggered_count=sum(r.triggered for r in results))


def build_heartbeat_message(results: list[IndicatorResult]) -> str:
    """Build the daily heartbeat message for a Telegram chat."""
    return _build_message(results, heartbeat=True)


def _e(text: str) -> str:
    """Escape a string for safe inclusion in an HTML Telegram message."""
    return html.escape(str(text))


def _results_from_check_response(checks: list[dict[str, Any]]) -> list[IndicatorResult]:
    """Convert the raw /api/indicators/check response format to IndicatorResult objects."""
    results = []
    for check in checks:
        indicator = check.get("indicator", {})
        result = check.get("result") or {}
        results.append(
            IndicatorResult(
                name=indicator.get("name", "Unknown"),
                triggered=result.get("triggered", False),
                value=result.get("value"),
                threshold=result.get("threshold"),
                message=result.get("message", ""),
                checked_at=datetime.fromisoformat(result.get("checked_at", "").replace("Z", "+00:00"))
                if result.get("checked_at")
                else None,
            )
        )
    return results
