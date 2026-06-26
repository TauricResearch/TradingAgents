"""Interactive Telegram command handlers for the dashboard indicators.

Provides a tiny Application that registers `/fetch`, `/status`, `/ping`, and `/help`
commands which run indicator checks and reply with formatted summaries to the
requesting chat.

The handler restricts usage to the configured `TELEGRAM_CHAT_ID` by default
to avoid public abuse; you can remove this check if you want the bot to be
publicly triggerable.
"""

from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from web.server.notifier import (
    _require_telegram,
    build_results_message,
)

_require_telegram()

logger = logging.getLogger(__name__)


def create_telegram_application(token: str) -> Application:
    """Return a configured `Application` with command handlers registered.

    The returned Application is not started; the caller should call
    `await app.initialize()` and `await app.start()` (or use `app.run_polling()`)
    depending on the deployment preferences.
    """
    from web.server import indicators

    app = Application.builder().token(token).build()

    async def fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None:
            logger.warning("/fetch received without an effective chat")
            return

        chat_id = update.effective_chat.id
        logger.info("/fetch command received from chat_id=%s", chat_id)

        allowed = os.getenv("TRADINGAGENTS_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        if allowed is not None and chat_id != int(allowed):
            logger.warning("Unauthorized /fetch attempt from %s (allowed=%s)", chat_id, allowed)
            await context.bot.send_message(chat_id=chat_id, text="Unauthorized.")
            return

        await context.bot.send_message(chat_id=chat_id, text="Fetching indicator data, please wait...")

        try:
            from web.server.notifier import _results_from_check_response

            checks = indicators.run_checks()
            results = _results_from_check_response(checks)
            text = build_results_message(results)
        except Exception:
            logger.exception("Manual /fetch run failed for chat_id=%s", chat_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text="Fetch failed. Please check the bot logs and try again.",
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None:
            logger.warning("/ping received without an effective chat")
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text="pong")

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None:
            logger.warning("/help received without an effective chat")
            return
        lines = [
            "<b>Available commands</b>",
            "/fetch - run indicator checks now and return the summary",
            "/ping - confirm the bot is reachable",
        ]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

    app.add_handler(CommandHandler("fetch", fetch_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("help", help_command))
    logger.info("Registered handlers: /fetch, /ping, /help")
    return app
