"""Telegram notification helper with console fallback."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class TelegramNotifier:
    """Send signal summaries to Telegram when configured."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None, dry_run: bool = True):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.dry_run = dry_run or not (self.token and self.chat_id)

    def send_signal(self, signal: Dict) -> Dict:
        text = self._format_signal(signal)
        if self.dry_run:
            print(text)
            return {"status": "dry_run", "message": text}
        return self.send_text(text)

    def send_text(self, text: str, **kwargs: Any) -> Dict[str, Any]:
        """Send a plain Telegram message and return the Telegram API response."""
        if self.dry_run:
            print(text)
            return {"status": "dry_run", "message": text}
        payload: Dict[str, Any] = {"chat_id": self.chat_id, "text": text, "disable_notification": False}
        payload.update(kwargs)
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json=payload,
            timeout=(5, 15),
        )
        response.raise_for_status()
        return {"status": "sent", "response": response.json()}

    def send_approval_request(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """Send a trade proposal with inline approve/reject buttons."""
        text = self._format_approval(approval)
        approval_id = str(approval.get("id"))
        if self.dry_run:
            print(text)
            return {"status": "dry_run", "message": text}
        return self.send_text(
            text,
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"approve:{approval_id}"},
                        {"text": "❌ Reject", "callback_data": f"reject:{approval_id}"},
                    ]
                ]
            },
        )

    def send_order_opened(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Send a notification when a paper order is actually opened."""
        text = self._format_order_opened(order)
        return self.send_text(text)

    def send_trade_closed(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Send the final WIN/LOSS result for a closed paper trade."""
        text = self._format_trade_closed(trade)
        if self.dry_run:
            print(text)
            return {"status": "dry_run", "message": text}
        return self.send_text(text)

    def get_updates(self, offset: Optional[int] = None, timeout: int = 0) -> Dict[str, Any]:
        """Poll Telegram updates. Used by the local dashboard scheduler."""
        if self.dry_run:
            return {"ok": True, "result": []}
        params: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["callback_query"]}
        if offset is not None:
            params["offset"] = offset
        # Use (connect_timeout, read_timeout) tuple: 5s to connect, then allow Telegram API time to respond.
        # For timeout=0 (no long-poll), read should complete quickly; still allow 8s for slow networks.
        request_timeout = (5, max(8, timeout + 3))
        response = requests.get(f"https://api.telegram.org/bot{self.token}/getUpdates", params=params, timeout=request_timeout)
        response.raise_for_status()
        return response.json()

    def answer_callback(self, callback_query_id: str, text: str) -> Dict[str, Any]:
        if self.dry_run:
            return {"status": "dry_run"}
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text, "show_alert": False},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _short(text: Any, limit: int = 180) -> str:
        value = " ".join(str(text or "").split())
        return value if len(value) <= limit else value[: limit - 1] + "…"

    @staticmethod
    def _fmt(value: Any, digits: int = 4) -> str:
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _reward_risk(signal: Dict[str, Any]) -> Optional[float]:
        try:
            entry = float(signal.get("entry"))
            stop_loss = float(signal.get("stop_loss"))
            take_profit = float(signal.get("take_profit"))
        except (TypeError, ValueError):
            return None
        risk = entry - stop_loss
        reward = take_profit - entry
        if risk <= 0 or reward <= 0:
            return None
        return reward / risk

    @staticmethod
    def _format_signal(signal: Dict) -> str:
        return (
            f"Crypto signal: {signal.get('coin')} {signal.get('signal')}\n"
            f"Strategy: {signal.get('strategy')} | Confidence: {signal.get('confidence')}\n"
            f"Entry: {signal.get('entry')} | SL: {signal.get('stop_loss')} | TP: {signal.get('take_profit')}\n"
            f"Reason: {signal.get('reasoning')}\n"
            "Reply/confirm manually before execution."
        )

    @staticmethod
    def _format_approval(approval: Dict[str, Any]) -> str:
        signal = approval.get("signal") or {}
        decision = approval.get("llm_decision") or {}
        sizing = approval.get("sizing") or {}
        stats = sizing.get("stats") or {}
        win_rate = stats.get("win_rate")
        win_text = "chưa đủ mẫu" if win_rate is None else f"{float(win_rate) * 100:.1f}% ({stats.get('wins', 0)}W/{stats.get('losses', 0)}L)"
        rr = TelegramNotifier._reward_risk(signal)
        rr_text = f"RR {rr:.2f}" if rr is not None else "RR —"
        llm_action = decision.get("llm_original_action") or decision.get("action") or "—"
        review_flag = " · cần duyệt vì LLM không đồng thuận" if decision.get("human_review_required") else ""
        return (
            f"📌 DUYỆT PAPER #{approval.get('id')}\n"
            f"{signal.get('symbol')} {signal.get('action')} · {signal.get('strategy')} · {signal.get('market_regime')}\n"
            f"Entry {TelegramNotifier._fmt(signal.get('entry'))} | SL {TelegramNotifier._fmt(signal.get('stop_loss'))} | TP {TelegramNotifier._fmt(signal.get('take_profit'))} | {rr_text}\n"
            f"RSI {TelegramNotifier._fmt(signal.get('rsi'), 1)} · Str {TelegramNotifier._fmt(signal.get('strength'), 3)} · Vol {TelegramNotifier._fmt(signal.get('volume_spike'), 2)}\n"
            f"LLM: {llm_action} · conf {TelegramNotifier._fmt(decision.get('confidence'), 2)}{review_flag}\n"
            f"Size: {TelegramNotifier._fmt(sizing.get('notional_usdt'), 2)} USDT ({float(sizing.get('allocation_pct') or 0) * 100:.1f}% cash) · WR {win_text}\n"
            f"Lý do: {TelegramNotifier._short(decision.get('reasoning') or signal.get('reason'), 220)}\n\n"
            "Approve = mở PAPER · Reject = bỏ qua"
        )

    @staticmethod
    def _format_order_opened(order: Dict[str, Any]) -> str:
        position = order.get("position") or {}
        signal = position.get("signal") or {}
        decision = position.get("llm_decision") or {}
        if order.get("status") != "opened" or not position:
            return f"⚠️ PAPER order không mở được: {order.get('status')}\nReason: {order.get('reason')}"
        rr = TelegramNotifier._reward_risk(signal)
        rr_text = f"RR {rr:.2f}" if rr is not None else "RR —"
        auto = "auto" if order.get("auto_approved") or decision.get("auto_approved") else "manual"
        return (
            f"🟢 OPEN PAPER · {auto}\n"
            f"{position.get('symbol')} {position.get('side')} · {position.get('strategy')}\n"
            f"Entry {TelegramNotifier._fmt(position.get('entry_price'))} | SL {TelegramNotifier._fmt(position.get('stop_loss'))} | TP {TelegramNotifier._fmt(position.get('take_profit'))} | {rr_text}\n"
            f"Size {TelegramNotifier._fmt(position.get('notional'), 2)} USDT · Qty {TelegramNotifier._fmt(position.get('quantity'), 6)} · conf {TelegramNotifier._fmt(position.get('confidence'), 2)}\n"
            f"RSI {TelegramNotifier._fmt(signal.get('rsi'), 1)} · Str {TelegramNotifier._fmt(signal.get('strength'), 3)} · Vol {TelegramNotifier._fmt(signal.get('volume_spike'), 2)}\n"
            f"Lý do: {TelegramNotifier._short(decision.get('reasoning') or signal.get('reason'), 180)}\n"
            f"Opened: {position.get('opened_at')}"
        )

    @staticmethod
    def _format_trade_closed(trade: Dict[str, Any]) -> str:
        result = str(trade.get("result") or "").upper()
        icon = "✅" if result == "WIN" else "❌" if result == "LOSS" else "➖"
        pnl_usdt = float(trade.get("pnl_usdt") or trade.get("pnl_amount") or 0.0)
        pnl_pct = float(trade.get("pnl_pct") or trade.get("pnl") or 0.0)
        return (
            f"{icon} CLOSE PAPER · {result or 'FLAT'}\n"
            f"{trade.get('symbol') or trade.get('coin')} · {trade.get('strategy') or '—'} · {trade.get('exit_reason')}\n"
            f"Entry {TelegramNotifier._fmt(trade.get('entry_price') or trade.get('entry'))} → Exit {TelegramNotifier._fmt(trade.get('exit_price') or trade.get('exit'))}\n"
            f"PnL {pnl_usdt:+.4f} USDT ({pnl_pct:+.2f}%) · Size {TelegramNotifier._fmt(trade.get('notional'), 2)} USDT\n"
            f"Opened: {trade.get('opened_at')}\nClosed: {trade.get('closed_at')}"
        )