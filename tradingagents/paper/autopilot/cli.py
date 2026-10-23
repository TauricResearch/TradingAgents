"""Koral Equities V3: independent autonomous PAPER-ONLY swing-alpha daemon.

Usage is operator-controlled; serve must stay running (or be scheduled on the
operator's own computer). It NEVER connects to a brokerage or Trading 212.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from tradingagents.paper.autopilot.performance import scorecard

from tradingagents.paper.cli import exclusive
from tradingagents.paper.autopilot import feeds, observe, runner
from tradingagents.paper.autopilot.state import STATE, atomic_write, create_new, read


def status(state) -> dict:
    book = state.portfolio.book
    history = book.equity_history
    benchmark = history[-1]["spy_benchmark_gbp"] if history else None
    return {"mode": "V3_AUTONOMOUS_PAPER_ONLY", "schema": state.schema,
            "created_utc": state.created_utc, "start": book.started,
            "last_session": book.last_session, "equity_gbp": round(book.equity(),2),
            "cash_gbp": round(book.cash_gbp, 2),
            "spy_buy_and_hold_gbp": benchmark,
            "positions": list(book.positions.values()), "orders": list(book.orders),
            "intents": {k:{"status":x["status"], "ticker":x["plan"]["ticker"],
                           "confirmations":x["consecutive"]} for k,x in state.portfolio.intents.items()},
            "auto_paper_enabled": state.auto_paper_enabled, "paused": state.paused,
            "drawdown_halt":book.halted, "watchlist":state.watchlist,
            "ai_research_count":len(state.ai_receipts),
            "recent_audit":state.audit[-8:], "real_money_exposure":0,
            "performance": scorecard(book)}


def run_phase(path: Path, phase: str, *, now: datetime | None = None):
    with exclusive(path):
        if phase in ("preopen", "preclose"):
            return runner.snapshot_phase(path, phase=phase, now=now)
        if phase == "close":
            return runner.run_afterclose(path, now=now)
        raise ValueError("Unknown phase")


def next_phase(now: datetime) -> str | None:
    try:
        feeds.session_cutoff(now, "preopen")
        return "preopen"
    except ValueError:
        pass
    try:
        feeds.session_cutoff(now, "preclose")
        return "preclose"
    except ValueError:
        pass
    try:
        feeds.session_cutoff(now, "close")
        return "close"
    except ValueError:
        return None


def serve(path: Path, every_seconds: int = 60):
    """Timezone-aware polling while this local process runs; not cloud automation."""
    if not 30 <= every_seconds <= 3600:
        raise ValueError("Poll interval must be 30–3600 seconds")
    print("KORAL EQUITIES V3 | paper-only local scheduler active; Ctrl+C to stop",flush=True)
    print("PREOPEN 08:45-09:25, PRECLOSE 17:00-17:25, CLOSE >=17:40 New York local.",flush=True)
    attempted: dict[str,float] = {}
    while True:
        now = datetime.now(timezone.utc)
        # This is a weak process-pulse, NOT authorization to buy anything.
        # Status UI must not confuse 'enabled' with a running scheduler.
        pulse = path.expanduser().resolve().parent / "service_heartbeat.json"
        pulse.parent.mkdir(parents=True, exist_ok=True)
        tmp = pulse.with_name(".heartbeat.tmp")
        tmp.write_text(json.dumps({"last_pulse_utc":now.isoformat(),"mode":"PAPER_ONLY"}), encoding="utf-8")
        os.replace(tmp,pulse)
        phase = next_phase(now)
        if phase is not None:
            key = feeds.ny_now(now).date().isoformat() + ":" + phase
            try:
                root = path.expanduser().resolve().parent
                snap = root / "calendar" / feeds.ny_now(now).date().isoformat() / (phase + ".json")
                st = read(path)
                if (phase in ("preopen", "preclose") and snap.exists()) or (
                        phase == "close" and st.portfolio.book.last_session == feeds.ny_now(now).date().isoformat()
                        and (not st.can_buy() or all(f"{st.portfolio.book.last_session}:{t}" in st.ai_receipts
                            for t in st.watchlist[:3] if t not in st.portfolio.book.positions))):
                    attempted[key] = now.timestamp()
                elif now.timestamp() - attempted.get(key, 0) >= 600:
                    attempted[key] = now.timestamp()
                    result = run_phase(path, phase, now=now)
                    print(json.dumps(result, indent=2, default=str),flush=True)
            except Exception as exc:
                print(f"V3 {phase} FAIL CLOSED: {type(exc).__name__}: {exc}",file=sys.stderr,flush=True)
        time.sleep(every_seconds)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="koral-equities-v3", description="Autonomous, independently audited GBP paper simulator; no real broker")
    parser.add_argument("--state", type=Path, default=STATE)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Initialize a NEW separate V3 £10k portfolio; never overwrite")
    init.add_argument("--start", required=True, help="Today or last completed NYSE session (YYYY-MM-DD)")
    init.add_argument("--tickers", nargs="+", default=["AAPL","MSFT","NVDA"], help="Predeclared Swing Alpha watchlist, max 8")
    for name in ("status", "report", "enable-paper", "disable-paper", "pause", "resume", "preopen", "preclose", "close"):
        commands.add_parser(name)
    cancel = commands.add_parser("cancel-intent")
    cancel.add_argument("id")
    service = commands.add_parser("serve", help="Run local NY-time scheduler while this PC is on")
    service.add_argument("--poll-seconds", type=int, default=60)
    watcher = commands.add_parser("observe", help="Collect research-only feeds; cannot modify any paper portfolio")
    watcher.add_argument("--dir", type=Path, default=observe.DEFAULT_OBSERVATION_HOME)
    watcher.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "NVDA"])
    watcher.add_argument("--poll-seconds", type=int, default=60)
    watcher.add_argument("--once", action="store_true", help="Probe the current NY window once, then exit")
    args = parser.parse_args(argv)
    try:
        path = args.state.expanduser().resolve()
        if args.command == "observe":
            result = observe.monitor(
                args.dir, args.tickers,
                poll_seconds=args.poll_seconds,
                once=args.once,
            )
            if result is not None:
                print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "serve":
            read(path)  # Preflight: refuse missing ledger, never auto-init.
            serve(path, args.poll_seconds)
            return 0
        with exclusive(path):
            if args.command == "init":
                st = create_new(path, args.start, args.tickers)
                result = status(st)
            elif args.command in {"preopen", "preclose", "close"}:
                # Cannot be invoked as-of a user-forged date: actual NY clock only.
                if args.command in ("preopen", "preclose"):
                    result = runner.snapshot_phase(path, phase=args.command)
                else:
                    result = runner.run_afterclose(path)
            else:
                st = read(path)
                if args.command in ("status", "report"):
                    result = scorecard(st.portfolio.book) if args.command=="report" else status(st)
                else:
                    if args.command == "enable-paper":st.set_running(True)
                    elif args.command == "disable-paper":st.set_running(False)
                    elif args.command == "pause":st.pause(True)
                    elif args.command == "resume":st.pause(False)
                    elif args.command == "cancel-intent":
                        if st.portfolio.cancel(args.id):st.event("OPERATOR_CANCELLED",id=args.id)
                    else:
                        raise ValueError("Unsupported operator command")
                    atomic_write(path, st)
                    result = status(st)
        print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"V3 PAPER SAFE HALT: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
