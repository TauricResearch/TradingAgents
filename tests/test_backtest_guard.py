"""Tests for the point-in-time look-ahead guard.

These exercise the real ``route_to_vendor`` dispatch path rather than a stub,
so they verify the guard actually sits where the agent's data requests go.
"""

import threading

import pytest

from tradingagents.backtest.guard import (
    LookAheadError,
    check_request,
    point_in_time_guard,
)
from tradingagents.backtest.runner import BacktestRunner, BacktestSpec
from tradingagents.backtest.store import DecisionStore
from tradingagents.dataflows import interface

CONFIG = {
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.6",
    "quick_think_llm": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def stub_vendors(monkeypatch):
    """Replace the vendor implementations with no-ops.

    The guard runs *before* dispatch, so a request that passes it would
    otherwise fall through to a real vendor and hit the network — slow, and
    impossible in CI, which has no API keys. Stubbing the dispatch table keeps
    these tests offline while still exercising the real ``route_to_vendor``
    path the guard is installed on. Method names are kept real so the
    category lookup behaves normally.
    """
    monkeypatch.setattr(
        interface,
        "VENDOR_METHODS",
        {
            "get_news": {"yfinance": lambda *a, **k: "stub news"},
            "get_insider_transactions": {"yfinance": lambda *a, **k: "stub insiders"},
        },
    )


# ---------------------------------------------------------------------------
# check_request
# ---------------------------------------------------------------------------

def test_a_date_past_the_as_of_is_a_violation():
    with pytest.raises(LookAheadError, match="2026-02-01"):
        check_request("get_news", ("NVDA", "2026-01-01", "2026-02-01"), {}, "2026-01-05")


def test_the_as_of_date_itself_is_allowed():
    """The analysis window is inclusive of the trade date."""
    check_request("get_news", ("NVDA", "2026-01-01", "2026-01-05"), {}, "2026-01-05")


def test_earlier_dates_are_allowed():
    check_request("get_stock_data", ("NVDA", "2025-01-01", "2026-01-04"), {}, "2026-01-05")


def test_keyword_arguments_are_checked():
    with pytest.raises(LookAheadError):
        check_request("get_news", (), {"end_date": "2026-06-01"}, "2026-01-05")


def test_dates_nested_in_containers_are_checked():
    with pytest.raises(LookAheadError):
        check_request("get_indicators", (["2026-09-09"],), {}, "2026-01-05")


def test_dates_embedded_in_prose_are_checked():
    with pytest.raises(LookAheadError, match="2026-03-03"):
        check_request("get_news", ("news through 2026-03-03",), {}, "2026-01-05")


def test_non_date_arguments_are_ignored():
    check_request("get_indicators", ("NVDA", "close_50_sma", 50, None), {}, "2026-01-05")


def test_the_violation_message_names_the_method_and_the_dates():
    with pytest.raises(LookAheadError) as excinfo:
        check_request("get_macro_indicators", ("cpi", "2026-12-31"), {}, "2026-01-05")

    message = str(excinfo.value)
    assert "get_macro_indicators" in message
    assert "2026-12-31" in message
    assert "2026-01-05" in message


# ---------------------------------------------------------------------------
# Installation on the real dispatch path
# ---------------------------------------------------------------------------

def test_guard_fires_through_route_to_vendor():
    """The guard must sit on the path every data tool actually uses."""
    with pytest.raises(LookAheadError), point_in_time_guard("2026-01-05"):
        interface.route_to_vendor("get_news", "NVDA", "2026-01-01", "2026-06-01")


def test_no_guard_is_installed_outside_the_context():
    assert interface._request_guard is None

    with point_in_time_guard("2026-01-05"):
        assert interface._request_guard is not None

    assert interface._request_guard is None


def test_a_previously_installed_guard_is_restored():
    calls = []
    previous = interface.set_request_guard(lambda m, a, k: calls.append(m))
    try:
        with point_in_time_guard("2026-01-05"):
            pass
        interface.route_to_vendor("get_insider_transactions", "NVDA")
        assert calls == ["get_insider_transactions"]
    finally:
        interface.set_request_guard(previous)


def test_nested_guards_restore_correctly():
    with point_in_time_guard("2026-01-05"):
        with point_in_time_guard("2026-01-04"):
            pass
        # The outer guard must still be active and still be checking.
        with pytest.raises(LookAheadError):
            interface.route_to_vendor("get_news", "NVDA", "2026-01-01", "2026-02-01")

    assert interface._request_guard is None


def test_a_raising_body_still_uninstalls():
    with pytest.raises(RuntimeError), point_in_time_guard("2026-01-05"):
        raise RuntimeError("boom")

    assert interface._request_guard is None


# ---------------------------------------------------------------------------
# Non-strict mode
# ---------------------------------------------------------------------------

def test_non_strict_mode_collects_instead_of_raising():
    with point_in_time_guard("2026-01-05", strict=False) as violations:
        interface.route_to_vendor("get_news", "NVDA", "2026-01-01", "2026-06-01")

    assert len(violations) == 1
    assert "2026-06-01" in violations[0]


def test_non_strict_mode_records_nothing_for_a_clean_run():
    with point_in_time_guard("2026-01-05", strict=False) as violations:
        pass

    assert violations == []


# ---------------------------------------------------------------------------
# Thread isolation
# ---------------------------------------------------------------------------

def test_each_thread_is_held_to_its_own_as_of_date():
    """Concurrent tickers must not inherit each other's trade date."""
    results = {}

    def worker(name, as_of, requested):
        try:
            with point_in_time_guard(as_of):
                interface.route_to_vendor("get_news", "NVDA", "2025-01-01", requested)
            results[name] = "allowed"
        except LookAheadError:
            results[name] = "blocked"

    threads = [
        # Permissive thread: its own as-of covers the request.
        threading.Thread(target=worker, args=("late", "2026-06-30", "2026-06-01")),
        # Restrictive thread: the same request is a violation for it.
        threading.Thread(target=worker, args=("early", "2026-01-05", "2026-06-01")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == {"late": "allowed", "early": "blocked"}


def test_an_unguarded_thread_is_unaffected():
    """Installing the hook must not police work that never opted in."""
    outcome = {}

    def unguarded():
        interface.route_to_vendor("get_insider_transactions", "NVDA")
        outcome["ran"] = True

    with point_in_time_guard("2026-01-05"):
        thread = threading.Thread(target=unguarded)
        thread.start()
        thread.join()

    assert outcome == {"ran": True}


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------

class LeakyGraph:
    """A graph whose data access reaches past the trade date."""

    def __init__(self, offset_date="2026-12-31"):
        self.offset_date = offset_date
        self.curr_state = {}

    def propagate(self, company_name, trade_date, asset_type="stock"):
        interface.route_to_vendor("get_news", company_name, trade_date, self.offset_date)
        self.curr_state = {"final_trade_decision": "Rating: Buy"}
        return self.curr_state, "Buy"


class CleanGraph:
    """A graph that only ever asks for data up to the trade date."""

    def __init__(self):
        self.curr_state = {}

    def propagate(self, company_name, trade_date, asset_type="stock"):
        interface.route_to_vendor("get_news", company_name, "2025-01-01", trade_date)
        self.curr_state = {"final_trade_decision": "Rating: Buy"}
        return self.curr_state, "Buy"


def make_runner(tmp_path, graph, strict):
    spec = BacktestSpec(
        tickers=["NVDA"], start="2026-01-05", end="2026-01-09",
        every_n_days=5, strict_point_in_time=strict,
    )
    return BacktestRunner(
        spec=spec,
        store=DecisionStore(tmp_path / "decisions.jsonl"),
        graph_factory=lambda t, c, cb: graph,
        config=CONFIG,
        memory_dir=tmp_path / "memory",
    )


def test_strict_mode_records_a_leaky_decision_as_a_failure(tmp_path):
    runner = make_runner(tmp_path, LeakyGraph(), strict=True)
    summary = runner.run()

    assert summary.produced == 0
    assert summary.failed == 1
    assert "LookAheadError" in runner.store.failures()[0].error


def test_a_clean_graph_passes_under_strict_mode(tmp_path):
    runner = make_runner(tmp_path, CleanGraph(), strict=True)
    summary = runner.run()

    assert summary.produced == 1
    assert summary.failed == 0


def test_leakage_is_not_checked_when_the_guard_is_off(tmp_path):
    runner = make_runner(tmp_path, LeakyGraph(), strict=False)
    summary = runner.run()

    assert summary.produced == 1
    assert interface._request_guard is None
