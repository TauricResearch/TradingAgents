"""Standalone, append-only audited V3 *simulated* portfolio. Zero broker code.

State is a distinct V3 ledger, not V1/V2. No in-place mutating past returns.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from tradingagents.paper.conditional import ConditionalBook, TradeIntent

VERSION = "koral-autopaper-v3.1-isolated"
HOME = Path.home() / ".tradingagents" / "paper" / "v3_autopilot"
STATE = HOME / "portfolio.json"
LEGACIES = (Path.home() / ".tradingagents" / "paper" / "portfolio.json",
            Path.home() / ".tradingagents" / "paper" / "v2" / "portfolio.json",
            Path.home() / ".tradingagents" / "paper" / "v3" / "portfolio.json")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,11}\Z")


def normalize_tickers(names: list[str], cap: int = 8) -> list[str]:
    if not isinstance(names, list) or not 1 <= len(names) <= cap:
        raise ValueError("Provide 1-8 pre-declared stocks for the swing sleeve")
    if any(type(x) is not str or x != x.strip().upper() or not SYMBOL.fullmatch(x) for x in names):
        raise ValueError("Invalid canonical US-listed ticker")
    if len(set(names)) != len(names):
        raise ValueError("Duplicate ticker")
    return names


def fingerprint(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


@dataclass
class V3State:
    created_utc: str
    portfolio: ConditionalBook
    watchlist: list[str]
    auto_paper_enabled: bool = False
    paused: bool = False
    ai_receipts: dict[str, dict] = field(default_factory=dict)
    audit: list[dict] = field(default_factory=list)
    schema: str = VERSION

    @classmethod
    def new(cls, start: str, tickers: list[str]) -> "V3State":
        date.fromisoformat(start)
        instance = cls(datetime.now(timezone.utc).isoformat(),
                       ConditionalBook.new(start), normalize_tickers(tickers))
        instance.event("V3_CREATED", date=start, paper_only=True, watchlist=instance.watchlist)
        return instance

    def event(self, kind: str, **details) -> None:
        record = {"seq": len(self.audit) + 1, "kind": kind,
                  "utc": datetime.now(timezone.utc).isoformat(),
                  "previous": self.audit[-1]["hash"] if self.audit else "0" * 64,
                  "details": details}
        record["hash"] = fingerprint(record)
        self.audit.append(record)

    def to_dict(self) -> dict:
        return {"schema": self.schema, "created_utc": self.created_utc,
                "watchlist": self.watchlist, "auto_paper_enabled": self.auto_paper_enabled,
                "paused": self.paused, "ai_receipts": self.ai_receipts,
                "portfolio": self.portfolio.to_dict(), "audit": self.audit,
                "paper_only": True}

    @classmethod
    def from_dict(cls, data: dict) -> "V3State":
        expected = {"schema", "created_utc", "watchlist", "auto_paper_enabled", "paused",
                    "ai_receipts", "portfolio", "audit", "paper_only"}
        if type(data) is not dict or set(data) != expected or data["schema"] != VERSION or data["paper_only"] is not True:
            raise ValueError("Invalid or non-paper V3 state")
        if type(data["auto_paper_enabled"]) is not bool or type(data["paused"]) is not bool:
            raise ValueError("Autonomy controls tampered with")
        if type(data["ai_receipts"]) is not dict or type(data["audit"]) is not list:
            raise ValueError("Invalid V3 journal")
        previous = "0" * 64
        for i, item in enumerate(data["audit"], 1):
            if (not isinstance(item, dict) or set(item) != {"seq", "kind", "utc", "previous", "details", "hash"}
                    or item["seq"] != i or item["previous"] != previous):
                raise ValueError("V3 journal hash chain is broken")
            original = dict(item)
            digest = original.pop("hash")
            if fingerprint(original) != digest:
                raise ValueError("V3 journal hash mismatch")
            previous = digest
        result = cls(data["created_utc"], ConditionalBook.from_dict(data["portfolio"]),
                     normalize_tickers(data["watchlist"]), data["auto_paper_enabled"],
                     data["paused"], deepcopy(data["ai_receipts"]), deepcopy(data["audit"]))
        return result

    def can_buy(self) -> bool:
        return bool(self.auto_paper_enabled and not self.paused and not self.portfolio.book.halted)

    def set_running(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("Invalid autonomy toggle")
        if self.auto_paper_enabled != enabled:
            self.auto_paper_enabled = enabled
            self.event("AUTOPAPER_ENABLED" if enabled else "AUTOPAPER_DISABLED")
            if not enabled:
                self.cancel_queued("autonomy_disabled")

    def pause(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("Invalid pause toggle")
        if self.paused != enabled:
            self.paused = enabled
            self.event("PAUSED" if enabled else "RESUMED")
            if enabled:
                self.cancel_queued("operator_paused")

    def cancel_queued(self, reason: str) -> None:
        for intent_id, record in list(self.portfolio.intents.items()):
            if record["status"] in ("WATCHING", "QUEUED"):
                self.portfolio.cancel(intent_id)
                self.event("V3_CANCELLED", intent_id=intent_id, reason=reason)

    def machine_accept(self, plan: TradeIntent, report: str, session: str,
                       approval: str) -> None:
        """Separately audited V3 automated POLICY gate; not V2 human approval.

        Plan must be independently validated by v3/decision.py before calling.
        No automatic rating-to-buy shortcut; no manual operator impersonation.
        """
        from tradingagents.paper.conditional import evidence_hash
        if approval != "POLICY_VERIFIED" or not self.can_buy():
            raise ValueError("No V3 machine-verified permission for a new entry")
        plan.validate()
        if evidence_hash(report) != plan.report_sha256:
            raise ValueError("Research provenance mismatch")
        if plan.decision_date != session or self.portfolio.book.last_session != session:
            raise ValueError("Plan decision not from latest marked session")
        if plan.ticker not in self.watchlist:
            raise ValueError("Ticker not in operator-approved swing watchlist")
        if plan.intent_id in self.portfolio.intents:
            raise ValueError("Intent replay")
        if plan.ticker in self.portfolio.book.positions or any(o["ticker"] == plan.ticker for o in self.portfolio.book.orders):
            raise ValueError("Existing exposure")
        if any(rec["plan"]["ticker"] == plan.ticker and rec["status"] in ("WATCHING", "QUEUED")
               for rec in self.portfolio.intents.values()):
            raise ValueError("Live plan already exists")
        # Limit new autonomous exposure to one idea each completed market day.
        if any(e["kind"] == "V3_POLICY_ACCEPTED" and e["details"]["date"] == session
               for e in self.audit):
            raise ValueError("V3 policy permits at most one new intent per session")
        self.portfolio.intents[plan.intent_id] = {
            "plan": asdict(plan), "status": "WATCHING", "consecutive": 0,
            "last_close_usd": None, "last_seen_date": session, "order_id": None}
        self.portfolio.book._event(session, "V3_MACHINE_POLICY_ACCEPTED", ticker=plan.ticker,
                                   intent_id=plan.intent_id, report_sha256=plan.report_sha256)
        self.event("V3_POLICY_ACCEPTED", date=session, ticker=plan.ticker,
                   intent_id=plan.intent_id, report_sha256=plan.report_sha256,
                   entry_rule=plan.entry_rule, verified_policy=True)


def checked_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved in {x.resolve() for x in LEGACIES}:
        raise ValueError("V1 and V2 paper ledgers are immutable from the V3 application")
    if resolved.name != "portfolio.json":
        raise ValueError("V3 state file must be named portfolio.json")
    return resolved


def read(path: Path = STATE) -> V3State:
    path = checked_path(path)
    result = V3State.from_dict(json.loads(path.read_text(encoding="utf-8")))
    # Verify the externally stored daily pricing evidence as well as the audit
    # hash chain before allowing ANY subsequent simulated entry or mark.
    root = path.parent / "market_evidence"
    for item in result.audit:
        if item["kind"] != "SESSION_MARKED":
            continue
        details = item["details"]
        day = details.get("date")
        expected = details.get("market_input_sha256")
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("Market evidence session metadata missing")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Market evidence fingerprint missing")
        evidence = root / (day + ".json")
        if not evidence.is_file() or hashlib.sha256(evidence.read_bytes()).hexdigest() != expected:
            raise ValueError("Market evidence tampered or unavailable; halt for reconciliation")
    return result


def atomic_write(path: Path, state: V3State) -> None:
    path = checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".v3-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(tmp, 0o600)
            json.dump(state.to_dict(), handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def create_new(path: Path, date_: str, tickers: list[str]) -> V3State:
    path = checked_path(path)
    if path.exists():
        raise ValueError("V3 paper account already exists; refusing to reset")
    instance = V3State.new(date_, tickers)
    atomic_write(path, instance)
    return instance
