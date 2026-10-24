"""Offline source provenance checks for real-market dry-run; no network or ledger."""
import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from tradingagents.paper.autopilot import live_dry_run as dry
from tradingagents.paper.autopilot.decision import AIExecutionProposal, policy_intent
from tradingagents.paper.conditional import evidence_hash

DAY = "2026-10-23"
NY = ZoneInfo("America/New_York")


def at(hour, minute):
    return datetime(2026, 10, 23, hour, minute, tzinfo=NY)


def market():
    def b(o, h, l, c):
        return {"open": o, "high": h, "low": l, "close": c}
    return {
        "schema": "koral-observation-v1", "mode": "OBSERVE_ONLY",
        "session": DAY, "phase": "close", "orders": [],
        "source": "YAHOO_SECONDARY_NOT_EXCHANGE_CERTIFIED",
        "capture_started_utc": at(17, 40).astimezone(timezone.utc).isoformat(),
        "capture_completed_utc": at(17, 41).astimezone(timezone.utc).isoformat(),
        "ohlc_usd": {"AAPL": b(200, 204, 199, 202),
                     "MSFT": b(500, 504, 499, 502),
                     "NVDA": b(210, 213, 209, 211),
                     "SPY": b(600, 605, 598, 601)},
        "fx_gbp_per_usd_open": .74, "fx_gbp_per_usd_close": .741,
        "corporate_actions": "QUERIED_NO_UNMODELLED_EVENTS_REPORTED",
    }


def calendar():
    def e(symbol, good, next_date):
        return {
            "asof_date": DAY,
            "next_earnings_date": next_date if good else None,
            "last_earnings_date": "2026-07-30" if good else None,
            "source": "YAHOO+NASDAQ_CONSENSUS_SECONDARY" if good else "UNVERIFIED_EARNINGS_SOURCE",
            "verified": good,
            "observed_at_utc": at(17, 10).astimezone(timezone.utc).isoformat(),
        }
    return {
        "session": DAY, "phase": "preclose",
        "observed_utc": at(17, 10).astimezone(timezone.utc).isoformat(),
        "source_policy": "TWO_SECONDARY_FEEDS_MUST_AGREE_OR_BLOCK",
        "earnings": {"AAPL": e("AAPL", True, "2026-11-02"),
                     "MSFT": e("MSFT", True, "2026-10-28"),
                     "NVDA": e("NVDA", False, None)},
    }


def saved(tmp_path, *, m=None, c=None):
    root = tmp_path / "observations"
    (root / "market").mkdir(parents=True)
    (root / "calendar" / DAY).mkdir(parents=True)
    (root / "market" / (DAY + ".json")).write_bytes(
        (json.dumps(m if m is not None else market(), sort_keys=True) + "\n").encode()
    )
    if c is not False:
        (root / "calendar" / DAY / "preclose.json").write_bytes(
            (json.dumps(c if c is not None else calendar(), sort_keys=True) + "\n").encode()
        )
    return root


def test_real_source_audit_is_retroactive_and_never_trades(tmp_path):
    home = saved(tmp_path)
    result = dry.run_dry_run(tmp_path / "review", home, DAY, ["AAPL", "MSFT", "NVDA"],
                             now=datetime(2026,10,24,12,0,tzinfo=timezone.utc))
    assert result["classification"] == "RETROSPECTIVE_SOURCE_AUDIT_NOT_FORWARD_RESEARCH"
    assert result["account_reads"] == result["account_writes"] == result["paper_orders_created"] == 0
    assert result["real_ai_attempted"] is False
    assert result["research"]["AAPL"]["eligible_for_research"] is True
    assert result["research"]["MSFT"]["reason"] == "EARNINGS_BLACKOUT_OR_BAD_ASOF_CUTOFF"
    assert result["research"]["NVDA"]["reason"] == "EARNINGS_EVIDENCE_MISSING_OR_INVALID"
    assert result["source_hashes"]["original_sources/market.json"] == hashlib.sha256(
        (home / "market" / (DAY + ".json")).read_bytes()
    ).hexdigest()
    assert (tmp_path / "review" / "DRY_RUN_MANIFEST.json").is_file()


def test_historical_source_refuses_real_ai_and_does_not_create_folder(tmp_path):
    home = saved(tmp_path)
    with pytest.raises(ValueError, match="Historical observations"):
        dry.run_dry_run(tmp_path / "bad_ai", home, DAY, ["AAPL"], ai_count=1,
                        now=datetime(2026,10,24,12,0,tzinfo=timezone.utc))
    assert not (tmp_path / "bad_ai").exists()


def test_preclose_live_same_day_requires_completed_capture(tmp_path):
    home = saved(tmp_path)
    with pytest.raises(ValueError, match="future-dated"):
        dry.run_dry_run(tmp_path / "early", home, DAY, ["AAPL"], ai_count=1,
                        now=at(17, 40).astimezone(timezone.utc))
    assert not (tmp_path / "early").exists()


def test_missing_market_data_blocks_without_guessing(tmp_path):
    m = market()
    del m["ohlc_usd"]["MSFT"]
    home = saved(tmp_path, m=m)
    with pytest.raises(ValueError, match="Missing mandatory"):
        dry.read_observation(home, DAY, ["AAPL", "MSFT"], at(18,5).astimezone(timezone.utc))


def test_invalid_us_stock_ohlc_blocked(tmp_path):
    m = market()
    m["ohlc_usd"]["AAPL"]["high"] = 190
    home = saved(tmp_path, m=m)
    with pytest.raises(ValueError, match="Invalid completed OHLC"):
        dry.read_observation(home, DAY, ["AAPL"], at(18,5).astimezone(timezone.utc))


@pytest.mark.parametrize("fx",[float("nan"), 0, 4, .1])
def test_invalid_fx_is_rejected(tmp_path,fx):
    m = market()
    m["fx_gbp_per_usd_close"] = fx
    home = saved(tmp_path, m=m)
    with pytest.raises(ValueError, match="Unreliable GBP"):
        dry.read_observation(home, DAY, ["AAPL"], at(18,5).astimezone(timezone.utc))


def test_corrupt_unverified_calendar_does_not_become_yes(tmp_path):
    c = calendar()
    c["earnings"]["AAPL"]["next_earnings_date"] = None
    home = saved(tmp_path, c=c)
    result = dry.read_observation(home, DAY, ["AAPL"], at(18,5).astimezone(timezone.utc))
    assert not result["tickers"]["AAPL"]["eligible_for_research"]


def test_missing_calendar_is_no_trade_not_permission(tmp_path):
    home = saved(tmp_path, c=False)
    result = dry.read_observation(home, DAY, ["AAPL"], at(18,5).astimezone(timezone.utc))
    assert result["tickers"]["AAPL"]["reason"] == "EARNINGS_EVIDENCE_MISSING_OR_INVALID"


def test_output_never_overwrites_rehearsal_or_paper_state(tmp_path):
    home = saved(tmp_path)
    folder = tmp_path / "review"
    folder.mkdir()
    (folder / "portfolio.json").write_bytes(b"DO_NOT_CHANGE")
    with pytest.raises(ValueError, match="already exists"):
        dry.run_dry_run(folder,home,DAY,["AAPL"],now=at(18,5))
    assert (folder / "portfolio.json").read_bytes()==b"DO_NOT_CHANGE"


def test_ai_receipt_from_real_call_is_report_hash_bound_but_never_submitted(tmp_path):
    home = saved(tmp_path)
    pm = ("Rating: Overweight. Initiate after TWO consecutive closes above $205.00. "
          "Use a firm stop-loss at $190.00 for the paper trade.")
    trader = "**Stop Loss**: $190.00"
    received = []
    def fake_ai(_graph, *, ticker, session, bar, root, state):
        assert ticker == "AAPL"
        assert session == DAY
        assert state.portfolio.book.orders == []
        received.append(ticker)
        report = json.dumps({"pm":pm,"trader":trader,"ticker":ticker},sort_keys=True)+"\n"
        dest=root/"reports"/session/ticker
        dest.mkdir(parents=True)
        (dest/"source.json").write_bytes(report.encode())
        typed=AIExecutionProposal(
            action="CONDITIONAL_LONG", rating="Overweight",
            entry_quote="TWO consecutive closes above $205.00",
            stop_quote=trader, trigger_usd=205., stop_usd=190., required_closes=2,
            expiry_days=14, holding_sessions=20,
            allocation_fraction=.05, rationale="Controlled mock for DRY-RUN test",
        )
        plan=policy_intent(typed,ticker=ticker,session=session,
                           final_pm=pm,trader_plan=trader,report=report,
                           close_usd=bar.close,sector="Technology")
        return {"source_sha256": evidence_hash(report),"decision":"CONDITIONAL_LONG"},plan,report
    out = dry.run_dry_run(tmp_path/"same_day",home,DAY,["AAPL","MSFT","NVDA"],
                          ai_count=3,now=at(18,5),
                          graph_factory=lambda root:object(),research_fn=fake_ai)
    assert received == ["AAPL"]
    assert out["real_ai_attempted"] is True
    assert out["research"]["AAPL"]["reason"]=="CONDITIONAL_PLAN_DIAGNOSTIC_ONLY"
    assert out["research"]["AAPL"]["conditional_plan"]["submitted"] is False
    assert out["paper_orders_created"] == out["account_reads"] == out["account_writes"] == 0
    assert out["research"]["MSFT"]["eligible_for_research"] is False
    assert out["research"]["NVDA"]["eligible_for_research"] is False
    assert (tmp_path/"same_day"/"reports"/DAY/"AAPL"/"source.json").exists()


def test_crlf_or_fake_source_hash_never_becomes_approved(tmp_path):
    home = saved(tmp_path)
    def corrupted_model(_graph,*,ticker,session,bar,root,state):
        report="pm\n"
        dest=root/"reports"/session/ticker
        dest.mkdir(parents=True)
        (dest/"source.json").write_bytes(b"pm\r\n")
        return {"source_sha256":evidence_hash(report)},None,report
    out=dry.run_dry_run(tmp_path/"corrupt",home,DAY,["AAPL"],ai_count=1,
                        now=at(18,5),graph_factory=lambda r:object(),
                        research_fn=corrupted_model)
    assert out["research"]["AAPL"]["reason"]=="AI_OR_PROVENANCE_FAILED_ValueError"
    assert out["paper_orders_created"]==0


def test_dry_run_is_restricted_to_at_most_three_stocks(tmp_path):
    home=saved(tmp_path)
    with pytest.raises(ValueError,match="1-8|1-3"):
        dry.run_dry_run(tmp_path/"too_many",home,DAY,["AAPL","MSFT","NVDA","COST"],now=at(18,5))


def test_rejects_earnings_from_after_immutable_calendar_capture(tmp_path):
    """A 17:20 source cannot appear in evidence captured at 17:10."""
    c = calendar()
    c["earnings"]["AAPL"]["observed_at_utc"] = at(17, 20).astimezone(timezone.utc).isoformat()
    home = saved(tmp_path, c=c)
    result = dry.read_observation(home, DAY, ["AAPL"], at(18, 5).astimezone(timezone.utc))
    assert result["tickers"]["AAPL"]["eligible_for_research"] is False
    assert result["tickers"]["AAPL"]["reason"] == "EARNINGS_EVIDENCE_MISSING_OR_INVALID"


def test_rejects_calendar_claiming_capture_after_market_observation(tmp_path):
    c = calendar()
    c["observed_utc"] = at(17, 50).astimezone(timezone.utc).isoformat()
    home = saved(tmp_path, c=c)
    result = dry.read_observation(home, DAY, ["AAPL"], at(18, 5).astimezone(timezone.utc))
    assert result["tickers"]["AAPL"]["eligible_for_research"] is False
