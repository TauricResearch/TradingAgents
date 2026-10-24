"""Independent live-source dry run: genuine observed market data, NO orders.

Reads existing observer evidence and may request actual multi-agent research in
an eligible same-session NY close window. Does not load, mutate, or initialise
ANY paper portfolio. No buy/sell/signal API is imported or invoked.

A historical observation inspected later is explicitly RETROSPECTIVE. It cannot
be used as a forward research decision or a basis for simulated fills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingagents.paper.autopilot import observe
from tradingagents.paper.autopilot.state import V3State, normalize_tickers
from tradingagents.paper.conditional import EarningsSnapshot, evidence_hash
from tradingagents.paper.engine import Bar

NY = ZoneInfo("America/New_York")
MARKET_SOURCE = "YAHOO_SECONDARY_NOT_EXCHANGE_CERTIFIED"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Missing UTC provenance timestamp")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid UTC provenance timestamp") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError("Source timestamp must be explicitly UTC")
    return result


def _asof(session: str) -> date:
    try:
        day = date.fromisoformat(session)
    except ValueError as exc:
        raise ValueError("Invalid session date") from exc
    if day.isoformat() != session or day.weekday() >= 5:
        raise ValueError("Session must be a canonical US-market weekday")
    return day


def _strict_bar(raw: object, symbol: str) -> Bar:
    if not isinstance(raw, dict) or set(raw) != {"open", "high", "low", "close"}:
        raise ValueError(f"Unrecognised OHLC schema for {symbol}")
    if any(type(x) not in (int, float) for x in raw.values()):
        raise ValueError(f"Non-numeric OHLC for {symbol}")
    bar = Bar(**raw)
    if not bar.valid():
        raise ValueError(f"Invalid completed OHLC for {symbol}")
    return bar


def read_observation(observer: Path, session: str, tickers: list[str], now: datetime) -> dict:
    """Validate immutable real-source files, as-of dates and risk evidence."""
    day = _asof(session)
    names = normalize_tickers(tickers, cap=3)
    home = observe.observation_home(observer)
    market = home / "market" / (session + ".json")
    if not market.is_file():
        raise ValueError(f"Completed observation missing for {session}; do not invent prices")
    market_raw = market.read_bytes()
    m = json.loads(market_raw)
    if not isinstance(m, dict) or m.get("schema") != "koral-observation-v1":
        raise ValueError("Unknown or corrupt market observation schema")
    if (m.get("mode") != "OBSERVE_ONLY" or m.get("orders") != [] or
            m.get("source") != MARKET_SOURCE or m.get("session") != session or
            m.get("phase") != "close" or
            m.get("corporate_actions") != "QUERIED_NO_UNMODELLED_EVENTS_REPORTED"):
        raise ValueError("Market evidence has inconsistent provenance or corporate actions")
    start = _utc(m.get("capture_started_utc"))
    completed = _utc(m.get("capture_completed_utc"))
    start_ny = start.astimezone(NY)
    if (completed < start or completed > now or completed-start > timedelta(minutes=90) or
            start_ny.date() != day or start_ny.time() < time(17, 40)):
        raise ValueError("Market observation was premature, future-dated or incomplete")
    bars = m.get("ohlc_usd")
    if not isinstance(bars, dict):
        raise ValueError("Missing observed stock-price records")
    required = set(names) | {"SPY"}
    if not required.issubset(bars):
        raise ValueError(f"Missing mandatory market instruments: {sorted(required - set(bars))}")
    if set(bars) != required:
        raise ValueError("Archived market watchlist does not exactly match requested tickers")
    parsed = {symbol: _strict_bar(bars[symbol], symbol) for symbol in sorted(required)}
    fx0, fx1 = m.get("fx_gbp_per_usd_open"), m.get("fx_gbp_per_usd_close")
    if (type(fx0) not in (int, float) or type(fx1) not in (int, float) or
            not .3 <= fx0 <= 2 or not .3 <= fx1 <= 2 or abs(fx1 / fx0 - 1) > .05):
        raise ValueError("Unreliable GBP conversion in observed market source")
    source = home / "calendar" / session / "preclose.json"
    calendar_raw = source.read_bytes() if source.is_file() else None
    records: dict[str, dict] = {}
    c = None
    if calendar_raw is not None:
        try:
            c = json.loads(calendar_raw)
            if (not isinstance(c, dict) or c.get("session") != session or
                    c.get("phase") != "preclose" or
                    c.get("source_policy") != "TWO_SECONDARY_FEEDS_MUST_AGREE_OR_BLOCK"):
                raise ValueError("Unexpected earnings-calendar provenance")
            if (not isinstance(c.get("earnings"), dict) or
                    set(c["earnings"]) != set(names)):
                raise ValueError("Archived earnings watchlist mismatch")
            envelope_utc = _utc(c.get("observed_utc"))
            observed = envelope_utc.astimezone(NY)
            if (observed.date() != day or
                    not time(17, 0) <= observed.time() <= time(17, 25) or
                    envelope_utc > now or envelope_utc > start):
                raise ValueError("Calendar was captured outside its original cutoff")
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            c = None
    for symbol in names:
        status = {"status": "NO_TRADE", "reason": "EARNINGS_EVIDENCE_MISSING_OR_INVALID",
                  "eligible_for_research": False, "price_close_usd": parsed[symbol].close}
        try:
            if c is None or not isinstance(c.get("earnings"), dict):
                raise ValueError("Unverified earnings source")
            raw = c["earnings"][symbol]
            if not isinstance(raw, dict) or set(raw) != {
                "asof_date", "next_earnings_date", "last_earnings_date",
                "source", "verified", "observed_at_utc",
            }:
                raise ValueError("Missing earnings timestamp or exact source fields")
            earnings = EarningsSnapshot(**raw)
            # A report cannot contain observations made AFTER the file claims
            # it was captured. safe() checks the phase cutoff, not this earlier
            # immutable snapshot boundary.
            if _utc(earnings.observed_at_utc) > envelope_utc:
                raise ValueError("Earnings observation postdates its archived snapshot")
            if (earnings.verified is not True or
                    earnings.source != "YAHOO+NASDAQ_CONSENSUS_SECONDARY"):
                raise ValueError("Earnings sources did not agree")
            status["next_earnings_date"] = earnings.next_earnings_date
            status["last_earnings_date"] = earnings.last_earnings_date
            if not earnings.safe(session, "afterclose"):
                status["reason"] = "EARNINGS_BLACKOUT_OR_BAD_ASOF_CUTOFF"
            else:
                status["reason"] = "SECONDARY_EARNINGS_GATE_PASSED"
                status["eligible_for_research"] = True
        except (ValueError, TypeError, KeyError):
            pass
        records[symbol] = status
    return {
        "session": session, "watchlist": names, "bars": parsed,
        "market_source_bytes": market_raw, "calendar_source_bytes": calendar_raw,
        "market_sha256": _sha(market_raw),
        "calendar_sha256": _sha(calendar_raw) if calendar_raw is not None else None,
        "fx_gbp_per_usd": [fx0, fx1], "tickers": records,
        "capture_completed_utc": completed.isoformat(),
    }


def _dry_run_output(path: Path, observer: Path) -> Path:
    destination = path.expanduser().resolve()
    paper = (Path.home() / ".tradingagents" / "paper").resolve()
    observation = observer.expanduser().resolve()
    if (destination == paper or paper in destination.parents or
            destination == observation or observation in destination.parents):
        raise ValueError("Dry-run outputs must not overlap paper portfolios or observations")
    if destination.exists():
        raise ValueError("Dry-run output already exists; choose a NEW folder")
    return destination


def run_dry_run(
    output: Path, observer: Path, session: str, tickers: list[str], *,
    ai_count: int = 0, now: datetime | None = None,
    graph_factory=None, research_fn=None,
) -> dict:
    """One source-backed evidence audit, optionally a REAL forward AI dry run.

    No calls to a ledger reader/writer, no submitted intent, no orders.
    A historical snapshot may be audited, but can NEVER be used to issue a
    backdated model decision. Real AI requires the SAME NY date after close.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Dry-run clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if type(ai_count) is not int or not 0 <= ai_count <= 3:
        raise ValueError("AI budget must be between zero and three")
    names = normalize_tickers(tickers, cap=3)
    data = read_observation(observer, session, names, now)
    live = now.astimezone(NY).date() == _asof(session)
    if ai_count and not live:
        raise ValueError("Historical observations cannot be treated as forward AI decisions")
    if ai_count and now.astimezone(NY).time() < time(17, 40):
        raise ValueError("AI may read completed daily data only after 17:40 NY")
    folder = _dry_run_output(output, observer)
    folder.mkdir(parents=True, exist_ok=False)
    original = folder / "original_sources"
    original.mkdir()
    (original / "market.json").write_bytes(data["market_source_bytes"])
    if data["calendar_source_bytes"] is not None:
        (original / "preclose.json").write_bytes(data["calendar_source_bytes"])
    decisions = dict(data["tickers"])
    model_invoked = False
    if ai_count:
        from tradingagents.paper.autopilot import runner
        # An ephemeral ZERO-EXPOSURE memory object, NEVER saved to a paper book.
        ephemeral = V3State.new(session, names)
        ephemeral.portfolio.book.last_session = session
        selected = [ticker for ticker in names if decisions[ticker]["eligible_for_research"]][:ai_count]
        graph = None
        factory = graph_factory or runner._graph_factory
        analyse = research_fn or runner._research_one
        for ticker in selected:
            status = decisions[ticker]
            model_invoked = True
            try:
                if graph is None:
                    graph = factory(folder)
                receipt, plan, research = analyse(
                    graph, ticker=ticker, session=session,
                    bar=data["bars"][ticker], root=folder, state=ephemeral,
                )
                path = folder / "reports" / session / ticker / "source.json"
                if (not path.is_file() or _sha(path.read_bytes()) != evidence_hash(research)
                        or receipt.get("source_sha256") != evidence_hash(research)):
                    raise ValueError("Actual model report failed source-byte provenance")
                status["ai_receipt"] = receipt
                if plan is None:
                    status["reason"] = "AI_POLICY_REJECTED_OR_NO_COMPLETE_INSTRUCTION"
                else:
                    plan.validate()
                    if (plan.ticker != ticker or plan.decision_date != session or
                            plan.report_sha256 != evidence_hash(research)):
                        raise ValueError("Plan does not match exact report and session")
                    status["reason"] = "CONDITIONAL_PLAN_DIAGNOSTIC_ONLY"
                    status["conditional_plan"] = {
                        "intent_id": plan.intent_id, "trigger_usd": plan.trigger_usd,
                        "required_closes": plan.required_closes,
                        "stop_loss_usd": plan.stop_loss_usd,
                        "expiry_date": plan.expiry_date,
                        "max_holding_sessions": plan.max_holding_sessions,
                        "allocation_fraction": plan.initial_allocation_fraction,
                        "report_sha256": plan.report_sha256,
                        "approved": False, "submitted": False,
                    }
            except Exception as exc:
                status["reason"] = f"AI_OR_PROVENANCE_FAILED_{type(exc).__name__}"
            status["status"] = "RESEARCH_ONLY_NO_ORDERS"
    manifest = {
        "schema": "koral-real-market-dry-run-v1", "mode": "NO_ORDERS",
        "classification": (
            "RETROSPECTIVE_SOURCE_AUDIT_NOT_FORWARD_RESEARCH" if not live
            else "SAME_SESSION_REAL_AI_DRY_RUN_NOT_FORWARD_TRADE" if model_invoked
            else "SAME_SESSION_NO_ELIGIBLE_AI_BLOCKED_NO_TRADE" if ai_count
            else "SAME_SESSION_MARKET_SOURCE_AUDIT_ONLY"
        ),
        "session": session, "audit_generated_utc": now.isoformat(),
        "completed_capture_utc": data["capture_completed_utc"],
        "source_vendor": MARKET_SOURCE, "source_issuer_verified": False,
        "model_external_source_timestamps_fully_audited": False,
        "real_market_prices_used": True, "real_ai_attempted": model_invoked,
        "account_reads": 0, "account_writes": 0, "paper_orders_created": 0,
        "broker_connected": False,
        "source_hashes": {
            "original_sources/market.json": data["market_sha256"],
            **({"original_sources/preclose.json": data["calendar_sha256"]}
               if data["calendar_sha256"] else {}),
        },
        "fx_gbp_per_usd": data["fx_gbp_per_usd"],
        "research": decisions,
        "notice": ("Earnings flags are agreement between two SECONDARY vendors, not certified "
                   "company evidence. This run cannot open, queue, or authorise a trade."),
    }
    manifest["audit_files_sha256"] = {
        p.relative_to(folder).as_posix(): _sha(p.read_bytes())
        for p in folder.rglob("*") if p.is_file()
    }
    (folder / "DRY_RUN_MANIFEST.json").write_bytes(
        (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    )
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="koral-equities-real-data-dry-run",
        description="Read genuine captured market observations. Optional real AI, NEVER any order.",
    )
    parser.add_argument("--observer", type=Path, default=observe.DEFAULT_OBSERVATION_HOME)
    parser.add_argument("--session", required=True, help="Observed NY market session YYYY-MM-DD")
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "NVDA"])
    parser.add_argument("--ai", type=int, default=0, choices=(0, 1, 2, 3),
                        help="Real LLM analyses (same NY session after 17:40 only)")
    parser.add_argument("--output", type=Path, required=True, help="NEW, independent audit folder")
    args = parser.parse_args(argv)
    try:
        summary = run_dry_run(args.output, args.observer, args.session, args.tickers,
                              ai_count=args.ai)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"LIVE-SOURCE DRY RUN BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    print(json.dumps({
        "status": "SOURCE_AUDIT_ONLY_NO_ORDERS", "classification": summary["classification"],
        "session": summary["session"], "model_attempted": summary["real_ai_attempted"],
        "results": {k: v["reason"] for k, v in summary["research"].items()},
        "manifest": str(args.output / "DRY_RUN_MANIFEST.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
