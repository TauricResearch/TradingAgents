"""Integration: the Execution Gate wired into the run finalization.

``record_decision`` now evaluates every finished run through the gate and
writes the audit JSON beside the state log. These tests pin the contract's
core promises at the integration level: the decision is still recorded
(the gate never blocks reporting), the verdict lands in the state, the
audit file exists, and a reliability-layer failure cannot sink the run.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.gate_integration import (
    attach_to_state,
    evaluate_decision,
    write_audit_record,
)


def _state(rating="Overweight", decision_text="**Rating**: Overweight\nBuy the dip."):
    """The minimal final state _log_state reads, plus the decision fields."""
    return {
        "company_of_interest": "BRK-B",
        "trade_date": "2026-11-08",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {"bull_history": "", "bear_history": "",
                                    "history": "", "current_response": ""},
        "trader_investment_plan": "",
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "history": ""},
        "investment_plan": "",
        "final_rating": rating,
        "final_trade_decision": decision_text,
    }


# ---------------------------------------------------------------------------
# evaluate_decision
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overweight_decision_with_no_plan_waits():
    """No plan numbers -> no risk check is guessed; the honest default holds."""
    record, decision = evaluate_decision(
        "BRK-B", "2026-11-08", _state(), snapshot_id="s1",
    )
    assert decision.action.value in ("WAIT", "BLOCK")
    assert record.strategic is not None
    assert record.strategic.rating == "OVERWEIGHT"
    assert record.strategic.legacy_label == "Overweight"


@pytest.mark.unit
def test_invalid_stop_plan_blocks():
    """The BRK-B plan (543.70/543.50/ATR 9.408) blocks through the wiring."""
    record, decision = evaluate_decision(
        "BRK-B", "2026-11-08", _state(), snapshot_id="s1",
        entry=543.70, stop=543.50, atr=9.408,
    )
    assert decision.action.value == "BLOCK"
    assert "RISK_PLAN_BLOCKED" in [r.value for r in decision.reasons]
    assert record.stop_validation is not None
    assert record.stop_validation.blocked


@pytest.mark.unit
def test_unreadable_rating_blocks_rather_than_guessing():
    """An unreadable rating (#1170) must not become a call the gate trusts."""
    record, decision = evaluate_decision(
        "BRK-B", "2026-11-08", _state(rating="REVIEW"), snapshot_id="s1",
    )
    assert decision.action.value == "BLOCK"
    assert record.strategic is None


@pytest.mark.unit
def test_empty_rating_blocks():
    record, decision = evaluate_decision(
        "BRK-B", "2026-11-08", _state(rating=""), snapshot_id="s1",
    )
    assert decision.action.value == "BLOCK"


@pytest.mark.unit
def test_causal_guard_flows_through_the_wiring():
    """A weekend release with a calendar: the verdict reaches the audit."""
    record, decision = evaluate_decision(
        "BRK-B", "2026-11-08", _state(), snapshot_id="s1",
        sessions=["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"],
        event_publication_date="2026-11-07",
    )
    assert record.causal is not None
    assert record.causal.status == "NOT_YET_OBSERVABLE"
    assert record.to_dict()["events"][0]["post_event_price_status"] == \
        "NOT_YET_OBSERVABLE"


@pytest.mark.unit
def test_model_versions_reach_the_audit():
    record, _ = evaluate_decision(
        "BRK-B", "2026-11-08", _state(), snapshot_id="s1",
        model_versions={"deep": "GLM-5.3", "quick": "DeepSeek-V4.1-Flash"},
    )
    assert record.to_dict()["audit"]["model_versions"]["deep"] == "GLM-5.3"


# ---------------------------------------------------------------------------
# Persistence and state attachment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audit_record_is_written_beside_the_state_log(tmp_path):
    record, _ = evaluate_decision("BRK-B", "2026-11-08", _state(), snapshot_id="s1")
    path = write_audit_record(record, str(tmp_path))
    assert path.exists()
    # Without a run id the historical name is kept, so existing readers and
    # the smoke checks that only look for "an audit" still work.
    assert path == tmp_path / "BRK-B" / "reliability_audit" / "audit_2026-11-08.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ticker"] == "BRK-B"
    assert data["schema_version"] == "1.0"


@pytest.mark.unit
def test_two_runs_of_the_same_day_do_not_overwrite_each_other(tmp_path):
    """§2 of P4: the dated filename used to lose one analysis per day."""
    record, _ = evaluate_decision("BRK-B", "2026-11-08", _state(), snapshot_id="s1")
    first = write_audit_record(record, str(tmp_path), run_id="run-a")
    second = write_audit_record(record, str(tmp_path), run_id="run-b")

    assert first != second
    assert first.exists() and second.exists()
    assert first.name == "audit_2026-11-08_run-a.json"


@pytest.mark.unit
def test_attach_to_state_exposes_the_verdict():
    state = _state()
    _, decision = evaluate_decision("BRK-B", "2026-11-08", state, snapshot_id="s1")
    attach_to_state(state, decision)
    assert state["execution_action"] == decision.action.value
    assert state["execution_reason_codes"] == [r.value for r in decision.reasons]


# ---------------------------------------------------------------------------
# The graph's record_decision wiring
# ---------------------------------------------------------------------------


def _graph_with_tmp_results(monkeypatch, tmp_path):
    """A TradingAgentsGraph-shaped minimal stub: only what record_decision touches."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path / "results")}
    graph.selected_analysts = []  # run_settings reads it for the state log
    graph.memory_log = None  # replaced per-test
    return graph


@pytest.mark.unit
def test_record_decision_attaches_the_verdict_and_writes_the_audit(
    monkeypatch, tmp_path
):
    """The wiring: state gains execution_action; the audit file exists."""
    graph = _graph_with_tmp_results(monkeypatch, tmp_path)
    state = _state()
    # No memory log on the stub: store_decision is skipped by the empty
    # decision guard? No — the decision text is present, so patch the log.
    class _Log:
        def store_decision(self, **kwargs):
            self.stored = kwargs

    log = _Log()
    graph.memory_log = log
    graph._evaluate_reliability = graph._evaluate_reliability  # bound already

    graph.record_decision("BRK-B", "2026-11-08", state)
    assert "execution_action" in state
    audit_dir = tmp_path / "results" / "BRK-B" / "reliability_audit"
    # The audit is now run-scoped: the date plus the run id the graph minted.
    audits = list(audit_dir.glob("audit_2026-11-08_*.json"))
    assert len(audits) == 1, f"expected one run-scoped audit, got {audits}"
    assert log.stored["ticker"] == "BRK-B"


@pytest.mark.unit
def test_reliability_failure_never_sinks_the_run(monkeypatch, tmp_path):
    """A broken audit layer must not lose the run's reports or memory entry."""
    graph = _graph_with_tmp_results(monkeypatch, tmp_path)

    class _Log:
        def __init__(self):
            self.stored = None

        def store_decision(self, **kwargs):
            self.stored = kwargs

    graph.memory_log = _Log()

    def boom(*args, **kwargs):
        raise RuntimeError("audit layer down")

    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.evaluate_decision", boom
    )
    state = _state()
    graph.record_decision("BRK-B", "2026-11-08", state)  # must not raise
    # The decision still reached the memory log.
    assert graph.memory_log.stored["ticker"] == "BRK-B"
    # And the state log was still written.
    assert (tmp_path / "results" / "BRK-B" / "TradingAgentsStrategy_logs" /
            "full_states_log_2026-11-08.json").exists()
