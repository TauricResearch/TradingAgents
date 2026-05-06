"""Daily scheduled-analysis runner.

Triggered by ``trading-scheduler.timer``. Walks every per-user
``preferences.json`` and, for each user that has opted in, runs the same
``worker.py`` analysis pipeline that the webui uses, then pushes a formatted
summary to the user's Telegram chat.

Usage:
    python scheduler.py                  # fire for everyone (the systemd path)
    python scheduler.py --dry-run        # preview only, no worker, no Telegram
    python scheduler.py --user <slug>    # run just one user (handy for testing)

Logs to stdout/stderr → systemd journal.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

import notify
import ticker_resolver
import user_prefs

from tradingagents.dataflows.range_stats import (
    RangeStatsUnavailable,
    compute_range_stats,
    format_range_stats_telegram,
)

PYTHON_BIN = os.getenv("TRADINGAGENTS_PYTHON_BIN", sys.executable)
WORKER_PATH = str(_ROOT / "worker.py")
LOCK_PATH = "/tmp/trading-scheduler.lock"
WEBUI_BASE_URL = os.getenv("WEBUI_PUBLIC_URL", "http://localhost:8501")


def _log(msg: str) -> None:
    """Print with a timestamp + flush — visible immediately in journalctl."""
    print(f"{time.strftime('%F %T')} {msg}", flush=True)


def _decision_label(text: str) -> str:
    if not text:
        return "—"
    upper = text.upper()
    for word in ("BUY", "SELL", "HOLD"):
        if re.search(rf"\b{word}\b", upper):
            return word
    # rating words
    for word, repl in (("OVERWEIGHT", "BUY"), ("UNDERWEIGHT", "SELL"),
                       ("NEUTRAL", "HOLD")):
        if re.search(rf"\b{word}\b", upper):
            return repl
    return "—"


def _decision_emoji(label: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(label, "⚪")


def _trade_date() -> str:
    """Today's date in Asia/Shanghai (matches when the timer fires)."""
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except Exception:
        return _dt.date.today().isoformat()


def _build_config(prefs: dict[str, Any], slug: str) -> dict[str, Any]:
    """Produce a worker-shape config dict for one user. Mirrors webui.py."""
    from tradingagents.default_config import DEFAULT_CONFIG
    user_home = Path.home() / ".tradingagents" / "users" / slug
    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"] = prefs.get("provider", "google")
    cfg["deep_think_llm"] = prefs.get("deep_model", "gemini-2.5-flash")
    cfg["quick_think_llm"] = prefs.get("quick_model", "gemini-2.5-flash")
    cfg["max_debate_rounds"] = int(prefs.get("max_debate_rounds", 1))
    cfg["max_risk_discuss_rounds"] = int(prefs.get("max_risk_discuss_rounds", 1))
    cfg["output_language"] = prefs.get("output_language", "中文")
    cfg["backend_url"] = None
    cfg["checkpoint_enabled"] = False
    cfg["data_cache_dir"] = str(user_home / "cache")
    cfg["results_dir"] = str(user_home / "logs")
    cfg["memory_log_path"] = str(user_home / "memory" / "trading_memory.md")
    return cfg


def _run_worker(slug: str, ticker: str, trade_date: str,
                prefs: dict[str, Any]) -> dict[str, Any]:
    """Spawn worker.py for one ticker. Returns:
        {"ok": True, "decision": "..."} on success
        {"ok": False, "error": {...}} on failure
    """
    config = _build_config(prefs, slug)
    selected = prefs.get("selected_analysts") or ["market"]
    request = {
        "config": config,
        "ticker": ticker,
        "trade_date": trade_date,
        "selected_analysts": selected,
    }
    proc = subprocess.Popen(
        [PYTHON_BIN, "-u", WORKER_PATH],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8",
    )
    proc.stdin.write(json.dumps(request))
    proc.stdin.close()
    decision: str | None = None
    error: dict[str, Any] | None = None
    chunk_count = 0
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("kind")
        if kind == "chunk":
            chunk_count += 1
        elif kind == "done":
            decision = ev.get("decision", "")
        elif kind == "error":
            error = ev
    proc.wait(timeout=60)
    _log(f"  worker {ticker}: chunks={chunk_count} exit={proc.returncode}")
    if error:
        return {"ok": False, "error": error}
    if decision is None:
        return {"ok": False, "error": {"type": "EmptyStream",
                                        "msg": "worker emitted no done event"}}
    return {"ok": True, "decision": decision}


