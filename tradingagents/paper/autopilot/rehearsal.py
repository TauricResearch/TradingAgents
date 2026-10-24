"""Isolated full trade-cycle REHEARSAL. All AI outputs, prices, FX and calendars
are SYNTHETIC test fixtures; not a forward trade or evidence of alpha.

Exercises REAL V3 policy, journal, dated earnings veto, close confirmation,
subsequent opening fill, overnight gap-stop accounting and SHA-256 provenance.
Never reads or writes an existing live or paper account.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingagents.paper.autopilot import runner
from tradingagents.paper.autopilot.decision import AIExecutionProposal, policy_intent
from tradingagents.paper.autopilot.state import atomic_write, create_new, read
from tradingagents.paper.conditional import EarningsSnapshot, evidence_hash
from tradingagents.paper.engine import Bar

DAYS = ("2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27")
TICKER = "KXDEMO"  # Fictional symbol
PM = ("Rating: Overweight. Initiate after TWO consecutive closes above $102.00. "
      "Use a firm stop-loss at $92.00 for the paper trade.")
TRADER = "**Stop Loss**: $92.00"
BARS = {
    DAYS[0]: Bar(99.5, 101, 99, 100),
    DAYS[1]: Bar(102.1, 105, 101, 104),
    DAYS[2]: Bar(104.2, 106, 103, 105),
    DAYS[3]: Bar(105.8, 108, 104, 107),
    DAYS[4]: Bar(88, 90, 85, 86),
}
NY = ZoneInfo("America/New_York")


def clock(day, hour=18, minute=10):
    return datetime.fromisoformat(
        f"{day}T{hour:02d}:{minute:02d}:00"
    ).replace(tzinfo=NY)


def quotes(_state, *, target):
    if target not in BARS:
        raise ValueError("No controlled quote for requested date")
    return {
        TICKER: {target: BARS[target]},
        "SPY": {target: Bar(600, 602, 599, 601)},
        "GBPUSD=X": {target: Bar(1.33, 1.34, 1.32, 1.33)},
    }, [target], lambda _bars, _day: (.75, .75)


def mock_calendar(_ticker, day, at):
    return EarningsSnapshot(
        day, "2026-12-15", "2026-07-21",
        "REHEARSAL_FAKE_CALENDAR_NEVER_USE_FOR_LIVE_ORDERS",
        True, at.astimezone(timezone.utc).isoformat(),
    )


def mock_ai(_model, *, ticker, session, bar, root, state):
    if ticker != TICKER or session != DAYS[0]:
        raise ValueError("Unexpected mock AI source date")
    report = json.dumps({
        "source": "MOCK_AI_NOT_REAL_LLM", "ticker": ticker,
        "session": session, "close_usd": bar.close,
        "portfolio_manager": PM, "trader": TRADER,
        "rating": "Overweight", "synthetic": True,
    }, sort_keys=True, indent=2) + "\n"
    location = root / "reports" / session / ticker
    location.mkdir(parents=True, exist_ok=False)
    (location / "source.json").write_text(report, encoding="utf-8")
    proposal = AIExecutionProposal(
        action="CONDITIONAL_LONG", rating="Overweight",
        entry_quote="TWO consecutive closes above $102.00",
        stop_quote=TRADER, trigger_usd=102.0, stop_usd=92.0,
        required_closes=2, expiry_days=14, holding_sessions=20,
        allocation_fraction=.05, rationale="Synthetic close-confirmed setup",
    )
    plan = policy_intent(
        proposal, ticker=ticker, session=session, final_pm=PM,
        trader_plan=TRADER, report=report,
        close_usd=bar.close, sector="Technology",
    )
    return {
        "ticker": ticker, "session": session,
        "decision": "CONDITIONAL_LONG", "intent_id": plan.intent_id,
        "source_file": f"reports/{session}/{ticker}/source.json",
        "source_sha256": evidence_hash(report),
        "model": "DETERMINISTIC_MOCK",
    }, plan, report


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_output(destination: Path) -> Path:
    folder = destination.expanduser().resolve()
    paper = (Path.home() / ".tradingagents" / "paper").resolve()
    if folder == paper or paper in folder.parents:
        raise ValueError("Rehearsal must not access actual paper accounts")
    if folder.exists():
        raise ValueError("Rehearsal destination already exists; choose a NEW folder")
    return folder


def run_rehearsal(destination: Path) -> dict:
    """One complete mock trade and immutable raw evidence bundle."""
    folder = safe_output(destination)
    folder.mkdir(parents=True, exist_ok=False)
    account = folder / "portfolio.json"
    create_new(account, DAYS[0], [TICKER])
    runner.mark_closed_sessions(account, now=clock(DAYS[0]), loader=quotes)
    state = read(account)
    state.set_running(True)  # Isolated REHEARSAL account, never V3.1 real paper
    atomic_write(account, state)
    outcome = runner.afterclose_research(
        account, now=clock(DAYS[0]), loader=quotes,
        graph_factory=lambda root: object(), research_fn=mock_ai,
        max_analyses=1,
    )
    assert outcome["conditional_intents"] == 1
    state = read(account)
    receipt = state.ai_receipts[DAYS[0] + ":" + TICKER]
    ident = receipt["intent_id"]
    contract = state.portfolio.intents[ident]["plan"]
    assert not state.portfolio.book.orders

    for confirmations, day in enumerate(DAYS[1:3], start=1):
        runner.snapshot_phase(
            account, phase="preclose", now=clock(day, 17, 10),
            fetcher=mock_calendar,
        )
        runner.mark_closed_sessions(account, now=clock(day), loader=quotes)
        state = read(account)
        item = state.portfolio.intents[ident]
        assert item["consecutive"] == confirmations
        assert (item["status"] == "QUEUED") == (confirmations == 2)
        assert not state.portfolio.book.positions

    runner.snapshot_phase(
        account, phase="preopen", now=clock(DAYS[3], 9, 15),
        fetcher=mock_calendar,
    )
    runner.mark_closed_sessions(account, now=clock(DAYS[3]), loader=quotes)
    state = read(account)
    buys = [e for e in state.portfolio.book.events if e["type"] == "BUY_FILLED"]
    assert len(buys) == 1 and state.portfolio.intents[ident]["status"] == "FILLED"
    assert TICKER in state.portfolio.book.positions
    assert not state.portfolio.book.orders

    runner.mark_closed_sessions(account, now=clock(DAYS[4]), loader=quotes)
    state = read(account)
    exits = state.portfolio.book.completed
    assert len(exits) == 1 and exits[0]["reason"] == "STOP"
    assert exits[0]["exit_usd"] < contract["stop_loss_usd"]
    assert exits[0]["pnl_gbp"] < 0
    assert not state.portfolio.book.positions
    assert not state.portfolio.book.orders

    source = folder / receipt["source_file"]
    assert sha(source) == receipt["source_sha256"] == contract["report_sha256"]
    kinds = {e["type"] for e in state.portfolio.book.events}
    expected = {"BUY_FILLED", "SELL_FILLED", "V3_MACHINE_POLICY_ACCEPTED",
                "V2_CONDITIONAL_ORDER_QUEUED", "V2_INTENT_FILLED"}
    assert expected <= kinds
    assert len([e for e in state.audit if e["kind"] == "SESSION_MARKED"]) == 5
    assert any(e["kind"] == "AI_RESEARCH_RECEIPT" and
               e["details"]["receipt"]["ticker"] == TICKER for e in state.audit)
    all_files = sorted(
        p for p in folder.rglob("*") if p.is_file()
        and p.name not in ("AUDIT_MANIFEST.json", "SUMMARY.md")
    )
    manifest = {
        "schema": "koral-e2e-rehearsal-v1",
        "classification": "SYNTHETIC_CONTROLLED_NOT_FORWARD_PERFORMANCE",
        "real_money_exposure_gbp": 0, "broker_connected": False,
        "real_llm_called": False, "live_prices_used": False,
        "ticker": TICKER, "sessions": list(DAYS),
        "source_sha256": receipt["source_sha256"], "intent_id": ident,
        "audit_event_types": sorted(kinds),
        "files_sha256": {p.relative_to(folder).as_posix(): sha(p) for p in all_files},
        "entry": buys[0], "exit": exits[0],
        "pnl_gbp": exits[0]["pnl_gbp"],
        "equity_gbp": round(state.portfolio.book.equity(), 2),
        "last_session": state.portfolio.book.last_session,
        "open_positions": len(state.portfolio.book.positions),
        "pending_orders": len(state.portfolio.book.orders),
        "warning": "All inputs are synthetic. DO NOT count as forward returns.",
    }
    (folder / "AUDIT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (folder / "SUMMARY.md").write_text(
        "# Koral Equities — Synthetic full paper trade lifecycle\n\n"
        "**MOCK AI AND INVENTED PRICES. NOT A LIVE FORWARD TRADE.**\n\n"
        "- Decision: 21 October. Confirmed completed closes: 22 and 23 October.\n"
        "- Conditional entry queued: 23 October. Simulated open fill: 26 October.\n"
        "- Overnight gap below stop, worse opening exit: 27 October.\n"
        "- Modelled simulated P&L: GBP " + str(exits[0]["pnl_gbp"]) + "\n"
        "- Rehearsal equity: GBP " + str(manifest["equity_gbp"]) + "\n"
        "- SHA-256 proof and complete local audit in AUDIT_MANIFEST.json.\n",
        encoding="utf-8",
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="SYNTHETIC trade rehearsal; NEVER genuine forward P&L",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = run_rehearsal(args.output)
    except (ValueError, KeyError, OSError, TypeError, AssertionError) as exc:
        parser.exit(2, f"REHEARSAL BLOCKED: {exc}\n")
    print(json.dumps({
        "status": "CONTROLLED_REHEARSAL_PASSED",
        "real_forward_trade": False,
        "pnl_gbp": manifest["pnl_gbp"],
        "equity_gbp": manifest["equity_gbp"],
        "manifest": str(args.output / "AUDIT_MANIFEST.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
