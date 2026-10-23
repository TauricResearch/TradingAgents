"""Koral Equities V2 *offline* paper-replay CLI. No market API or brokerage calls.

Usage is deliberately explicit and cannot promote a model's Buy/Overweight
rating into an executable contract. A human must approve an independently
validated JSON plan. The original account is never read or written.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import fields
from datetime import date
from pathlib import Path

from .conditional import (
    ConditionalBook, EarningsSnapshot, TradeIntent, dump_v2, evidence_hash,
)
from .engine import Bar

DEFAULT_V2_PATH = Path.home() / ".tradingagents" / "paper" / "v2" / "portfolio.json"


def _write(path: Path, data: ConditionalBook) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".koral-v2-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(dump_v2(data))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read(path: Path) -> ConditionalBook:
    if not path.exists():
        raise ValueError("No isolated V2 paper account. Run 'init' first.")
    return ConditionalBook.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    return raw


def _strict_dataclass(typ, raw: dict):
    if not isinstance(raw, dict) or set(raw) != {f.name for f in fields(typ)}:
        raise ValueError("JSON must exactly match the approved schema")
    return typ(**raw)


def _read_day(path: Path):
    x = _json(path)
    expected = {"session", "bars", "gbp_per_usd_open", "gbp_per_usd_close", "spy_close_usd",
                "earnings_preopen", "earnings_afterclose"}
    if set(x) != expected:
        raise ValueError("Daily fixture missing keys or has unknown data")
    candles = {symbol: _strict_dataclass(Bar, data) for symbol, data in x["bars"].items()}
    pre = {symbol: _strict_dataclass(EarningsSnapshot, data)
           for symbol, data in x["earnings_preopen"].items()}
    close = {symbol: _strict_dataclass(EarningsSnapshot, data)
             for symbol, data in x["earnings_afterclose"].items()}
    return x["session"], candles, x["gbp_per_usd_open"], x["gbp_per_usd_close"], \
        x["spy_close_usd"], pre, close


def _print(book: ConditionalBook):
    b = book.book
    print(f"KORAL EQUITIES V2 | OFFLINE REPLAY | equity GBP {b.equity():,.2f} | "
          f"cash GBP {b.cash_gbp:,.2f} | last {b.last_session or 'none'} | "
          f"holdings {len(b.positions)} | queued {len(b.orders)} | halted={b.halted}")
    for identifier, i in book.intents.items():
        print(f"  {identifier} {i['plan']['ticker']}: {i['status']} "
              f"({i['consecutive']} confirming closes)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="koral-equities-v2-replay",
                                     description="Isolated conditional offline simulation only")
    parser.add_argument("--state", type=Path, default=DEFAULT_V2_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    initialise = commands.add_parser("init", help="Create separate V2 paper account (never overwrite)")
    initialise.add_argument("--start", required=True, help="First eligible simulated session YYYY-MM-DD")
    commands.add_parser("status")
    submit = commands.add_parser("approve-plan", help="Explicitly approve a structured candidate")
    submit.add_argument("--plan", type=Path, required=True)
    submit.add_argument("--report", type=Path, required=True,
                        help="Exact original report text file used for provenance hash")
    submit.add_argument("--approve", action="store_true", help="Human approves the stated plan")
    replay = commands.add_parser("replay-day", help="Advance by one as-of fixture, never network data")
    replay.add_argument("--fixture", type=Path, required=True)
    cancel = commands.add_parser("cancel-intent")
    cancel.add_argument("id")
    args = parser.parse_args(argv)
    path = args.state.expanduser().resolve()
    baseline = Path.home() / ".tradingagents" / "paper" / "portfolio.json"
    if path == baseline.resolve():
        parser.error("Refusing to overwrite the original V1 paper portfolio")
    try:
        if args.command == "init":
            date.fromisoformat(args.start)
            if path.exists():
                raise ValueError("V2 state already exists; never reset or overwrite")
            book = ConditionalBook.new(args.start)
            _write(path, book)
        else:
            book = _read(path)
            if args.command == "approve-plan":
                if not args.approve:
                    raise ValueError("Explicit --approve is required for research sandbox plans")
                plan = _strict_dataclass(TradeIntent, _json(args.plan))
                actual = evidence_hash(args.report.read_text(encoding="utf-8"))
                if plan.report_sha256 != actual:
                    raise ValueError("Plan report_sha256 does not match the supplied research report")
                book.submit(plan, operator_approved=True)
                _write(path, book)
            elif args.command == "replay-day":
                day, bars, fx0, fx1, spy, pre, close = _read_day(args.fixture)
                book = book.advance(day, bars, fx0, fx1, spy, pre, close)
                _write(path, book)
            elif args.command == "cancel-intent":
                if book.cancel(args.id):
                    _write(path, book)
        _print(book)
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"V2 replay rejected: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
