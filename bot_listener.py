"""Long-polling bot listener — replies to /start, /chatid, /help with the
caller's chat_id and a deep link to the webui.

Lets users self-serve their chat_id from the same bot that delivers reports,
so they don't need to involve @userinfobot.

Runs as a systemd service (``trading-bot-listener.service``) so it's always
ready to greet newcomers.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
WEBUI = os.getenv("WEBUI_PUBLIC_URL", "http://localhost:8501")

LONG_POLL_TIMEOUT = 30      # seconds Telegram holds the connection
RECV_TIMEOUT = 40            # client-side socket timeout (slightly > server)
RETRY_DELAY = 5


def _log(msg: str) -> None:
    print(f"{time.strftime('%F %T')} {msg}", flush=True)


def _reply(chat_id: int | str, text: str) -> None:
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={
                "chat_id": chat_id, "text": text,
                "parse_mode": "Markdown", "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if r.status_code != 200:
            _log(f"sendMessage chat_id={chat_id} HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        _log(f"sendMessage chat_id={chat_id} failed: {type(e).__name__}: {e}")


def _is_chinese(name: str) -> bool:
    return any("一" <= c <= "鿿" for c in name)


def _build_welcome(chat_id: int, first: str) -> str:
    if _is_chinese(first):
        return (
            f"👋 你好 {first}！\n\n"
            f"你的 Telegram chat_id 是：\n"
            f"`{chat_id}`\n\n"
            f"把这串数字粘到 [TradingAgents]({WEBUI}) 左侧 sidebar 的 "
            f"**📅 每日定时分析** 里保存即可。\n\n"
            f"配置完成后每天 07:00 北京时间会自动推送你设的股票分析到这里。"
        )
    return (
        f"👋 Hi {first}!\n\n"
        f"Your Telegram chat_id is:\n"
        f"`{chat_id}`\n\n"
        f"Paste it into the **📅 Daily schedule** panel in [TradingAgents]({WEBUI}) "
        f"and hit Save.\n\n"
        f"Once configured, your daily analysis will arrive here at 07:00 Asia/Shanghai."
    )


def main() -> int:
    if not TOKEN:
        _log("TELEGRAM_BOT_TOKEN is unset — refusing to start.")
        return 2

    _log(f"bot listener starting; webui={WEBUI}")
    offset = 0
    while True:
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": LONG_POLL_TIMEOUT,
                        "allowed_updates": '["message"]'},
                timeout=RECV_TIMEOUT,
            )
            if r.status_code != 200:
                _log(f"getUpdates HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(RETRY_DELAY)
                continue
            data = r.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                first = chat.get("first_name", "") or chat.get("title", "") or ""
                text = (msg.get("text") or "").strip()
                if not chat_id:
                    continue
                # Reply to any text message — this bot's only job is handing
                # out chat_id, so don't gate on a keyword allowlist.
                if text:
                    _log(f"reply chat_id={chat_id} first_name={first!r} text={text[:60]!r}")
                    _reply(chat_id, _build_welcome(chat_id, first))
        except requests.RequestException as e:
            _log(f"poll error: {type(e).__name__}: {e}")
            time.sleep(RETRY_DELAY)
        except KeyboardInterrupt:
            _log("interrupted; exiting.")
            return 0
        except Exception as e:
            _log(f"unexpected: {type(e).__name__}: {e}")
            time.sleep(RETRY_DELAY)


if __name__ == "__main__":
    sys.exit(main())
