"""Tests for candidate_handoff_guard_node in portfolio_setup.py."""
import json
from unittest.mock import MagicMock

import pytest


def _make_state(
    equity_candidates: list,
    ticker_analyses: dict,
    prioritized_candidates: list,
) -> dict:
    scan_summary = {"equity_candidates": equity_candidates}
    return {
        "scan_summary": scan_summary,
        "ticker_analyses": ticker_analyses,
        "prioritized_candidates": json.dumps(prioritized_candidates),
        "portfolio_id": "test-portfolio",
        "run_id": "test-run",
        "analysis_date": "2026-05-03",
    }


def _make_guard_node():
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    setup = PortfolioGraphSetup(
        agents={
            "review_holdings": MagicMock(),
            "macro_summary": MagicMock(),
            "micro_summary": MagicMock(),
            "pm_decision": MagicMock(),
        },
        repo=None,
        config={},
        macro_memory=None,
        micro_memory=None,
    )
    return setup._make_candidate_handoff_guard_node()


def test_guard_passes_when_n_in_zero():
    """No equity candidates from scanner → guard short-circuits, no error."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[],
        ticker_analyses={},
        prioritized_candidates=[],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_when_all_buy_flow_through():
    """2 candidates, both extracted BUY, both in prioritized_candidates → pass."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
        },
        prioritized_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_when_all_hold():
    """2 candidates, both extracted HOLD → N_out == 0 is legitimate, no error."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "HOLD"}},
            "TEAM": {"final_trade_decision_structured": {"status": "completed", "action": "HOLD"}},
        },
        prioritized_candidates=[],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_on_partial_extraction_failure():
    """1 BUY, 1 extraction_failed → N_out == 1, accounted. No error."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {"final_trade_decision_structured": {"status": "extraction_failed", "action": None}},
        },
        prioritized_candidates=[{"ticker": "OWL"}],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_on_timeout_fallback_drop():
    """timeout_fallback status is a legitimate non-buy drop and should not raise."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {
                "final_trade_decision_structured": {
                    "status": "timeout_fallback",
                    "action": "HOLD",
                }
            },
        },
        prioritized_candidates=[{"ticker": "OWL"}],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_on_empty_structured_drop():
    """empty status is a legitimate non-buy drop and should not raise."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {
                "final_trade_decision_structured": {
                    "status": "empty",
                    "action": "HOLD",
                }
            },
        },
        prioritized_candidates=[{"ticker": "OWL"}],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_raises_all_extraction_failed():
    """2 candidates, both extraction_failed, N_out == 0 → CandidateHandoffError."""
    from tradingagents.agents.utils.output_validation import CandidateHandoffError

    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "extraction_failed", "action": None}},
            "TEAM": {"final_trade_decision_structured": {"status": "extraction_failed", "action": None}},
        },
        prioritized_candidates=[],
    )
    with pytest.raises(CandidateHandoffError) as exc_info:
        guard(state)
    assert exc_info.value.kind == "all_extraction_failed"
    assert exc_info.value.n_in == 2
    assert exc_info.value.n_out == 0


def test_guard_raises_unaccountable_drop():
    """1 BUY, 1 HOLD, but N_out == 0 (HOLD not in candidates is fine, BUY drop is not)."""
    from tradingagents.agents.utils.output_validation import CandidateHandoffError

    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {"final_trade_decision_structured": {"status": "completed", "action": "HOLD"}},
        },
        # OWL should be in here (it's a BUY) but it isn't — unaccountable drop
        prioritized_candidates=[],
    )
    with pytest.raises(CandidateHandoffError) as exc_info:
        guard(state)
    assert exc_info.value.kind == "unaccountable_drop"
