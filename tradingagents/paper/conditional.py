"""Koral Equities V2: auditable, long-only conditional paper-execution contract.

This is a separately versioned, offline decision replay. It does NOT parse an
LLM's prose into trade orders, schedule trades, or contact a real broker.
Unknown, contradictory or missing instructions fail closed.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from .engine import Bar, Book

_SCHEMA = "koral-conditional-v2.1"
_TICKER = re.compile(r"[A-Z0-9.\-]{1,16}\Z")
_SECTOR = re.compile(r"[A-Za-z][A-Za-z0-9 &\-]{1,60}\Z")


def _day(x: str) -> date:
    if not isinstance(x, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", x):
        raise ValueError("Expected YYYY-MM-DD date")
    v = date.fromisoformat(x)
    if v.isoformat() != x:
        raise ValueError("Noncanonical date")
    return v


def _number(x: float, name: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(x)


@dataclass(frozen=True)
class TradeIntent:
    """Explicit permission to *consider* a conditional LONG paper entry.

    A raw Buy/Overweight rating is NOT this structure. 'Risk reference' prose
    is not a stop order. A stop here must be approved as a real stop trigger.
    Decisions of any other type must be recorded as research-only elsewhere.
    """

    intent_id: str
    ticker: str
    decision_date: str
    expiry_date: str
    rating: str
    side: str
    entry_rule: str
    trigger_usd: float
    required_closes: int
    stop_loss_usd: float
    stop_is_executable: bool
    initial_allocation_fraction: float
    max_holding_sessions: int
    max_entry_gap_fraction: float
    sector: str
    report_sha256: str
    source: str = "STRUCTURED_APPROVED_RESEARCH"
    schema: str = _SCHEMA

    def validate(self) -> None:
        if self.schema != _SCHEMA:
            raise ValueError("Unknown V2 execution contract version")
        if not isinstance(self.intent_id, str) or not re.fullmatch(r"KEI-[A-Z0-9_-]{4,64}", self.intent_id):
            raise ValueError("Invalid immutable intent ID")
        if not isinstance(self.ticker, str) or not _TICKER.fullmatch(self.ticker):
            raise ValueError("Ticker must be canonical uppercase US symbol")
        if self.side != "ENTER_LONG" or self.entry_rule != "CLOSES_ABOVE":
            raise ValueError("Only explicitly conditional long entries supported")
        if self.rating not in ("Buy", "Overweight"):
            raise ValueError("A long entry requires a positive final rating")
        if self.stop_is_executable is not True:
            raise ValueError("A risk-review reference is NOT an approved stop")
        signal = _day(self.decision_date)
        expiry = _day(self.expiry_date)
        if not signal < expiry <= signal + timedelta(days=31):
            raise ValueError("Entry expiry must be 1–31 calendar days after decision")
        if type(self.required_closes) is not int or not 1 <= self.required_closes <= 3:
            raise ValueError("Required consecutive closes must be 1–3")
        if type(self.max_holding_sessions) is not int or not 1 <= self.max_holding_sessions <= 126:
            raise ValueError("Holding period must be 1–126 sessions")
        trigger = _number(self.trigger_usd, "entry trigger")
        stop = _number(self.stop_loss_usd, "executable stop")
        if not .70 * trigger <= stop < trigger:
            raise ValueError("Stop must be below trigger and within 30%")
        alloc = _number(self.initial_allocation_fraction, "initial allocation")
        if alloc > .30:
            raise ValueError("Initial allocation may not exceed 30%")
        gap = _number(self.max_entry_gap_fraction, "maximum entry gap")
        if gap > .05:
            raise ValueError("Maximum entry gap may not exceed 5%")
        if not isinstance(self.sector, str) or not _SECTOR.fullmatch(self.sector):
            raise ValueError("Verified sector label is required")
        if not isinstance(self.report_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.report_sha256):
            raise ValueError("Source report SHA-256 provenance required")
        if self.source != "STRUCTURED_APPROVED_RESEARCH":
            raise ValueError("Unapproved research origin")


@dataclass(frozen=True)
class EarningsSnapshot:
    """A timestamped issuer earnings calendar snapshot from an independent feed.

    Requires independent verification of publication time and vendor correctness.
    A schema prevents use of late-arriving data, but cannot prove provenance.
    """

    asof_date: str
    next_earnings_date: str | None
    last_earnings_date: str | None
    source: str
    verified: bool
    observed_at_utc: str

    def safe(self, session: str, phase: str, blackout_days: int = 7) -> bool:
        if self.asof_date != session or self.verified is not True or not self.source:
            return False
        if self.next_earnings_date is None or self.last_earnings_date is None:
            return False  # Missing last/next earnings date is NOT an all-clear.
        if phase not in {"preopen", "afterclose"}:
            raise ValueError("Invalid earnings snapshot cutoff")
        day = _day(session)
        try:
            observed = datetime.fromisoformat(self.observed_at_utc)
            if observed.utcoffset() is None:
                return False
            ny = ZoneInfo("America/New_York")
            cutoff = datetime.combine(day,
                                      time(9, 30) if phase == "preopen" else time(17, 30),
                                      tzinfo=ny)
            age = cutoff - observed.astimezone(ny)
            # Refuse earnings calendars that were published too late or are
            # stale by more than four hours at the decision-time cutoff.
            if not timedelta(0) <= age <= timedelta(hours=4):
                return False
        except (ValueError, TypeError, OverflowError):
            return False
        next_event = _day(self.next_earnings_date)
        last_event = _day(self.last_earnings_date)
        if last_event > day or last_event >= next_event:
            return False
        # Exclude 2 calendar days *following* a confirmed earnings event so
        # the first after-hours repricing cannot be mistaken for a normal setup.
        return (next_event - day).days > blackout_days and (day - last_event).days > 2


@dataclass
class ConditionalBook:
    """V2 state beside, never over, the original baseline ledger."""

    book: Book
    intents: dict[str, dict] = field(default_factory=dict)
    schema: str = _SCHEMA

    @classmethod
    def new(cls, start: str) -> "ConditionalBook":
        return cls(Book.new(start))

    def to_dict(self) -> dict:
        return {"schema": self.schema, "book": asdict(self.book), "intents": deepcopy(self.intents)}

    @classmethod
    def from_dict(cls, data: dict) -> "ConditionalBook":
        if not isinstance(data, dict) or set(data) != {"schema", "book", "intents"}:
            raise ValueError("Unexpected V2 state structure")
        if data["schema"] != _SCHEMA or not isinstance(data["intents"], dict):
            raise ValueError("Invalid version or pending instructions")
        result = cls(Book.load(data["book"]), deepcopy(data["intents"]))
        for key, value in result.intents.items():
            plan = TradeIntent(**value["plan"])
            plan.validate()
            if key != plan.intent_id or value["status"] not in {
                "WATCHING", "QUEUED", "FILLED", "EXPIRED", "CANCELLED", "REJECTED"
            }:
                raise ValueError("Corrupt intent state")
        return result

    def submit(self, plan: TradeIntent, *, operator_approved: bool = False) -> None:
        """Save a contract, not an order; never silently interpret a rating."""
        if not isinstance(plan, TradeIntent):
            raise TypeError("Only structured TradeIntent objects can be submitted")
        if operator_approved is not True:
            raise ValueError("Human operator approval required in the V2 research sandbox")
        plan.validate()
        if plan.decision_date != self.book.last_session:
            raise ValueError("Plan must be submitted after that completed session")
        if plan.intent_id in self.intents:
            raise ValueError("Duplicate intent ID")
        if plan.ticker in self.book.positions or any(x["ticker"] == plan.ticker for x in self.book.orders):
            raise ValueError("There is already exposure or an order in this ticker")
        if any(x["plan"]["ticker"] == plan.ticker and x["status"] in {"WATCHING", "QUEUED"}
               for x in self.intents.values()):
            raise ValueError("An active entry plan already exists for this ticker")
        if self.book.halted:
            raise ValueError("Portfolio drawdown halt active")
        self.intents[plan.intent_id] = {"plan": asdict(plan), "status": "WATCHING",
                                        "consecutive": 0, "last_close_usd": None,
                                        "last_seen_date": plan.decision_date, "order_id": None}
        self.book._event(plan.decision_date, "V2_INTENT_ACCEPTED", ticker=plan.ticker,
                         intent_id=plan.intent_id, trigger_usd=plan.trigger_usd,
                         confirmation_sessions=plan.required_closes,
                         report_sha256=plan.report_sha256)

    def cancel(self, intent_id: str) -> bool:
        """Manual V2-only cancellation, logged without erasing history."""
        if intent_id not in self.intents:
            raise ValueError("Unknown intent ID")
        state = self.intents[intent_id]
        if state["status"] not in {"WATCHING", "QUEUED"}:
            return False
        order_id = state["order_id"]
        if order_id is not None:
            self.book.orders = [x for x in self.book.orders if x["id"] != order_id]
        state["status"] = "CANCELLED"
        self.book._event(self.book.last_session or self.book.started, "V2_INTENT_CANCELLED",
                         intent_id=intent_id, ticker=state["plan"]["ticker"])
        return True

    def advance(self, session: str, bars: dict[str, Bar], gbp_per_usd_open: float,
                gbp_per_usd_close: float, spy_close_usd: float,
                earnings_preopen: dict[str, EarningsSnapshot],
                earnings_afterclose: dict[str, EarningsSnapshot]) -> "ConditionalBook":
        """Replay exactly one daily session: open fills first, close triggers last.

        A two-close confirmation on dates T1/T2 queues the order at T2's close.
        It may fill at T3 OPEN only if still valid, not across a chase gap, and
        the independently verified earnings calendar permits it. Unknown data
        always fail closed (atomic: this instance never changes on failure).
        """
        _day(session)
        if session < self.book.started or (self.book.last_session and session <= self.book.last_session):
            raise ValueError("Session not strictly newer than the current book")
        active = [(id_, record, TradeIntent(**record["plan"])) for id_, record in self.intents.items()
                  if record["status"] in {"WATCHING", "QUEUED"}]
        required_symbols = {p.ticker for _, _, p in active} | set(self.book.positions)
        required_symbols |= {x["ticker"] for x in self.book.orders}
        missing = required_symbols - set(bars)
        if missing:
            raise ValueError(f"No valid bar for active plan/position: {sorted(missing)}")
        if any(not bars[t].valid() for t in required_symbols):
            raise ValueError("Invalid OHLC in an active plan/position")
        # Research at session close and order fills at the session open have
        # different as-of cutoffs. An after-close data fetch must NOT be used
        # retroactively to justify an earlier opening fill.
        for _, record, plan in active:
            # A queued order fills at OPEN: require only pre-open information.
            # Watching plans are evaluated at CLOSE: require only as-of-close.
            if record["status"] == "WATCHING" and plan.ticker not in earnings_afterclose:
                raise ValueError("Verified session-specific after-close earnings calendar missing")
            if record["status"] == "QUEUED" and plan.ticker not in earnings_preopen:
                raise ValueError("Verified session-specific pre-open earnings calendar missing")
        work = deepcopy(self)
        # Pre-open queued order gate: expire, earnings blackout, loss of breakout,
        # and excessive opening gap => no entry, before the old Book handles fills.
        for id_, _, plan in active:
            record = work.intents[id_]
            if record["status"] != "QUEUED":
                continue
            reason = None
            if session > plan.expiry_date:
                reason = "expired_before_open"
            elif not earnings_preopen[plan.ticker].safe(session, "preopen"):
                reason = "earnings_blackout_or_unverified"
            elif bars[plan.ticker].open < plan.trigger_usd:
                reason = "open_below_breakout_trigger"
            elif bars[plan.ticker].open > record["last_close_usd"] * (1 + plan.max_entry_gap_fraction):
                reason = "opening_gap_exceeded_limit"
            if reason:
                work.book.orders = [x for x in work.book.orders if x["id"] != record["order_id"]]
                record["status"] = "EXPIRED" if reason == "expired_before_open" else "REJECTED"
                work.book._event(session, "V2_ORDER_VETO", ticker=plan.ticker,
                                 intent_id=id_, reason=reason)
        # Reuse cash, FX, hard stops, P&L, slippage and drawdown accounting.
        before = len(work.book.events)
        work.book = work.book.step(session, bars, gbp_per_usd_open,
                                   gbp_per_usd_close, spy_close_usd)
        today_events = work.book.events[before:]
        for id_, _, plan in active:
            record = work.intents[id_]
            if record["status"] != "QUEUED":
                continue
            order_id = record["order_id"]
            if any(e.get("type") == "BUY_FILLED" and e.get("id") == order_id for e in today_events):
                record["status"] = "FILLED"
                work.book._event(session, "V2_INTENT_FILLED", ticker=plan.ticker, intent_id=id_)
            elif any(e.get("type") == "ORDER_REJECTED" and e.get("id") == order_id for e in today_events):
                record["status"] = "REJECTED"
                work.book._event(session, "V2_INTENT_REJECTED", ticker=plan.ticker, intent_id=id_)
        for id_, _, plan in active:
            record = work.intents[id_]
            if record["status"] != "WATCHING":
                continue
            if session > plan.expiry_date:
                record["status"] = "EXPIRED"
                work.book._event(session, "V2_INTENT_EXPIRED", ticker=plan.ticker, intent_id=id_)
                continue
            if work.book.halted or plan.ticker in work.book.positions:
                record["consecutive"] = 0
                continue
            if not earnings_afterclose[plan.ticker].safe(session, "afterclose"):
                record["consecutive"] = 0
                work.book._event(session, "V2_ENTRY_BLOCKED", ticker=plan.ticker,
                                 intent_id=id_, reason="earnings_calendar_or_blackout")
                continue
            price = bars[plan.ticker].close
            record["last_seen_date"] = session
            record["consecutive"] = record["consecutive"] + 1 if price > plan.trigger_usd else 0
            if record["consecutive"] < plan.required_closes or session == plan.decision_date:
                continue
            # Successful confirmation is still NOT an execution. Queue a
            # stricter-than-baseline BUY that may fill only at a later opening.
            order_id = work.book._id()
            order = {"id": order_id, "ticker": plan.ticker, "side": "BUY",
                     "created": session, "rating": plan.rating, "stop_usd": plan.stop_loss_usd,
                     "allocation_cap_fraction": plan.initial_allocation_fraction,
                     "max_holding_sessions": plan.max_holding_sessions,
                     "source_intent_id": id_, "sector": plan.sector}
            work.book.orders.append(order)
            work.book._event(session, "V2_CONDITIONAL_ORDER_QUEUED", **order)
            record["order_id"] = order_id
            record["last_close_usd"] = price
            record["status"] = "QUEUED"
        return work


def evidence_hash(report: str) -> str:
    """Reproducible digest of the exact original, unedited report payload."""
    return hashlib.sha256(report.encode("utf-8")).hexdigest()


def dump_v2(book: ConditionalBook) -> str:
    return json.dumps(book.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
