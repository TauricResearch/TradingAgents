"""Hermes tool: Telegram approval cards and notifications.

All HITL interaction flows through Telegram.  The bot only responds to the
user ID in TELEGRAM_ALLOWED_USER_ID (an integer string), rejecting all other
sources.

Env vars consumed:
    TELEGRAM_BOT_TOKEN         Bot token from @BotFather (required)
    TELEGRAM_ALLOWED_USER_ID   Telegram user ID to accept messages from (required)

Approval flow:
    send_approval_card() sends an inline-button card and blocks via
    threading.Event until the user taps ✅/❌ or the timeout expires.
    The "📊 More Info" button sends an expanded detail message and resets
    the wait so the card remains live.

Dependency: python-telegram-bot >= 20 (async, PTB v20+)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECS = 30 * 60  # 30 minutes

# Level → prefix used in send_notification
_LEVEL_PREFIX = {
    "info":    "ℹ️",
    "warning": "⚠️",
    "alert":   "🚨",
}


# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------

def _bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise EnvironmentError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it via fly secrets set TELEGRAM_BOT_TOKEN=..."
        )
    return token


def _allowed_user_id() -> int:
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not raw:
        raise EnvironmentError(
            "TELEGRAM_ALLOWED_USER_ID is not set. "
            "Set it via fly secrets set TELEGRAM_ALLOWED_USER_ID=<your_id>"
        )
    try:
        return int(raw)
    except ValueError:
        raise EnvironmentError(
            f"TELEGRAM_ALLOWED_USER_ID must be an integer user ID, got: {raw!r}"
        )


# ---------------------------------------------------------------------------
# Card text helpers
# ---------------------------------------------------------------------------

def _format_approval_card(card: dict[str, Any]) -> str:
    """Format the trade setup card text from a trade_card dict.

    Expected card keys (all optional with fallback):
        ticker, direction, entry, stop, risk_pct, shares,
        risk_dollars, risk_pct_account, equity,
        win_rate, n_trades, regime, top_signal
    """
    ticker     = card.get("ticker", "?")
    direction  = card.get("direction", card.get("signal", "?")).upper()
    entry      = card.get("entry",      card.get("entry_price",  "?"))
    stop       = card.get("stop",       card.get("stop_loss",    "?"))
    shares     = card.get("shares",     "?")
    risk_pct   = card.get("risk_pct",   "?")
    risk_dollars     = card.get("risk_dollars",     "?")
    risk_pct_account = card.get("risk_pct_account", "?")
    equity           = card.get("equity",            "?")
    win_rate   = card.get("win_rate",   "?")
    n_trades   = card.get("n_trades",   "?")
    regime     = card.get("regime",     "unknown")
    top_signal = card.get("top_signal", card.get("scenario", "—"))

    # Format numeric fields neatly when they're actual numbers.
    def _fmt_price(v: Any) -> str:
        return f"{v:.2f}" if isinstance(v, float) else str(v)

    def _fmt_int(v: Any) -> str:
        return f"{int(v):,}" if isinstance(v, (int, float)) else str(v)

    entry_str  = _fmt_price(entry)
    stop_str   = _fmt_price(stop)
    equity_str = _fmt_int(equity)

    risk_pct_str = (
        f"{risk_pct:.1f}" if isinstance(risk_pct, float) else str(risk_pct)
    )

    lines = [
        f"📊 TRADE SETUP — {ticker}",
        "",
        f"Direction:  {direction}",
        f"Entry:      ${entry_str}",
        f"Stop:       ${stop_str}  (-{risk_pct_str}%)",
        f"Shares:     {shares}",
        f"Risk:       ${risk_dollars}  ({risk_pct_account}% of ${equity_str})",
        "",
        f"Historical: {win_rate}% win rate ({n_trades} similar trades)",
        f"Regime:     {regime}",
        f"Top signal: {top_signal}",
    ]
    return "\n".join(lines)


def _format_more_info(card: dict[str, Any]) -> str:
    """Format the expanded detail message for the 📊 More Info button."""
    ticker = card.get("ticker", "?")
    lines = [f"📊 MORE INFO — {ticker}", ""]

    # Analyst signals
    analysts = card.get("analysts_fired", card.get("analysts", []))
    if analysts:
        lines.append("Analysts fired: " + ", ".join(analysts))

    # Full scenario
    scenario = card.get("scenario", "")
    if scenario:
        lines.extend(["", "Scenario:", scenario])

    # Similar past trades
    similar = card.get("similar_trades", [])
    if similar:
        lines.extend(["", "Top similar trades:"])
        for i, t in enumerate(similar[:3], 1):
            outcome = t.get("outcome", "?")
            date    = t.get("date", "?")
            pnl     = t.get("pnl_pct", "?")
            lines.append(f"  {i}. {date}  {outcome}  ({pnl}% P&L)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Blocking approval card (sync wrapper over PTB async)
# ---------------------------------------------------------------------------

def send_approval_card(
    trade_card: dict[str, Any],
    timeout_secs: int = _DEFAULT_TIMEOUT_SECS,
) -> str:
    """Send an approval card to Telegram and block until the user responds.

    Args:
        trade_card:   Dict with trade setup fields (see _format_approval_card).
        timeout_secs: Seconds to wait before auto-rejecting (default 30 min).

    Returns:
        "approved", "rejected", or "timeout".
    """
    try:
        _bot_token()
        _allowed_user_id()
    except EnvironmentError as exc:
        logger.error("send_approval_card: env var error: %s", exc)
        return "timeout"

    # Use a threading.Event to bridge the async PTB world into a sync return.
    decision_event: threading.Event = threading.Event()
    decision_result: list[str] = ["timeout"]   # mutable container for closure

    def _run_bot() -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_approval_flow(
                trade_card, timeout_secs, decision_event, decision_result
            ))
        finally:
            loop.close()

    bot_thread = threading.Thread(target=_run_bot, daemon=True)
    bot_thread.start()

    # Block the calling thread until the bot sets the event or timeout fires.
    decision_event.wait(timeout=timeout_secs + 10)   # +10s grace for async cleanup

    result = decision_result[0]
    logger.info("send_approval_card: result=%s for ticker=%s", result, trade_card.get("ticker"))
    return result


async def _async_approval_flow(
    trade_card: dict[str, Any],
    timeout_secs: int,
    decision_event: threading.Event,
    decision_result: list[str],
) -> None:
    """Async PTB flow: send card, handle callbacks, set result."""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        ContextTypes,
    )
    import asyncio

    token      = _bot_token()
    allowed_id = _allowed_user_id()
    card_text  = _format_approval_card(trade_card)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve",    callback_data="approved"),
            InlineKeyboardButton("❌ Reject",     callback_data="rejected"),
            InlineKeyboardButton("📊 More Info",  callback_data="more_info"),
        ]
    ])

    # We need the message_id to edit / delete after response.
    sent_message_id: list[int] = []
    more_info_sent:  list[bool] = [False]

    app = Application.builder().token(token).build()

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query.from_user.id != allowed_id:
            await query.answer("Unauthorised.")
            return

        await query.answer()
        data = query.data

        if data == "more_info" and not more_info_sent[0]:
            more_info_sent[0] = True
            detail = _format_more_info(trade_card)
            await context.bot.send_message(chat_id=allowed_id, text=detail)
            return   # Leave the card live; wait for Approve/Reject

        if data in ("approved", "rejected"):
            decision_result[0] = data
            # Edit message to show the outcome.
            label = "APPROVED ✅" if data == "approved" else "REJECTED ❌"
            await query.edit_message_text(text=f"{card_text}\n\n— {label}")
            decision_event.set()
            # Stop the app so the thread can exit.
            await app.stop()

    app.add_handler(CallbackQueryHandler(callback_handler))

    await app.initialize()
    await app.start()

    # Send the approval card.
    msg = await app.bot.send_message(
        chat_id=allowed_id,
        text=card_text,
        reply_markup=keyboard,
    )
    sent_message_id.append(msg.message_id)

    # Wait until timeout or until decision_event is set by the callback.
    deadline = time.monotonic() + timeout_secs
    while not decision_event.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Timeout — edit card to say so.
            try:
                await app.bot.edit_message_text(
                    chat_id=allowed_id,
                    message_id=sent_message_id[0],
                    text=f"{card_text}\n\n— TIMEOUT (auto-rejected)",
                )
            except Exception:
                pass
            decision_result[0] = "timeout"
            decision_event.set()
            break
        await asyncio.sleep(min(5.0, remaining))

    await app.stop()
    await app.shutdown()


# ---------------------------------------------------------------------------
# Notification (fire-and-forget)
# ---------------------------------------------------------------------------

def send_notification(message: str, level: str = "info") -> bool:
    """Send a plain text notification via Telegram.

    Args:
        message: Text to send.
        level:   "info", "warning", or "alert" (controls prefix emoji).

    Returns:
        True on success, False on failure.
    """
    if not message or not message.strip():
        return False

    prefix = _LEVEL_PREFIX.get(level.lower(), _LEVEL_PREFIX["info"])
    text = f"{prefix} {message.strip()}"

    try:
        import asyncio
        from telegram import Bot

        token      = _bot_token()
        allowed_id = _allowed_user_id()

        async def _send() -> None:
            async with Bot(token) as bot:
                await bot.send_message(chat_id=allowed_id, text=text)

        asyncio.run(_send())
        logger.info("send_notification: sent level=%s", level)
        return True

    except EnvironmentError as exc:
        logger.error("send_notification: env var error: %s", exc)
        return False
    except Exception as exc:
        logger.exception("send_notification: failed to send message")
        return False
