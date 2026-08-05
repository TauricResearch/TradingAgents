"""Forward paper-ledger immutability, calendar timing, and accounting."""

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tradingagents.paper_trading import (
    PaperStore,
    _cycle_with_retries,
    advance_mark,
    current_decision_date,
    decide,
    decision_window,
    next_daemon_run,
)


def _config():
    return {
        "tickers": ["A", "B"],
        "benchmark": "SPY",
        "cost_bps": 5.0,
        "slippage_bps": 5.0,
        "annual_borrow_bps": 300.0,
    }


def _decisions():
    return [
        {
            "ticker": "A", "replicate": 0, "action": "Buy", "score": 1.0,
            "data_fingerprint": "data-a", "signal_fingerprint": "signal-v1",
            "final_decision": "Rating: Buy",
        },
        {
            "ticker": "B", "replicate": 0, "action": "Hold", "score": 0.0,
            "data_fingerprint": "data-b", "signal_fingerprint": "signal-v1",
            "final_decision": "Rating: Hold",
        },
    ]


@pytest.mark.unit
def test_paper_store_freezes_complete_decision_set(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("core", _config(), 100.0)
    store.record_decision_set(
        "core", "2026-07-27", "2026-07-28", 200.0,
        _decisions(), {"A": 1.0, "B": 0.0},
    )

    assert store.target_for_entry("core", "2026-07-28") == {
        "decision_date": "2026-07-27",
        "weights": {"A": 1.0, "B": 0.0},
    }
    assert store.status("core")["decision_rows"] == 2
    with pytest.raises(sqlite3.IntegrityError):
        store.record_decision_set(
            "core", "2026-07-27", "2026-07-28", 300.0,
            _decisions(), {"A": 0.0, "B": 1.0},
        )
    assert store.target_for_entry("core", "2026-07-28")["weights"] == {
        "A": 1.0, "B": 0.0,
    }
    store.close()


@pytest.mark.unit
def test_paper_run_config_cannot_change(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("core", _config(), 100.0)
    changed = {**_config(), "benchmark": "QQQ"}
    with pytest.raises(ValueError, match="different config"):
        store.create_run("core", changed, 200.0)
    store.close()


@pytest.mark.unit
def test_paper_marks_apply_next_open_costs_and_returns():
    first = advance_mark(
        previous=None,
        session_date="2026-07-28",
        captured_utc=1.0,
        opens={"A": 100.0, "B": 20.0},
        benchmark_open=100.0,
        target={"decision_date": "2026-07-27", "weights": {"A": 1.0, "B": 0.0}},
        trading_cost_bps=5,
        slippage_bps=5,
        annual_borrow_bps=300,
    )
    second = advance_mark(
        previous=first,
        session_date="2026-07-29",
        captured_utc=2.0,
        opens={"A": 110.0, "B": 20.0},
        benchmark_open=105.0,
        target=None,
        trading_cost_bps=5,
        slippage_bps=5,
        annual_borrow_bps=300,
    )

    assert first["nav"] == pytest.approx(0.999)
    assert first["turnover"] == 1.0
    assert second["nav"] == pytest.approx(1.0989)
    assert second["benchmark_nav"] == pytest.approx(1.05)


@pytest.mark.unit
def test_forward_mark_can_use_one_vintage_returns_across_a_split():
    previous = advance_mark(
        previous=None,
        session_date="2026-07-28",
        captured_utc=1.0,
        opens={"A": 100.0},
        benchmark_open=100.0,
        target={"decision_date": "2026-07-27", "weights": {"A": 1.0}},
        trading_cost_bps=0,
        slippage_bps=0,
        annual_borrow_bps=0,
    )

    current = advance_mark(
        previous=previous,
        session_date="2026-07-29",
        captured_utc=2.0,
        # A new adjusted-price vintage may show the post-split open at 50 even
        # though the prior immutable mark captured a pre-split 100.
        opens={"A": 50.0},
        benchmark_open=110.0,
        target=None,
        trading_cost_bps=0,
        slippage_bps=0,
        annual_borrow_bps=0,
        asset_returns={"A": 0.0},
        benchmark_period_return_override=0.10,
    )

    assert current["nav"] == pytest.approx(1.0)
    assert current["benchmark_nav"] == pytest.approx(1.1)


@pytest.mark.unit
def test_decision_window_is_after_cutoff_and_before_next_open():
    pytest.importorskip("exchange_calendars")
    cutoff, next_open, entry_date = decision_window("2026-07-27")
    assert cutoff == datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc)
    assert next_open == datetime(2026, 7, 28, 13, 30, tzinfo=timezone.utc)
    assert entry_date == "2026-07-28"
    assert current_decision_date(
        datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)
    ) == "2026-07-27"


