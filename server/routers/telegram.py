"""Test-ping a Telegram chat_id."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import notify
from ..deps import require_auth
from ..schemas import OkMessage, TelegramTestReq

router = APIRouter(prefix="/api", tags=["telegram"])


@router.post("/telegram/test", response_model=OkMessage)
def telegram_test(body: TelegramTestReq, email: str = Depends(require_auth)):
    ok, detail = notify.send_telegram(
        body.chat_id,
        f"✅ TradingAgents test ping for {email}",
        disable_notification=True,
    )
    return OkMessage(ok=ok, message=detail)
