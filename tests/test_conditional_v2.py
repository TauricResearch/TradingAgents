"""V2 deterministic execution tests: no LLM, vendor, network or real brokerage."""

import pytest

from tradingagents.paper.conditional import (
    ConditionalBook, EarningsSnapshot, TradeIntent, dump_v2, evidence_hash,
)
from tradingagents.paper.engine import Bar

START = "2026-10-21"
DAY1 = "2026-10-22"
DAY2 = "2026-10-23"
DAY3 = "2026-10-26"
DAY4 = "2026-10-27"


def mkbar(price=229, close=None, low=None, high=None):
    c = price if close is None else close
    l = min(price, c) - 1 if low is None else low
    h = max(price, c) + 1 if high is None else high
    return Bar(price, h, l, c)


def safe(d, next_date="2026-12-01", phase="afterclose", last_date="2026-08-01"):
    from datetime import datetime, time, timezone
    from zoneinfo import ZoneInfo

    hour = time(8, 30) if phase == "preopen" else time(17, 5)
    local = datetime.combine(datetime.fromisoformat(d).date(), hour,
                             tzinfo=ZoneInfo("America/New_York"))
    return {"NVDA": EarningsSnapshot(d, next_date, last_date, "provider:audit", True,
                                      local.astimezone(timezone.utc).isoformat())}


def open_calendar(d, next_date="2026-12-01"):
    return safe(d, next_date, phase="preopen")



def new_book():
    b = ConditionalBook.new(START)
    return b.advance(START, {}, .75, .75, 600, {}, {})


def plan(**kwargs):
    raw = dict(
        intent_id="KEI-NVDA_001", ticker="NVDA", decision_date=START,
        expiry_date="2026-11-10", rating="Overweight", side="ENTER_LONG",
        entry_rule="CLOSES_ABOVE", trigger_usd=226.87, required_closes=2,
        stop_loss_usd=212.16, stop_is_executable=True,
        initial_allocation_fraction=.10, max_holding_sessions=20,
        max_entry_gap_fraction=.03, sector="Information Technology",
        report_sha256=evidence_hash("Synthetic approved conditional mandate"),
    )
    return TradeIntent(**(raw | kwargs))


def test_overweight_does_not_enter_before_two_completed_closes():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    assert b.book.orders == [] and b.book.positions == {}
    b = b.advance(DAY1, {"NVDA": mkbar(227.9, close=228)}, .75, .75, 602, open_calendar(DAY1), safe(DAY1))
    assert b.book.orders == [] and b.book.positions == {}
    b = b.advance(DAY2, {"NVDA": mkbar(229, close=230)}, .75, .75, 605, open_calendar(DAY2), safe(DAY2))
    assert len(b.book.orders) == 1 and b.book.positions == {}
    assert b.book.orders[0]["created"] == DAY2
    assert b.book.orders[0]["stop_usd"] == 212.16
    assert b.book.orders[0]["allocation_cap_fraction"] == .10
    b = b.advance(DAY3, {"NVDA": mkbar(230.6, close=231)}, .75, .75, 604, open_calendar(DAY3), safe(DAY3))
    assert len(b.book.orders) == 0
    assert "NVDA" in b.book.positions
    p = b.book.positions["NVDA"]
    assert p["cost_gbp"] <= 1000.01
    assert p["planned_risk_gbp"] <= 200.01
    assert p["stop_usd"] == 212.16
    assert p["max_holding_sessions"] == 20
    assert b.intents["KEI-NVDA_001"]["status"] == "FILLED"


def test_break_in_consecutive_closes_resets_confirmation():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    for date, close in [(DAY1, 229), (DAY2, 223), (DAY3, 230)]:
        b = b.advance(date, {"NVDA": mkbar(close)}, .75, .75, 602, open_calendar(date), safe(date))
    assert b.intents["KEI-NVDA_001"]["consecutive"] == 1
    assert b.book.orders == []