@pytest.mark.unit
def test_weekend_still_maps_to_friday_decision_window():
    pytest.importorskip("exchange_calendars")
    assert current_decision_date(
        datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    ) == "2026-07-24"


@pytest.mark.unit
def test_daemon_runs_just_after_daily_data_cutoff():
    assert next_daemon_run(
        datetime(2026, 7, 27, 23, 0, tzinfo=timezone.utc)
    ) == datetime(2026, 7, 28, 0, 5, tzinfo=timezone.utc)
    assert next_daemon_run(
        datetime(2026, 7, 28, 0, 6, tzinfo=timezone.utc)
    ) == datetime(2026, 7, 29, 0, 5, tzinfo=timezone.utc)


@pytest.mark.unit
def test_forward_decision_manifest_accepts_paper_arguments(tmp_path, monkeypatch):
    pytest.importorskip("exchange_calendars")
    from tradingagents.dataflows import media_history
    from tradingagents.graph import trading_graph

    class FakeGraph:
        def __init__(self, **kwargs):
            self.curr_state = {}

        def propagate(self, ticker, decision_date):
            self.curr_state = {"final_trade_decision": f"Rating: Buy for {ticker}"}
            return {}, "Buy"

    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", FakeGraph)
    monkeypatch.setattr(
        media_history, "collected_window_fingerprint", lambda *args, **kwargs: "data-v1"
    )
    args = SimpleNamespace(
        run_id="paper-regression",
        db=str(tmp_path / "paper.db"),
        tickers="NVDA,MSFT",
        benchmark="SPY",
        analysts="market,social,news",
        replicates=1,
        portfolio_mode="long-only",
        gross_limit=1.0,
        max_weight=0.5,
        cost_bps=5.0,
        slippage_bps=5.0,
        annual_borrow_bps=300.0,
        results_dir=str(tmp_path / "results"),
        debug=False,
        global_topics_only=False,
    )

    result = decide(args, datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc))

    assert result["decision_date"] == "2026-07-27"
    assert result["decision_rows"] == 2
    assert result["weights"] == {"MSFT": 0.5, "NVDA": 0.5}


@pytest.mark.unit
def test_daemon_retries_transient_failure_and_records_success(monkeypatch):
    from tradingagents import paper_trading

    calls = {"cycles": 0, "heartbeats": []}

    def fake_cycle(args, now):
        calls["cycles"] += 1
        if calls["cycles"] < 3:
            raise RuntimeError("temporary provider failure")
        return {"decision_recorded": True}

    monkeypatch.setattr(paper_trading, "cycle", fake_cycle)
    monkeypatch.setattr(
        paper_trading,
        "_record_daemon_heartbeat",
        lambda db, key, captured: calls["heartbeats"].append(key),
    )

    result = _cycle_with_retries(
        SimpleNamespace(db="unused"), attempts=3, retry_seconds=0, sleep_fn=lambda _: None
    )

    assert result == {"decision_recorded": True}
    assert calls["cycles"] == 3
    assert calls["heartbeats"] == [
        "paper:last_failure_utc", "paper:last_failure_utc", "paper:last_success_utc"
    ]


@pytest.mark.unit
def test_daemon_retries_data_integrity_value_error_and_crashes_after_exhaustion(monkeypatch):
    from tradingagents import paper_trading

    heartbeats = []

    def bad_cycle(args, now):
        raise ValueError("bad NAV")

    monkeypatch.setattr(paper_trading, "cycle", bad_cycle)
    monkeypatch.setattr(
        paper_trading,
        "_record_daemon_heartbeat",
        lambda db, key, captured: heartbeats.append(key),
    )

    with pytest.raises(RuntimeError, match="failed after 2 attempts"):
        _cycle_with_retries(
            SimpleNamespace(db="unused"), attempts=2, retry_seconds=0, sleep_fn=lambda _: None
        )
    assert heartbeats == ["paper:last_failure_utc", "paper:last_failure_utc"]
