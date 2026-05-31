"""Telegram bot polling service — receives callbacks + replies.

Two responsibilities:
  - callback queries (inline button clicks): "act:<brief_id>:<action_type>:yes|no"
  - text replies to brief messages: resolve via deliveries.channel_ref

Both create brief_actions rows; never call F2 or the secretary directly.

main() runs the polling loop; called from systemd unit iic-telegram-bot.service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from tradingagents.persistence import store


log = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_at(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def handle_callback(*, update: Any, conn: sqlite3.Connection) -> None:
    """Inline button click → brief_actions row."""
    data = update.callback_query.data or ""
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "act":
        return
    _, brief_id, action_type, answer = parts

    chat_id = update.callback_query.message.chat.id
    message_id = update.callback_query.message.message_id
    channel_ref = f"{chat_id}:{message_id}"
    resolved = store.resolve_brief_id_by_channel_ref(
        conn, channel="telegram", channel_ref=channel_ref,
    )
    if resolved != brief_id:
        return

    state = "accepted" if answer == "yes" else "declined"
    # Prefer transitioning the pending action created at delivery time (S-8),
    # so a click does NOT create a duplicate row. Fall back to insert only when
    # no pending action exists (edge case: legacy brief delivered pre-S-8).
    pending = store.get_pending_action_by_brief(
        conn, brief_id=brief_id, action_type=action_type,
    )
    if pending is not None:
        aid = pending["action_id"]
    else:
        expires = _expires_at(24)
        aid = store.insert_brief_action(
            conn, brief_id=brief_id, action_type=action_type,
            action_params={}, expires_at=expires,
        )
    store.update_action_state(
        conn, action_id=aid, state=state, responded_at=_utc_now_iso(),
    )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                update.callback_query.answer(text="OK"), loop,
            )
        else:
            loop.run_until_complete(update.callback_query.answer(text="OK"))
    except Exception:  # noqa: BLE001
        pass


def handle_message(
    *, update: Any, conn: sqlite3.Connection, config: Dict[str, Any],
) -> None:
    """Free-text reply → refine_brief action. Non-reply messages ignored (V1)."""
    reply_to = getattr(update.message, "reply_to_message", None)
    if reply_to is None:
        return
    chat_id = reply_to.chat.id
    message_id = reply_to.message_id
    channel_ref = f"{chat_id}:{message_id}"
    brief_id = store.resolve_brief_id_by_channel_ref(
        conn, channel="telegram", channel_ref=channel_ref,
    )
    if brief_id is None:
        return
    expires_hours = config["refinement"]["action_expires_hours"]
    expires = _expires_at(expires_hours)
    aid = store.insert_brief_action(
        conn, brief_id=brief_id, action_type="refine_brief",
        action_params={"reply_text": update.message.text or ""},
        expires_at=expires,
    )
    store.update_action_state(
        conn, action_id=aid, state="accepted", responded_at=_utc_now_iso(),
    )


def main() -> None:
    """Start the polling loop. Called by the systemd unit."""
    from telegram.ext import (
        ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters,
    )
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.persistence.db import connect as iic_connect

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = DEFAULT_CONFIG
    token = os.environ.get("IIC_TELEGRAM_BOT_TOKEN", "")
    if not token or not config["telegram_bot"]["enabled"]:
        log.error("iic-telegram-bot disabled or token missing; exiting")
        return

    conn = iic_connect(config["iic_db_path"])

    app = ApplicationBuilder().token(token).build()

    def _allowed_chat_ids() -> set[str]:
        # str-normalize so both [123] (int) and ["123"] (str) entries match the
        # numeric chat.id. An empty set means deny-all by design (restricted).
        return {str(x) for x in config["telegram_bot"]["allowed_chat_ids"]}

    async def _on_callback(update, context):
        allowed = _allowed_chat_ids()
        chat = update.callback_query.message.chat
        if str(chat.id) not in allowed:
            return
        handle_callback(update=update, conn=conn)

    async def _on_message(update, context):
        allowed = _allowed_chat_ids()
        if str(update.message.chat.id) not in allowed:
            return
        handle_message(update=update, conn=conn, config=config)

    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

    log.info("iic-telegram-bot polling started")
    app.run_polling(allowed_updates=["callback_query", "message"])


if __name__ == "__main__":
    main()