def _load_full_state(slug: str, ticker: str, trade_date: str) -> dict[str, Any] | None:
    """Read the per-run JSON the worker just wrote (mirrors what webui's
    history panel reads)."""
    p = (Path.home() / ".tradingagents" / "users" / slug / "logs"
         / ticker / "TradingAgentsStrategy_logs"
         / f"full_states_log_{trade_date}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _push_full_report(
    chat_id: str, slug: str, ticker: str, trade_date: str, decision: str,
) -> None:
    """Send the analysis as a series of Telegram messages so a phone user can
    read everything inline without leaving the chat.

    First message: header (sound/vibrate). All subsequent: silent.
    """
    label = _decision_label(decision)
    emoji = _decision_emoji(label)

    full = _load_full_state(slug, ticker, trade_date)

    # Detect user-uploaded research notes used by this run, so the headline
    # message can call them out. Each uploaded note becomes a "## filename"
    # chunk in the joined string (per webui.py _assemble_user_research format).
    n_notes = 0
    if full:
        user_research_report = full.get("user_research_report") or ""
        if user_research_report:
            # Count by upload-separator, not by `## `, since LLM summaries may
            # emit `##` headers that would inflate the count.
            n_notes = user_research_report.count("\n\n---\n\n") + 1

    # 1. Header — small, formatted, with sound
    header = (
        f"📊 *{ticker}* · {trade_date}\n"
        f"*Decision*: {label} {emoji}"
    )
    if n_notes:
        suffix = "" if n_notes == 1 else "s"
        header += f"\n📎 Used {n_notes} user-uploaded research note{suffix}"
    notify.send_telegram(chat_id, header, parse_mode="Markdown",
                         disable_notification=False)

    # Range stats — fail-soft, never abort the report.
    try:
        rs = compute_range_stats(ticker, trade_date)
        notify.send_telegram(
            chat_id,
            format_range_stats_telegram(rs),
            parse_mode=None,
            disable_notification=True,
        )
    except RangeStatsUnavailable:
        pass
    except Exception as e:  # noqa: BLE001 — never let this kill a report
        _log(f"range-stats failed for {ticker}: {e}")

    sep = "━━━━━━━━━━━━━━━"

    sections: list[tuple[str, str]] = []
    if full:
        for key, label_zh in (
            ("market_report", "📈 市场分析 / Market"),
            ("sentiment_report", "💬 情绪分析 / Sentiment"),
            ("news_report", "📰 新闻 / News"),
            ("fundamentals_report", "🏢 基本面 / Fundamentals"),
            ("investment_plan", "⚖️ 投资方案（研究经理）/ Investment Plan"),
            ("trader_investment_decision", "💼 交易员方案 / Trader Plan"),
        ):
            content = (full.get(key) or "").strip()
            if content:
                sections.append((label_zh, content))

        # Investment debate
        debate = full.get("investment_debate_state") or {}
        bull = (debate.get("bull_history") or "").strip()
        bear = (debate.get("bear_history") or "").strip()
        rj = (debate.get("judge_decision") or "").strip()
        if bull or bear or rj:
            body = ""
            if bull: body += f"🐂 Bull\n{sep}\n{bull}\n\n"
            if bear: body += f"🐻 Bear\n{sep}\n{bear}\n\n"
            if rj:   body += f"⚖️ Research Manager\n{sep}\n{rj}"
            sections.append(("🐂🐻 多空辩论 / Bull-Bear Debate", body))

        # Risk debate
        risk = full.get("risk_debate_state") or {}
        agg = (risk.get("aggressive_history") or "").strip()
        con = (risk.get("conservative_history") or "").strip()
        neu = (risk.get("neutral_history") or "").strip()
        rrj = (risk.get("judge_decision") or "").strip()
        if agg or con or neu or rrj:
            body = ""
            if agg: body += f"🔥 Aggressive\n{sep}\n{agg}\n\n"
            if con: body += f"🛡️ Conservative\n{sep}\n{con}\n\n"
            if neu: body += f"⚖️ Neutral\n{sep}\n{neu}\n\n"
            if rrj: body += f"🧑‍💼 Portfolio Manager\n{sep}\n{rrj}"
            sections.append(("🔥🛡️ 风险辩论 / Risk Debate", body))

    # 2. Always include the final decision (verbatim from PM)
    sections.append(("🧑‍💼 最终决策 / Final Decision", decision.strip()))

    # 3. Send each section as its own silent message
    for title, content in sections:
        # parse_mode=None: LLM output may contain stray "*"/"_" that would break
        # the legacy Markdown parser. Title is plain ASCII so no risk.
        text = f"━━ {title} ━━\n\n{content}"
        notify.send_telegram(chat_id, text, parse_mode=None,
                             disable_notification=True)

    # 4. Footer with deep link back to webui (silent)
    footer = (
        f"🔗 完整 webui: {WEBUI_BASE_URL}\n"
        f"💡 命令: 给我发 /history {ticker} 看历史决策"
    )
    notify.send_telegram(chat_id, footer, parse_mode=None,
                         disable_notification=True)


