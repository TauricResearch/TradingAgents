"""Where fired alerts go besides the in-app inbox: Telegram, a webhook, email.

Every channel is off unless its environment variables are set, and they are the
only way to set one up: nothing is read from a file the app writes, and nothing
the API returns or the app logs carries a value from them. The page sees only
whether each channel is configured.

    Telegram  TRADINGAGENTS_ALERT_TELEGRAM_TOKEN, TRADINGAGENTS_ALERT_TELEGRAM_CHAT_ID
    Webhook   TRADINGAGENTS_ALERT_WEBHOOK_URL (a JSON POST with ``text`` and ``content``,
              so Slack and Discord incoming webhooks take it as it is)
    Email     TRADINGAGENTS_ALERT_SMTP_HOST, _SMTP_PORT (587, STARTTLS; 465 for SSL),
              _SMTP_USER, _SMTP_PASSWORD, _SMTP_TO, and optionally _SMTP_FROM

A delivery that fails is recorded on its inbox item with the reason, with every
configured value masked out of it, and never stops the evaluation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage

log = logging.getLogger(__name__)

PREFIX = "TRADINGAGENTS_ALERT_"
CHANNELS = {
    "telegram": {"label": "Telegram", "required": ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"), "optional": ()},
    "webhook": {"label": "Webhook", "required": ("WEBHOOK_URL",), "optional": ()},
    "email": {"label": "Email (SMTP)", "required": ("SMTP_HOST", "SMTP_TO"),
              "optional": ("SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")},
}
TIMEOUT = 15
_TOKEN_IN_URL = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


class DeliveryError(Exception):
    """A channel that could not deliver; the message has no secret in it."""


def _env(name: str) -> str:
    return (os.environ.get(PREFIX + name) or "").strip()


def configured(channel: str) -> bool:
    spec = CHANNELS[channel]
    return all(_env(n) for n in spec["required"])


def status() -> dict:
    """Each channel and whether it is configured; never a value."""
    return {name: {"label": spec["label"], "configured": configured(name),
                   "variables": [PREFIX + n for n in (*spec["required"], *spec["optional"])]}
            for name, spec in CHANNELS.items()}


def scrub(text: str) -> str:
    """``text`` with every configured channel value masked."""
    out = str(text)
    for spec in CHANNELS.values():
        for name in (*spec["required"], *spec["optional"]):
            value = _env(name)
            if len(value) >= 3 and name != "SMTP_PORT":
                out = out.replace(value, "***")
                if "%" not in value:
                    out = out.replace(urllib.parse.quote(value, safe=""), "***")
    return _TOKEN_IN_URL.sub("bot***", out)


def message_text(event: dict) -> str:
    lines = [f"🔔 {event['title']}"]
    if event.get("body"):
        lines.append(event["body"])
    if event.get("data_date"):
        lines.append(f"Data as of {event['data_date']}.")
    lines.append(f"Alert: {event.get('alert_name') or ''}")
    return "\n".join(lines)


def _post(url: str, data: bytes, content_type: str) -> None:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": content_type,
                                                          "User-Agent": "TradingAgents alerts"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:  # noqa: S310 — the user's own configured URL
        if res.status >= 300:
            raise DeliveryError(f"HTTP {res.status}")


def _telegram(event: dict) -> None:
    url = f"https://api.telegram.org/bot{_env('TELEGRAM_TOKEN')}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": _env("TELEGRAM_CHAT_ID"), "text": message_text(event)[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    _post(url, body, "application/x-www-form-urlencoded")


def _webhook(event: dict) -> None:
    url = _env("WEBHOOK_URL")
    if not url.lower().startswith(("https://", "http://")):
        raise DeliveryError("the webhook URL must start with https:// or http://")
    text = message_text(event)
    payload = {"text": text, "content": text[:2000], "title": event["title"], "body": event.get("body", ""),
               "alert": event.get("alert_name"), "kind": event.get("kind"), "symbol": event.get("symbol"),
               "dataDate": event.get("data_date"), "firedAt": event.get("fired_at"),
               "detail": event.get("detail") or {}}
    _post(url, json.dumps(payload, default=str).encode(), "application/json")


def _email(event: dict) -> None:
    host, to = _env("SMTP_HOST"), _env("SMTP_TO")
    try:
        port = int(_env("SMTP_PORT") or 587)
    except ValueError:
        raise DeliveryError("TRADINGAGENTS_ALERT_SMTP_PORT is not a number") from None
    user, password = _env("SMTP_USER"), _env("SMTP_PASSWORD")
    msg = EmailMessage()
    msg["Subject"] = f"[TradingAgents] {event['title']}"[:200]
    msg["From"] = _env("SMTP_FROM") or user or "tradingagents@localhost"
    msg["To"] = to
    msg.set_content(message_text(event))
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=TIMEOUT)
    with server:
        if port != 465:
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls(context=context)
                server.ehlo()
        if user:
            server.login(user, password)
        server.send_message(msg)


SENDERS = {"telegram": _telegram, "webhook": _webhook, "email": _email}


def send(channel: str, event: dict) -> None:
    """Deliver one event through one channel, or a DeliveryError with a scrubbed reason."""
    if channel not in CHANNELS:
        raise DeliveryError(f"no channel called {channel!r}")
    if not configured(channel):
        raise DeliveryError(f"{CHANNELS[channel]['label']} is not configured")
    try:
        SENDERS[channel](event)
    except DeliveryError as exc:
        raise DeliveryError(scrub(str(exc))) from None
    except Exception as exc:  # noqa: BLE001 — any network or protocol failure is the channel's
        raise DeliveryError(scrub(f"{type(exc).__name__}: {exc}")) from None


def deliver(event: dict) -> dict:
    """Send ``event`` through every configured channel. ``{channel: {"ok", "error", "at"}}``;
    never raises."""
    out = {}
    for channel in CHANNELS:
        if not configured(channel):
            continue
        at = datetime.now().isoformat(timespec="seconds")
        try:
            send(channel, event)
            out[channel] = {"ok": True, "error": None, "at": at}
        except DeliveryError as exc:
            log.warning("Alert delivery through %s failed: %s", channel, exc)
            out[channel] = {"ok": False, "error": str(exc), "at": at}
        except Exception as exc:  # noqa: BLE001 — evaluation must go on whatever a channel does
            reason = scrub(f"{type(exc).__name__}: {exc}")
            log.warning("Alert delivery through %s failed: %s", channel, reason)
            out[channel] = {"ok": False, "error": reason, "at": at}
    return out


def send_test(channel: str) -> dict:
    """A test message through one channel: ``{"ok": True}`` or ``{"ok": False, "error"}``."""
    now = datetime.now().isoformat(timespec="seconds")
    event = {"title": "Test alert from TradingAgents", "body": "If you can read this, alerts reach you here.",
             "alert_name": "Channel test", "kind": "test", "fired_at": now, "data_date": None, "detail": {}}
    try:
        send(channel, event)
        return {"ok": True, "error": None, "at": now}
    except DeliveryError as exc:
        return {"ok": False, "error": str(exc), "at": now}