def test_gap_chase_is_vetoed_before_any_fill():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    for d, c in [(DAY1, 228), (DAY2, 230)]:
        b = b.advance(d, {"NVDA": mkbar(c)}, .75, .75, 600, open_calendar(d), safe(d))
    out = b.advance(DAY3, {"NVDA": mkbar(250)}, .75, .75, 601, open_calendar(DAY3), safe(DAY3))
    assert out.book.positions == {}
    assert out.book.orders == []
    assert out.intents["KEI-NVDA_001"]["status"] == "REJECTED"
    assert any(e["type"] == "V2_ORDER_VETO" and e["reason"] == "opening_gap_exceeded_limit"
               for e in out.book.events)


def test_breakout_fails_at_next_open_and_does_not_buy():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    for d, c in [(DAY1, 228), (DAY2, 230)]:
        b = b.advance(d, {"NVDA": mkbar(c)}, .75, .75, 600, open_calendar(d), safe(d))
    out = b.advance(DAY3, {"NVDA": mkbar(222)}, .75, .75, 601, open_calendar(DAY3), safe(DAY3))
    assert not out.book.positions
    assert any(e.get("reason") == "open_below_breakout_trigger" for e in out.book.events)


def test_earnings_blackout_blocks_new_intents_without_making_up_dates():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    event_next_week = "2026-10-26"
    for day in (DAY1, DAY2):
        b = b.advance(day, {"NVDA": mkbar(230)}, .75, .75, 600,
                      open_calendar(day, event_next_week), safe(day, event_next_week))
    assert not b.book.orders and not b.book.positions
    assert b.intents["KEI-NVDA_001"]["consecutive"] == 0
    assert any(e["type"] == "V2_ENTRY_BLOCKED" for e in b.book.events)


def test_unverified_or_missing_calendar_fails_closed_atomically():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    before = dump_v2(b)
    with pytest.raises(ValueError, match="calendar missing"):
        b.advance(DAY1, {"NVDA": mkbar()}, .75, .75, 600, {}, {})
    assert dump_v2(b) == before
    no_event = {"NVDA": EarningsSnapshot(DAY1, None, "2026-08-01", "provider", True,
                                           safe(DAY1)["NVDA"].observed_at_utc)}
    b2 = b.advance(DAY1, {"NVDA": mkbar()}, .75, .75, 600, open_calendar(DAY1), no_event)
    assert not b2.book.orders
    assert any(e["type"] == "V2_ENTRY_BLOCKED" for e in b2.book.events)


def test_expiry_prevents_late_entry_or_fill():
    b = new_book()
    b.submit(plan(expiry_date=DAY1, required_closes=1), operator_approved=True)
    b = b.advance(DAY1, {"NVDA": mkbar(230)}, .75, .75, 600, open_calendar(DAY1), safe(DAY1))
    assert b.book.orders
    b = b.advance(DAY2, {"NVDA": mkbar(231)}, .75, .75, 600, open_calendar(DAY2), safe(DAY2))
    assert not b.book.orders and not b.book.positions
    assert b.intents["KEI-NVDA_001"]["status"] == "EXPIRED"


def test_earnings_announced_before_fill_blocks_queued_order():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    for day in (DAY1, DAY2):
        b = b.advance(day, {"NVDA": mkbar(230)}, .75, .75, 600, open_calendar(day), safe(day))
    b = b.advance(DAY3, {"NVDA": mkbar(231)}, .75, .75, 600,
                  open_calendar(DAY3, "2026-10-30"), safe(DAY3, "2026-10-30"))
    assert not b.book.positions and not b.book.orders
    assert any(e.get("reason") == "earnings_blackout_or_unverified" for e in b.book.events)


def test_bad_ohlc_and_missing_symbol_fail_without_touching_book():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    initial = dump_v2(b)
    with pytest.raises(ValueError, match="Invalid OHLC"):
        b.advance(DAY1, {"NVDA": Bar(230, 229, 220, 231)}, .75, .75, 600, open_calendar(DAY1), safe(DAY1))
    with pytest.raises(ValueError, match="No valid bar"):
        b.advance(DAY1, {}, .75, .75, 600, open_calendar(DAY1), safe(DAY1))
    assert dump_v2(b) == initial


def test_rating_alone_is_never_accepted_as_an_executable_plan():
    b = new_book()
    with pytest.raises(TypeError):
        b.submit("Overweight", operator_approved=True)
    with pytest.raises(ValueError, match="Human operator approval"):
        b.submit(plan())
    with pytest.raises(ValueError, match="approved stop"):
        b.submit(plan(stop_is_executable=False), operator_approved=True)
    with pytest.raises(ValueError, match="approved"):
        b.submit(plan(source="MODEL_FREE_TEXT"), operator_approved=True)
    assert not b.book.orders


def test_invalid_risk_contract_is_refused():
    modifications = [
        dict(initial_allocation_fraction=.33), dict(stop_loss_usd=230),
        dict(required_closes=0), dict(max_holding_sessions=127),
        dict(max_entry_gap_fraction=.10), dict(decision_date="2026-10-27"),
        dict(ticker="nvda"), dict(expiry_date="2026-12-20"),
        dict(report_sha256="not a report hash"), dict(sector=""),
    ]
    for change in modifications:
        b = new_book()
        with pytest.raises(ValueError):
            b.submit(plan(**change), operator_approved=True)
    assert b.book.orders == []


def test_duplicate_plans_and_cancellation_are_audited():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    with pytest.raises(ValueError, match="Duplicate"):
        b.submit(plan(), operator_approved=True)
    with pytest.raises(ValueError, match="active entry"):
        b.submit(plan(intent_id="KEI-NVDA_002"), operator_approved=True)
    assert b.cancel("KEI-NVDA_001") is True
    assert b.cancel("KEI-NVDA_001") is False
    assert any(e["type"] == "V2_INTENT_CANCELLED" for e in b.book.events)
    assert not b.book.orders


def test_serialisation_roundtrip_rejects_tampered_rules():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    data = b.to_dict()
    out = ConditionalBook.from_dict(data)
    assert dump_v2(out) == dump_v2(b)
    data["book"]["rules"]["risk_fraction"] = 1.0
    with pytest.raises(ValueError, match="Unrecognized risk configuration"):
        ConditionalBook.from_dict(data)


def test_no_same_close_execution_and_no_hindsight_processing():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    with pytest.raises(ValueError, match="not strictly newer"):
        b.advance(START, {"NVDA": mkbar(230)}, .75, .75, 600, open_calendar(START), safe(START))
    assert not b.book.positions


def test_preopen_rejects_earnings_data_that_only_arrived_after_the_open():
    b = new_book()
    b.submit(plan(), operator_approved=True)
    for date in (DAY1, DAY2):
        b = b.advance(date, {"NVDA": mkbar(230)}, .75, .75, 600,
                      open_calendar(date), safe(date))
    # Passing the 17:05 after-close quote as "pre-open" cannot authorize a fill.
    b = b.advance(DAY3, {"NVDA": mkbar(231)}, .75, .75, 600,
                  safe(DAY3), safe(DAY3))
    assert not b.book.positions
    assert any(e.get("reason") == "earnings_blackout_or_unverified" for e in b.book.events)


def test_stale_earnings_snapshot_never_authorises_new_order():
    b = new_book()
    b.submit(plan(required_closes=1), operator_approved=True)
    outdated = safe(DAY1)
    observed = outdated["NVDA"]
    from dataclasses import replace
    outdated["NVDA"] = replace(observed, observed_at_utc="2026-10-21T20:00:00+00:00")
    b = b.advance(DAY1, {"NVDA": mkbar(230)}, .75, .75, 600,
                  open_calendar(DAY1), outdated)
    assert not b.book.orders
    assert any(e["type"] == "V2_ENTRY_BLOCKED" for e in b.book.events)


