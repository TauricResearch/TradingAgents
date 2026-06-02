"""Webhook notification dispatcher — supports Slack, Discord, and generic HTTP."""
import logging
import json
import asyncio
from typing import Any

_logger = logging.getLogger(__name__)


def _build_payload(url: str, event: str, data: dict) -> dict:
    """Shape payload for Slack/Discord or fall back to generic JSON."""
    text = _format_text(event, data)
    if "hooks.slack.com" in url:
        return {"text": text}
    if "discord.com/api/webhooks" in url:
        color = {"analysis_complete": 0x6366F1, "trade_executed": 0x10B981,
                 "alert_triggered": 0xF59E0B}.get(event, 0x6B7280)
        return {"embeds": [{"title": _event_title(event), "description": text, "color": color}]}
    return {"event": event, "data": data, "text": text}


def _event_title(event: str) -> str:
    return {"analysis_complete": "📊 Analiz Tamamlandı", "trade_executed": "💰 İşlem Gerçekleşti",
            "alert_triggered": "🔔 Fiyat Alarmı"}.get(event, event)


def _format_text(event: str, data: dict) -> str:
    if event == "analysis_complete":
        return (f"**{data.get('ticker', '?')}** — Sinyal: **{data.get('signal', '?')}**\n"
                f"Tarih: {data.get('trade_date', '')}\n{data.get('summary', '')[:300]}")
    if event == "trade_executed":
        return (f"**{data.get('ticker', '?')}** {data.get('action', '?')} işlemi\n"
                f"Miktar: {data.get('quantity', 0):.4f} @ ${data.get('price', 0):.2f}")
    if event == "alert_triggered":
        return (f"**{data.get('ticker', '?')}** alarm tetiklendi\n"
                f"Hedef: ${data.get('target_price', 0):.2f} ({data.get('condition', '')})")
    return json.dumps(data)[:500]


async def send_webhook(url: str, event: str, data: dict, retries: int = 2) -> bool:
    """POST event payload to webhook URL. Returns True on success."""
    if not url:
        return False
    try:
        import httpx
        payload = _build_payload(url, event, data)
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(retries + 1):
                try:
                    r = await client.post(url, json=payload)
                    if r.status_code < 300:
                        return True
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                except httpx.RequestError:
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
        return False
    except Exception as exc:
        _logger.debug("Webhook failed: %s", exc)
        return False


async def notify_analysis_complete(ticker: str, signal: str | None, trade_date: str,
                                   final_decision: str, settings) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "analysis_complete" not in events or not url:
        return
    await send_webhook(url, "analysis_complete", {
        "ticker": ticker, "signal": signal, "trade_date": trade_date,
        "summary": (final_decision or "")[:300],
    })


async def notify_trade_executed(ticker: str, action: str, quantity: float,
                                price: float, settings) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "trade_executed" not in events or not url:
        return
    await send_webhook(url, "trade_executed", {"ticker": ticker, "action": action,
                                                "quantity": quantity, "price": price})


async def notify_alert_triggered(ticker: str, condition: str, target_price: float,
                                 settings) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "alert_triggered" not in events or not url:
        return
    await send_webhook(url, "alert_triggered", {"ticker": ticker, "condition": condition,
                                                 "target_price": target_price})


def _parse_events(raw: str) -> list[str]:
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []
