"""Telegram outbound channel — send_message via the Bot API.

Reads bot token from env IIC_TELEGRAM_BOT_TOKEN. allowed_chat_ids[0] is the
destination. Inline keyboard ([Run Backtest] [Dismiss]) is attached only
for mode='event_alert'.

The polling loop for incoming updates is a separate process (Task 13).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict

from tradingagents.delivery.base import DeliveryChannel, DeliveryError
from tradingagents.persistence import store


_BOT_CACHE: dict = {}


def _get_bot(token: str):
    """Lazy import + cache. Returns a python-telegram-bot Bot instance."""
    if token in _BOT_CACHE:
        return _BOT_CACHE[token]
    from telegram import Bot
    bot = Bot(token=token)
    _BOT_CACHE[token] = bot
    return bot


def _make_event_alert_keyboard(brief_id: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Run Backtest",
            callback_data=f"act:{brief_id}:run_backtest:yes",
        ),
        InlineKeyboardButton(
            "Dismiss",
            callback_data=f"act:{brief_id}:run_backtest:no",
        ),
    ]])


class TelegramOutbound(DeliveryChannel):
    channel_name = "telegram"

    def send(self, *, brief: Dict[str, Any], mode: str, body: str) -> int:
        cfg = self._config["telegram_bot"]
        if not cfg.get("enabled", False) or not cfg.get("allowed_chat_ids"):
            return store.insert_delivery(
                self._conn, brief_id=brief["brief_id"], channel=self.channel_name,
                status="skipped", sent_ts=None, channel_ref=None,
                skip_reason="telegram_disabled",
            )
        return super().send(brief=brief, mode=mode, body=body)

    def _send_impl(self, brief: Dict[str, Any], mode: str, body: str) -> tuple:
        token = os.environ.get("IIC_TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError("IIC_TELEGRAM_BOT_TOKEN not set")

        allowed = self._config["telegram_bot"].get("allowed_chat_ids") or []
        if not allowed:
            raise DeliveryError(
                "no Telegram target chat configured; "
                "set TELEGRAM_BOT_ALLOWED_CHAT_IDS"
            )
        chat_id = allowed[0]
        bot = _get_bot(token)

        keyboard = _make_event_alert_keyboard(brief["brief_id"]) if mode == "event_alert" else None

        coro = bot.send_message(
            chat_id=chat_id,
            text=body,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        sent = _run_coro(coro)
        return (f"{chat_id}:{sent.message_id}", None)


def _run_coro(coro):
    """Run an async coroutine to completion, regardless of current loop state."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
