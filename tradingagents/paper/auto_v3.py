"""Koral Equities V3 PAPER rehearsal. No broker API or AI-generated orders.

Separate V3 ledger, strict as-of JSON feeds, atomic state, exclusive lock and
tamper-detectable session journal. Live-source and AI approval adapters are
NOT implemented: data from local fixtures are NOT independently verified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from .conditional import ConditionalBook, EarningsSnapshot, TradeIntent, evidence_hash, dump_v2
from .engine import Bar

DEFAULT_HOME = Path.home() / ".tradingagents" / "paper" / "v3"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".ke-v3-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def exclusive(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("V3 account already locked; investigate previous process") from exc
    try:
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def locations(home: Path):
    home = home.expanduser().resolve()
    baseline = (Path.home() / ".tradingagents" / "paper").resolve()
    if home in (baseline, baseline / "v2"):
        raise ValueError("Refusing to write V1 or V2 account")
    return home / "portfolio.json", home / "journal.jsonl", home / "run.lock"


def init(home: Path, start: str):
    date.fromisoformat(start)
    book, journal, mutex = locations(home)
    with exclusive(mutex):
        if book.exists() or journal.exists():
            raise ValueError("V3 account exists; do not reset")
        atomic(book, dump_v2(ConditionalBook.new(start)).encode("utf-8"))
        atomic(journal, b"")


def read(home: Path):
    book, _, _ = locations(home)
    if not book.is_file():
        raise ValueError("V3 portfolio absent; init first")
    return ConditionalBook.from_dict(json.loads(book.read_text(encoding="utf-8")))


def verify(home: Path):
    book, journal, _ = locations(home)
    if not book.exists() or not journal.exists():
        raise ValueError("Missing V3 book or journal")
    records = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines() if x.strip()]
    if records and records[-1]["after_sha256"] != digest(book.read_bytes()):
        raise ValueError("Journal mismatch: manual reconciliation required")
    for old, new in zip(records, records[1:]):
        if old["after_sha256"] != new["before_sha256"]:
            raise ValueError("Broken journal continuity")


def feed(source: Path):
    raw = source.read_bytes()
    obj = json.loads(raw)
    required = {"day", "source", "captured_at_utc", "bars",
                "gbp_per_usd_open", "gbp_per_usd_close", "spy_close_usd",
                "earnings_preopen", "earnings_afterclose"}
    if not isinstance(obj, dict) or set(obj) != required:
        raise ValueError("Incomplete or unrecognised feed schema")
    day = date.fromisoformat(obj["day"])
    stamp = datetime.fromisoformat(obj["captured_at_utc"])
    if stamp.tzinfo is None or stamp.utcoffset() != timezone.utc.utcoffset(stamp):
        raise ValueError("Capture timestamp must be UTC")
    if stamp.date() < day or not isinstance(obj["source"], str) or len(obj["source"]) < 5:
        raise ValueError("Invalid feed provenance")
    # A daily OHLC file is not admissible before the completed NY session.
    # The 17:30 NY cutoff is intentionally conservative; an actual exchange
    # holiday/calendar adapter is mandatory before real automated scheduling.
    from zoneinfo import ZoneInfo
    from datetime import time
    ny_stamp = stamp.astimezone(ZoneInfo("America/New_York"))
    if day.weekday() >= 5 or ny_stamp.date() != day or ny_stamp.time() < time(17, 30):
        raise ValueError("Daily feed published before safe NY close, or not an eligible weekday")
    def typed(group, typ):
        if not isinstance(group, dict):
            raise ValueError("Feed group is not a record")
        return {key: typ(**value) for key, value in group.items()}
    bars = typed(obj["bars"], Bar)
    if any(not item.valid() for item in bars.values()):
        raise ValueError("Invalid stock OHLC")
    for key in ("gbp_per_usd_open", "gbp_per_usd_close"):
        x = obj[key]
        if type(x) not in (float, int) or not .3 <= x <= 2.0:
            raise ValueError("Invalid GBP/USD conversion")
    spy = obj["spy_close_usd"]
    if type(spy) not in (float, int) or not 1 <= spy <= 100000:
        raise ValueError("Invalid SPY quote")
    return raw, obj, bars, typed(obj["earnings_preopen"], EarningsSnapshot), typed(obj["earnings_afterclose"], EarningsSnapshot)


def run_day(home: Path, source: Path, *, preview: bool = False):
    book_path, journal, mutex = locations(home)
    if source.resolve() in {book_path.resolve(), journal.resolve()}:
        raise ValueError("Account file cannot be used as a quote feed")
    with exclusive(mutex):
        verify(home)
        prior = read(home)
        raw, obj, bars, pre, after = feed(source)
        day = obj["day"]
        if prior.book.last_session is not None and day <= prior.book.last_session:
            raise ValueError("Duplicate or out-of-order daily session")
        updated = prior.advance(day, bars, obj["gbp_per_usd_open"],
                                obj["gbp_per_usd_close"], obj["spy_close_usd"],
                                pre, after)
        payload = dump_v2(updated).encode("utf-8")
        result = {"day": day, "feed_sha256": digest(raw),
                  "source": obj["source"], "before_sha256": digest(book_path.read_bytes()),
                  "after_sha256": digest(payload),
                  "new_events": len(updated.book.events) - len(prior.book.events),
                  "mode": "PREVIEW" if preview else "PAPER_ADVANCED"}
        if not preview:
            history = journal.read_bytes()
            atomic(journal, history + json.dumps(result, sort_keys=True).encode() + b"\n")
            atomic(book_path, payload)
        return result


def approve_plan(home: Path, plan_path: Path, report_path: Path, *, operator_approved: bool=False):
    """Operator-reviewed structured paper plan; never infer one from a rating."""
    if operator_approved is not True:
        raise ValueError("Explicit operator approval required")
    book_path, journal, mutex = locations(home)
    if plan_path.resolve() in {book_path.resolve(),journal.resolve()} or report_path.resolve() in {book_path.resolve(),journal.resolve()}:
        raise ValueError("A portfolio file is not an investment report")
    with exclusive(mutex):
        verify(home)
        book = read(home)
        fields = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(fields, dict):
            raise ValueError("Structured plan must be a JSON object")
        plan = TradeIntent(**fields)
        source = report_path.read_text(encoding="utf-8")
        if evidence_hash(source) != plan.report_sha256:
            raise ValueError("Plan does not match original report SHA-256")
        book.submit(plan, operator_approved=True)
        payload = dump_v2(book).encode("utf-8")
        record = {"kind":"V3_OPERATOR_APPROVED_PLAN", "intent_id":plan.intent_id,
                  "ticker":plan.ticker, "report_sha256":plan.report_sha256,
                  "before_sha256":digest(book_path.read_bytes()),
                  "after_sha256":digest(payload), "day":plan.decision_date}
        original = journal.read_bytes()
        atomic(journal, original + json.dumps(record,sort_keys=True).encode() + b"\n")
        atomic(book_path, payload)
        return {"intent_id":plan.intent_id,"status":"WATCHING","mode":"PAPER_ONLY"}


def main(argv=None):
    p = argparse.ArgumentParser(prog="koral-equities-v3",
                                description="Isolated V3 paper replay, never brokerage execution")
    p.add_argument("--home", type=Path, default=DEFAULT_HOME)
    commands = p.add_subparsers(dest="cmd", required=True)
    commands.add_parser("status")
    create = commands.add_parser("init")
    create.add_argument("--start", required=True)
    advance = commands.add_parser("advance-day")
    advance.add_argument("--feed", type=Path, required=True)
    advance.add_argument("--preview", action="store_true")
    approval = commands.add_parser("approve-plan", help="Manually approve an exact structured paper plan")
    approval.add_argument("--plan", type=Path, required=True)
    approval.add_argument("--report", type=Path, required=True)
    approval.add_argument("--approve", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.cmd == "init":
            init(args.home, args.start)
        elif args.cmd == "status":
            verify(args.home)
            account = read(args.home)
            print(json.dumps({"mode": "V3_PAPER_ONLY", "equity_gbp": account.book.equity(),
                              "session": account.book.last_session,
                              "positions": len(account.book.positions),
                              "intents": len(account.intents)}))
        elif args.cmd == "advance-day":
            print(json.dumps(run_day(args.home, args.feed, preview=args.preview)))
        elif args.cmd == "approve-plan":
            print(json.dumps(approve_plan(args.home,args.plan,args.report,operator_approved=args.approve)))
        return 0
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        p.exit(2, f"V3 BLOCKED: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
