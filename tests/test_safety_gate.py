"""Contract tests for the deterministic Safety Gate (Candidate B); expected to
FAIL until it exists. No skip/importorskip: a missing module is a real failure.

``evaluate_safety`` returns final_rating (canonical or REVIEW), safety_gate_status
(PASS|REVIEW), safety_gate_reason_codes, safety_gate_missing_evidence. Evidence is
existence only for the selected plan's reports; a canonical rating is preserved or
downgraded to REVIEW, never upgraded/swapped; zero LLM/tool/vendor calls;
final_trade_decision unchanged; all violations collected in deterministic order.
Absent final_rating recovers via the frozen parser; a present noncanonical one
fails closed. Reason codes: MISSING_SELECTED_EVIDENCE, MISSING_INVESTMENT_PLAN,
MISSING_TRADER_PLAN, MISSING_DECISION, UNUSABLE_RATING, GATE_ERROR (PASS empty).

Coverage: REQ-SG-01, REQ-SG-02, REQ-SG-04, REQ-SG-06; INV-SG-01, INV-SG-02.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tradingagents.agents.rating import RATING_REVIEW, parse_rating
from tradingagents.graph.analyst_execution import build_analyst_execution_plan

REASONS = {
    "MISSING_SELECTED_EVIDENCE", "MISSING_INVESTMENT_PLAN", "MISSING_TRADER_PLAN",
    "MISSING_DECISION", "UNUSABLE_RATING", "GATE_ERROR",
}


def _evaluate():
    """Import the gate; a missing module is a real failure, not a skip."""
    try:
        from tradingagents.graph import safety_gate
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing module tradingagents.graph.safety_gate: {exc}")
    assert callable(getattr(safety_gate, "evaluate_safety", None)), (
        "tradingagents.graph.safety_gate.evaluate_safety must be callable"
    )
    return safety_gate.evaluate_safety


def _report_keys(selected):
    return tuple(spec.report_key for spec in build_analyst_execution_plan(selected).specs)


def _state(selected, rating="Buy"):
    """A fully evidenced, well-formed state for the given selection."""
    state = {
        "investment_plan": "plan",
        "trader_investment_plan": "proposal",
        "final_trade_decision": f"**Rating**: {rating}\n\nThesis.",
        "final_rating": rating,
    }
    state.update({key: f"{key} body" for key in _report_keys(selected)})
    return state


def _run(state, selected):
    return _evaluate()(dict(state), selected)


def _codes(result):
    return tuple(result["safety_gate_reason_codes"])


def _missing(result):
    return tuple(result["safety_gate_missing_evidence"])


def _assert_review(result):
    assert result["final_rating"] == RATING_REVIEW
    assert result["safety_gate_status"] == "REVIEW"
    assert _codes(result) and set(_codes(result)) <= REASONS


FOUR = ("market", "social", "news", "fundamentals")


# --- REQ-SG-01 pass-through, REQ-SG-04 compatibility ------------------------

@pytest.mark.unit
def test_complete_evidence_passes_through_and_decision_text_is_unchanged():
    state = _state(FOUR)
    original = state["final_trade_decision"]
    result = _run(state, FOUR)

    assert result["final_rating"] == "Buy"
    assert result["safety_gate_status"] == "PASS"
    assert _codes(result) == () and _missing(result) == ()
    assert result.get("final_trade_decision", original) == original


@pytest.mark.unit
def test_only_selected_reports_are_required():
    """A two-analyst run must not be held to the four-analyst report set."""
    selected = ("market", "news")
    result = _run(_state(selected), selected)

    assert result["safety_gate_status"] == "PASS" and result["final_rating"] == "Buy"


# --- INV-SG-01: every violation downgrades to REVIEW -----------------------

@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "   ", "\n\t ", None, 123, ["x"]])
def test_missing_or_nonstring_selected_evidence_downgrades(bad):
    selected = ("market", "news")
    state = _state(selected)
    state["market_report"] = bad
    result = _run(state, selected)

    _assert_review(result)
    assert "MISSING_SELECTED_EVIDENCE" in _codes(result)
    assert "market_report" in _missing(result)


@pytest.mark.unit
@pytest.mark.parametrize("field,code", [
    ("investment_plan", "MISSING_INVESTMENT_PLAN"),
    ("trader_investment_plan", "MISSING_TRADER_PLAN"),
    ("final_trade_decision", "MISSING_DECISION"),
])
def test_missing_plan_or_decision_downgrades(field, code):
    state = _state(FOUR)
    del state[field]
    result = _run(state, FOUR)

    _assert_review(result)
    assert code in _codes(result)


@pytest.mark.unit
def test_all_violations_are_collected_in_deterministic_order_with_exact_keys():
    selected = ("market", "news")
    broken = {
        "market_report": "   ", "investment_plan": "", "trader_investment_plan": "",
        "final_trade_decision": "", "final_rating": "",
    }
    first, second = _run(broken, selected), _run(broken, selected)

    _assert_review(first)
    assert _codes(first) == _codes(second) and _missing(first) == _missing(second)
    assert {"MISSING_SELECTED_EVIDENCE", "MISSING_INVESTMENT_PLAN",
            "MISSING_TRADER_PLAN", "MISSING_DECISION"} <= set(_codes(first))
    assert _missing(first) == ("market_report", "news_report")


# --- rating: reuse frozen parser, fail closed on bad input -----------------

@pytest.mark.unit
def test_absent_final_rating_is_recovered_from_the_parser():
    selected = ("market", "news")
    state = _state(selected)
    del state["final_rating"]
    result = _run(state, selected)

    assert parse_rating(state["final_trade_decision"]) == "Buy"
    assert result["final_rating"] == "Buy" and result["safety_gate_status"] == "PASS"


@pytest.mark.unit
@pytest.mark.parametrize("rating,prose", [
    ("Speculative", "**Rating**: Buy\n\nThesis."),   # noncanonical present, prose parses
    ("REVIEW", "**Rating**: Buy\n\nThesis."),         # REVIEW present, never upgraded
    (None, "The bull wants Buy, the bear wants Sell."),  # absent + ambiguous prose
    (None, "I cannot rate this security."),           # absent + no call
])
def test_bad_or_unrecoverable_rating_fails_closed(rating, prose):
    selected = ("market", "news")
    state = _state(selected)
    state["final_trade_decision"] = prose
    if rating is None:
        del state["final_rating"]
    else:
        state["final_rating"] = rating
    result = _run(state, selected)

    _assert_review(result)
    assert "UNUSABLE_RATING" in _codes(result)


# --- INV-SG-02 monotonic; idempotence; fail-closed -------------------------

@pytest.mark.unit
@pytest.mark.parametrize("complete", [True, False])
def test_monotonic_downgrade_and_idempotence(complete):
    selected = ("market", "social")
    state = _state(selected, rating="Sell")
    if not complete:
        state["news_report"] = ""      # irrelevant: not selected
        state["market_report"] = ""
    once = _run(state, selected)
    twice = _run({**state, **once}, selected)

    assert once["final_rating"] in ("Sell", RATING_REVIEW)   # never another tier
    assert twice["final_rating"] == once["final_rating"]
    assert twice["safety_gate_status"] == once["safety_gate_status"]
    assert _codes(twice) == _codes(once)


@pytest.mark.unit
def test_gate_error_fails_closed_as_review():
    gate = _evaluate()

    class Exploding(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    result = gate(Exploding(), ("market", "news"))

    assert result["final_rating"] == RATING_REVIEW
    assert result["safety_gate_status"] == "REVIEW"
    assert "GATE_ERROR" in tuple(result["safety_gate_reason_codes"])


# --- REQ-SG-02: no LLM / tool / vendor imports -----------------------------

@pytest.mark.unit
def test_gate_source_imports_no_llm_tool_or_vendor_layer():
    import tradingagents.graph.safety_gate as gate  # fails loudly if absent
    source = Path(gate.__file__).read_text(encoding="utf-8")
    banned = ("langchain_core", "langchain", "langgraph", "openai", "anthropic",
              "google", "yfinance", "curl_cffi", "requests", "tradingagents.dataflows",
              "tradingagents.llm_clients", "tradingagents.agents.tools")

    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = {m for m in imported if any(m == b or m.startswith(b + ".") for b in banned)}
    assert offenders == set(), f"gate must not import {offenders}"


@pytest.mark.unit
@pytest.mark.parametrize("rating", ["Buy", "Overweight", "Hold", "Underweight", "Sell"])
def test_tradeable_rating_is_only_kept_or_downgraded(rating):
    result = _run(_state(FOUR, rating=rating), FOUR)
    assert result["final_rating"] in (rating, RATING_REVIEW)