def test_max_holding_period_override_applies_to_filled_trade():
    b = new_book()
    b.submit(plan(required_closes=1, max_holding_sessions=1), operator_approved=True)
    b = b.advance(DAY1, {"NVDA": mkbar(230)}, .75, .75, 600,
                  open_calendar(DAY1), safe(DAY1))
    b = b.advance(DAY2, {"NVDA": mkbar(230)}, .75, .75, 600,
                  open_calendar(DAY2), safe(DAY2))
    assert "NVDA" in b.book.positions
    assert b.book.positions["NVDA"]["max_holding_sessions"] == 1
    assert any(o["side"] == "SELL" and o["ticker"] == "NVDA" for o in b.book.orders)
    b = b.advance(DAY3, {"NVDA": mkbar(231)}, .75, .75, 600,
                  open_calendar(DAY3), safe(DAY3))
    assert "NVDA" not in b.book.positions
    assert b.book.completed and b.book.completed[-1]["reason"] == "SIGNAL"


def test_v2_offline_cli_requires_exact_report_hash_and_no_legacy_state(tmp_path):
    import json
    from tradingagents.paper.conditional_cli import main, _read
    path = tmp_path / "v2.json"
    assert main(["--state", str(path), "init", "--start", START]) == 0
    report = tmp_path / "research.txt"
    report.write_text("A properly reviewed fictional mandate", encoding="utf-8")
    draft = plan(report_sha256=evidence_hash(report.read_text()))
    file = tmp_path / "plan.json"
    from dataclasses import asdict
    file.write_text(json.dumps(asdict(draft)), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--state", str(path), "approve-plan", "--plan", str(file), "--report", str(report)])
    assert exc.value.code == 2
    # advance account to asof before introducing the plan
    payload = {"session": START, "bars": {}, "gbp_per_usd_open": .75,
               "gbp_per_usd_close": .75, "spy_close_usd": 600,
               "earnings_preopen": {}, "earnings_afterclose": {}}
    fixture = tmp_path / "start.json"
    fixture.write_text(json.dumps(payload))
    assert main(["--state", str(path), "replay-day", "--fixture", str(fixture)]) == 0
    assert main(["--state", str(path), "approve-plan", "--plan", str(file),
                 "--report", str(report), "--approve"]) == 0
    assert len(_read(path).intents) == 1
    assert not _read(path).book.orders


def test_immediate_post_earnings_entry_is_blocked():
    b = new_book()
    b.submit(plan(required_closes=1), operator_approved=True)
    # The release occurred on the same date as the completed session. The
    # next-session entry cannot ignore a post-earnings repricing blackout.
    after = safe(DAY1, last_date=DAY1)
    out = b.advance(DAY1, {"NVDA": mkbar(230)}, .75, .75, 600,
                    open_calendar(DAY1), after)
    assert not out.book.orders
    assert any(e["type"] == "V2_ENTRY_BLOCKED" for e in out.book.events)


def test_sector_cap_tightens_position_size_below_five_positions():
    from tradingagents.paper.engine import Book
    b = Book.new(START).step(START, {}, .75, .75, 600)
    assert b.submit_signal("AAPL", "Buy", 100, START, stop_fraction=.01)
    assert b.submit_signal("MSFT", "Buy", 100, START, stop_fraction=.01)
    for order in b.orders:
        order["sector"] = "Information Technology"
        order["allocation_cap_fraction"] = .30
    b = b.step(DAY1, {"AAPL": mkbar(100, close=100.5, low=99.5),
                      "MSFT": mkbar(100, close=100.5, low=99.5)}, .75, .75, 600)
    sector = [p for p in b.positions.values() if p["sector"] == "Information Technology"]
    exposure = sum(p["shares"] * p["mark_usd"] * p["mark_gbp_per_usd"] for p in sector)
    # Opening spend is bounded by 40%; the mark may move slightly after entry.
    assert sum(p["cost_gbp"] for p in sector) <= 4000.01
    assert exposure <= 4100
    assert len(sector) == 2


def test_calendar_timestamp_must_be_actual_utc_not_future_local_time():
    from dataclasses import replace
    quote = safe(DAY1)["NVDA"]
    assert quote.safe(DAY1, "afterclose")
    false_utc = replace(quote, observed_at_utc="2026-10-22T17:05:00-04:00")
    assert not false_utc.safe(DAY1, "afterclose")
    after_cutoff = replace(quote, observed_at_utc="2026-10-22T23:00:00+00:00")
    assert not after_cutoff.safe(DAY1, "afterclose")
