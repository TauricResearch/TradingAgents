"""Telegram delivery for the scheduled TradingAgents runner.

Sends the Portfolio Manager's daily decision to a configured chat. Two
payloads per report:

1. A short Markdown message with Rating / Price Target / Horizon plus a
   preview of the executive summary. Useful as a glanceable alert.
2. The full ``decision.md`` as a PDF document (or, if PDF conversion
   failed, as a ``.md`` document — Telegram renders neither, but a tap
   downloads it).

The bot token and chat id are read from environment variables; if either is
missing the module short-circuits to a no-op so the headless runner can
still complete the analysis portion of the pipeline.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from tradingagents.reports.exporter import DecisionSummary

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"

DEFAULT_TIMEOUT = 30  # seconds, generous because sendDocument can be slow


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> TelegramConfig | None:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not bot_token or not chat_id:
            return None
        return cls(bot_token=bot_token, chat_id=chat_id)


def _post(config: TelegramConfig, method: str, **fields: Any) -> dict[str, Any]:
    """POST to the Telegram Bot API and return the parsed JSON envelope.

    Raises ``TelegramError`` on any non-200 response so callers can decide
    whether to retry or surface the failure to the user.
    """
    url = f"{API_BASE}/bot{config.bot_token}/{method}"
    response = requests.post(url, timeout=DEFAULT_TIMEOUT, **fields)
    payload: dict[str, Any]
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise TelegramError(f"Telegram returned non-JSON response: {response.text[:200]}") from exc
    if not payload.get("ok", False):
        raise TelegramError(
            f"Telegram {method} failed: status={response.status_code} body={payload}"
        )
    return payload


class TelegramError(RuntimeError):
    """Raised when the Telegram API returns a non-ok response."""


def send_report(
    ticker: str,
    summary: DecisionSummary,
    *,
    pdf_path: Path | None = None,
    markdown_path: Path | None = None,
    config: TelegramConfig | None = None,
) -> bool:
    """Send the short message and the full document to the configured chat.

    Returns ``True`` if both calls succeeded. Returns ``False`` early if
    Telegram is not configured (logs at info level so the scheduled run
    can still be diagnosed from ``run_daily.out.log``). Raises
    ``TelegramError`` only on hard transport / API failures — by design
    the caller is expected to catch and continue with the next ticker
    rather than abort the whole scheduled run.
    """
    cfg = config or TelegramConfig.from_env()
    if cfg is None:
        logger.info(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; skipping delivery for %s",
            ticker,
        )
        return False

    short = _render_short_message(ticker, summary)
    _post(
        cfg,
        "sendMessage",
        data={"chat_id": cfg.chat_id, "text": short, "parse_mode": "MarkdownV2"},
    )
    logger.info("Telegram short message sent for %s", ticker)

    document = pdf_path if pdf_path and pdf_path.exists() else markdown_path
    if document is None or not Path(document).exists():
        logger.warning("No document to send for %s (no pdf or markdown path)", ticker)
        return False

    caption = _build_caption(ticker, summary)
    with open(document, "rb") as fh:
        _post(
            cfg,
            "sendDocument",
            data={"chat_id": cfg.chat_id, "caption": caption[:1024]},
            files={"document": (document.name, fh)},
        )
    suffix = Path(document).suffix
    logger.info("Telegram document sent for %s (%s)", ticker, suffix)
    return True


def _render_short_message(ticker: str, summary: DecisionSummary) -> str:
    """Compose the short message with all user-data fields MarkdownV2-escaped.

    The template's intentional ``*bold*`` markers stay unescaped; only
    LLM-emitted strings (rating, price target, time horizon, thesis) get
    the escape pass. Without this, a tick like ``BTC-USD`` and a time
    horizon like ``3-6 mesi`` would crash the Bot API with
    "can't parse entities" because ``-`` and ``.`` are reserved in
    MarkdownV2.
    """
    parts: list[str] = [f"\U0001f4ca *{escape_markdown_v2(ticker)}* — TradingAgents report"]
    if summary.rating:
        parts.append(f"Rating: *{escape_markdown_v2(summary.rating)}*")
    if summary.price_target is not None:
        parts.append(f"Price target: `{summary.price_target:g}`")
    if summary.time_horizon:
        parts.append(f"Horizon: {escape_markdown_v2(summary.time_horizon)}")
    if summary.executive_summary:
        preview = _truncate(summary.executive_summary, 240)
        parts.append(f"\n{escape_markdown_v2(preview)}")
    return "\n".join(parts)


def _truncate(text: str, limit: int) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def _build_caption(ticker: str, summary: DecisionSummary) -> str:
    """Build the document caption shown above the PDF/MD attachment.

    Captions are sent as plain text (no ``parse_mode``) so the escape
    pass is unnecessary here.
    """
    parts: list[str] = [f"{ticker} — Portfolio Manager decision"]
    if summary.rating:
        parts.append(f"Rating: {summary.rating}")
    if summary.price_target is not None:
        parts.append(f"Price target: {summary.price_target:g}")
    if summary.time_horizon:
        parts.append(f"Horizon: {summary.time_horizon}")
    return "\n".join(parts)


# Telegram MarkdownV2 requires every one of these characters to be escaped
# with a leading backslash, otherwise the API returns a 400 with
# "can't parse entities". See https://core.telegram.org/bots/api#markdownv2-style
_MD2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(text: str) -> str:
    """Escape every MarkdownV2-reserved character in ``text``.

    Used on user-supplied fields (executive summary, thesis, time horizon)
    before they're interpolated into a ``sendMessage`` body. We don't
    escape the deliberate ``*bold*`` markup in the template itself — that
    markup is added by ``_render_short_message`` after escaping runs.
    """
    return "".join("\\" + ch if ch in _MD2_SPECIAL else ch for ch in text)
