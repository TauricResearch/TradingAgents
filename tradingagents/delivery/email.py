"""Email delivery channel via SMTP (Gmail default).

Reads credentials from env: IIC_SMTP_USER, IIC_SMTP_APP_PASSWORD.
If smtp.enabled is False, the send is recorded as skipped (no retry).
"""

from __future__ import annotations

import os
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any, Dict

from tradingagents.delivery.base import DeliveryChannel
from tradingagents.persistence import store


class EmailOutbound(DeliveryChannel):
    channel_name = "email"

    def send(self, *, brief: Dict[str, Any], mode: str, body: str) -> int:
        if not self._config["smtp"].get("enabled", False):
            return store.insert_delivery(
                self._conn, brief_id=brief["brief_id"], channel=self.channel_name,
                status="skipped", sent_ts=None, channel_ref=None,
                skip_reason="smtp_disabled",
            )
        return super().send(brief=brief, mode=mode, body=body)

    def _send_impl(self, brief: Dict[str, Any], mode: str, body: str) -> tuple:
        smtp_cfg = self._config["smtp"]
        user = os.environ.get("IIC_SMTP_USER", "")
        pw = os.environ.get("IIC_SMTP_APP_PASSWORD", "")
        if not user or not pw:
            raise RuntimeError("IIC_SMTP_USER / IIC_SMTP_APP_PASSWORD not set")

        msg = EmailMessage()
        message_id = f"<{uuid.uuid4().hex}@iic-forge>"
        msg["Message-ID"] = message_id
        msg["From"] = smtp_cfg["from_addr"]
        msg["To"] = ", ".join(smtp_cfg["to_addrs"])
        msg["Subject"] = f"[IIC] {mode}: {brief.get('scope', '')}"

        msg.set_content("This message requires an HTML-capable viewer.")
        msg.add_alternative(body, subtype="html")

        smtp = smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=30)
        try:
            smtp.starttls()
            smtp.login(user, pw)
            smtp.send_message(msg)
        finally:
            smtp.quit()

        return (message_id, None)
