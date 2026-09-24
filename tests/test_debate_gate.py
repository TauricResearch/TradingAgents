"""The optional Jev debate gate: early stop only on a confident decision-ready
transcript, never on failure, and never before both sides have spoken once.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from tradingagents.agents.debate_gate import jev_debate_gate
from tradingagents.graph.conditional_logic import ConditionalLogic


def _state(count: int, current: str = "Bull researcher: x") -> dict:
    return {
        "investment_debate_state": {
            "count": count,
            "current_response": current,
            "bull_history": "bull argument",
            "bear_history": "bear argument",
            "history": "bull argument bear argument",
            "judge_decision": "",
        }
    }


def test_gate_true_ends_debate_after_a_complete_round():
    logic = ConditionalLogic(max_debate_rounds=3, debate_gate=lambda s: True)
    assert logic.should_continue_debate(_state(2)) == "Research Manager"


def test_gate_none_keeps_alternation():
    logic = ConditionalLogic(max_debate_rounds=3, debate_gate=lambda s: None)
    assert logic.should_continue_debate(_state(2)) == "Bear Researcher"


def test_round_cap_wins_over_gate():
    # cap reached: same answer with or without a gate
    assert ConditionalLogic(max_debate_rounds=1,
                            debate_gate=lambda s: None).should_continue_debate(
                                _state(2)) == "Research Manager"


def test_gate_not_consulted_mid_round():
    calls = []

    def gate(state) -> bool | None:
        calls.append(state["count"])
        return True

    logic = ConditionalLogic(max_debate_rounds=3, debate_gate=gate)
    assert logic.should_continue_debate(_state(1)) == "Bear Researcher"
    assert calls == []  # odd count: bull and bear have not both spoken


def test_gate_false_keeps_alternation():
    logic = ConditionalLogic(max_debate_rounds=3, debate_gate=lambda s: False)
    assert logic.should_continue_debate(_state(2)) == "Bear Researcher"


def test_factory_without_key_returns_none(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jev_debate_gate() is None


def test_factory_gate_maps_answers_to_bool(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    def fake_system_one(state, questions):
        assert "decision_ready" in questions
        assert state["rounds_completed"] == 1
        return {"decision_ready": {"noul": 0.9}}

    with patch("tradingagents.agents.debate_gate.system_one", fake_system_one):
        gate = jev_debate_gate()
        assert gate is not None
        assert gate({"count": 2, "bull_history": "b", "bear_history": "r"}) is True


def test_factory_gate_degrades_on_error(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    from tradingagents.agents.post_screen import TypeSafeError

    with patch("tradingagents.agents.debate_gate.system_one",
               side_effect=TypeSafeError("HTTP 500")):
        gate = jev_debate_gate()
        assert gate({"count": 2, "bull_history": "b", "bear_history": "r"}) is None


def test_env_override_registers(monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG, _apply_env_overrides

    monkeypatch.setenv("TRADINGAGENTS_JEV_DEBATE_GATE", "true")
    config = _apply_env_overrides(DEFAULT_CONFIG.copy())
    assert config["jev_debate_gate"] is True