def _push_error(chat_id: str, ticker: str, trade_date: str,
                err: dict[str, Any]) -> None:
    msg = (
        f"⚠️ *{ticker}* · {trade_date}\n"
        f"Daily analysis failed.\n\n"
        f"`{err.get('type', 'Error')}`: {err.get('msg', '(no message)')[:300]}"
    )
    notify.send_telegram(chat_id, msg, parse_mode="Markdown")


def _process_user(slug: str, prefs: dict[str, Any], *, dry_run: bool) -> None:
    chat_id = (prefs.get("telegram_chat_id") or "").strip()
    raw_tickers = [t.strip() for t in (prefs.get("tickers") or []) if t and t.strip()]
    if not prefs.get("daily_schedule_enabled"):
        _log(f"user {slug}: skip (disabled)")
        return
    if not chat_id:
        _log(f"user {slug}: skip (no telegram_chat_id)")
        return
    if not raw_tickers:
        _log(f"user {slug}: skip (empty watchlist)")
        return

    trade_date = _trade_date()
    _log(f"user {slug}: {len(raw_tickers)} ticker(s) for {trade_date}")

    for raw in raw_tickers:
        ticker, _resolve_msg = ticker_resolver.resolve_ticker(raw)
        if not ticker:
            _log(f"  '{raw}': could not resolve")
            if not dry_run:
                notify.send_telegram(chat_id,
                    f"⚠️ Couldn't resolve `{raw}` to a ticker symbol.")
            continue
        _log(f"  {raw} → {ticker}")

        if dry_run:
            continue

        result = _run_worker(slug, ticker, trade_date, prefs)
        if result["ok"]:
            try:
                _push_full_report(chat_id, slug, ticker, trade_date,
                                  result["decision"])
            except Exception as e:
                _log(f"  telegram push failed for {ticker}: "
                     f"{type(e).__name__}: {e}")
        else:
            _push_error(chat_id, ticker, trade_date, result["error"])


def _acquire_host_lock() -> int | None:
    """Single-instance file lock so two scheduler runs can't trample."""
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would run; no worker spawn, no Telegram.")
    ap.add_argument("--user", help="Limit to a specific slug (or email — will be hashed).")
    args = ap.parse_args()

    if not os.getenv("TELEGRAM_BOT_TOKEN") and not args.dry_run:
        _log("TELEGRAM_BOT_TOKEN is not set — refusing to run a real schedule.")
        return 2

    lock = _acquire_host_lock()
    if lock is None:
        _log("another scheduler instance is already running — exiting.")
        return 0
    try:
        users = user_prefs.all_users_with_prefs()
        if args.user:
            target = args.user
            if "@" in target:
                target = user_prefs.user_home(target).name  # hash to slug
            users = [(s, p) for s, p in users if s == target]

        if not users:
            _log("no users with preferences found.")
            return 0

        _log(f"scheduler start: {len(users)} user(s){' [DRY-RUN]' if args.dry_run else ''}")
        for slug, prefs in users:
            try:
                _process_user(slug, prefs, dry_run=args.dry_run)
            except Exception as e:
                _log(f"user {slug}: UNEXPECTED ERROR {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
        _log("scheduler done.")
        return 0
    finally:
        try:
            os.close(lock)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
