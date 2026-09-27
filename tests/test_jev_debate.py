"""Debate convergence with TypeSafe Jev (docs/jev-use-cases.md, fit 3).

After each turn that could end a debate, Jev says whether the turn raised
anything new; the routers stop at the end of a round in which no turn did, and
never run past the configured rounds. When the investment debate ends, Jev's
read of whose case is better supported reaches the Research Manager as a hint.
Without Jev, or when a request fails, the debates run exactly as before.

A fake client stands in for the service: it answers from markers in the text,
so the tests pin the policy and the plumbing, not the model.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langgraph.graph import END, START, StateGraph

from tradingagents.agents import debate_judgments as dj, jev
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.state import AgentState
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import DEBATE_PATH_MAP, RISK_ANALYSIS_PATH_MAP

# ---------------------------------------------------------------------------
# A fake Jev client and scripted debaters
# ---------------------------------------------------------------------------

REPEAT = "[repeat]"  # a turn carrying this marker adds nothing new


class FakeJev:
    """Answers from markers in the text; records every request."""

    def __init__(self, fail=False, sides=None):
        self.fail = fail
        self.sides = sides or {"bull": 0.6, "bear": 0.3, "even": 0.1}
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def system_one(self, state, questions):
        self.requests.append((state, set(questions)))
        if self.fail:
            raise RuntimeError("jev is down")
        if "new_argument" in questions:
            p = 0.1 if REPEAT in state["latest_turn"] else 0.9
            return SimpleNamespace(answers={"new_argument": SimpleNamespace(noul=p)})
        top = max(self.sides, key=self.sides.get)
        return SimpleNamespace(answers={"stronger_side": SimpleNamespace(
            choice=top, confidence=self.sides[top], probabilities=dict(self.sides),
        )})


@pytest.fixture
def fake_jev(monkeypatch):
    """Turn Jev on with a fake client. Building the real questions needs the SDK."""
    pytest.importorskip("typesafe_sdk")
    client = FakeJev()
    monkeypatch.setattr(dj, "jev_client", lambda: client)
    return client


def _script_llm(replies):
    """An LLM that answers each call with the next reply, then repeats itself."""
    replies = list(replies)
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: MagicMock(
        content=replies.pop(0) if replies else f"nothing to add {REPEAT}"
    )
    return llm


_REPORTS = {
    "company_of_interest": "NVDA", "asset_type": "stock", "trade_date": "2026-09-23",
    "market_report": "m", "sentiment_report": "s", "news_report": "n",
    "fundamentals_report": "f", "trader_investment_plan": "plan",
}


def _initial_state():
    state = Propagator().create_initial_state("NVDA", "2026-09-23")
    state.update(_REPORTS)
    return state


def _run_investment_debate(logic, bull_replies, bear_replies):
    """The real bull/bear nodes and router in a graph that ends at the manager."""
    graph = StateGraph(AgentState)
    graph.add_node("Bull Researcher", logic.judge_turns(
        create_bull_researcher(_script_llm(bull_replies)), "investment"))
    graph.add_node("Bear Researcher", logic.judge_turns(
        create_bear_researcher(_script_llm(bear_replies)), "investment"))
    graph.add_node("Research Manager", lambda state: {})
    graph.add_edge(START, "Bull Researcher")
    for node in ("Bull Researcher", "Bear Researcher"):
        graph.add_conditional_edges(node, logic.should_continue_debate, DEBATE_PATH_MAP)
    graph.add_edge("Research Manager", END)
    return graph.compile().invoke(_initial_state())["investment_debate_state"]


def _run_risk_debate(logic, aggressive, conservative, neutral):
    graph = StateGraph(AgentState)
    for name, factory, replies in (
        ("Aggressive Analyst", create_aggressive_debator, aggressive),
        ("Conservative Analyst", create_conservative_debator, conservative),
        ("Neutral Analyst", create_neutral_debator, neutral),
    ):
        graph.add_node(name, logic.judge_turns(factory(_script_llm(replies)), "risk"))
        graph.add_conditional_edges(name, logic.should_continue_risk_analysis, RISK_ANALYSIS_PATH_MAP)
    graph.add_node("Portfolio Manager", lambda state: {})
    graph.add_edge(START, "Aggressive Analyst")
    graph.add_edge("Portfolio Manager", END)
    return graph.compile().invoke(_initial_state())["risk_debate_state"]


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("turn", "expected"), [
    (1, False), (2, False),  # round 1: the openings
    (3, True), (4, True),    # round 2
    (5, True), (6, True),    # round 3
    (7, False), (8, False),  # round 4 is the last configured round; it ends anyway
])
def test_only_turns_that_could_end_the_debate_are_judged(turn, expected):
    assert dj.worth_judging(turn, speakers=2, max_rounds=4) is expected


@pytest.mark.unit
def test_no_turn_is_judged_when_the_debate_cannot_end_early():
    # One or two configured rounds: round 1 is the openings, round 2 the last.
    for max_rounds in (1, 2):
        assert not any(dj.worth_judging(t, 2, max_rounds) for t in range(1, 2 * max_rounds + 1))
        assert not any(dj.worth_judging(t, 3, max_rounds) for t in range(1, 3 * max_rounds + 1))


@pytest.mark.unit
def test_min_rounds_below_two_is_rejected():
    with pytest.raises(ValueError, match="min_rounds"):
        dj.DebatePolicy(min_rounds=1)


def _debate(count, scores):
    return {"count": count, "new_argument": scores}


@pytest.mark.unit
@pytest.mark.parametrize(("debate", "expected"), [
    (_debate(4, [None, None, 0.1, 0.2]), True),   # round 2 added nothing
    (_debate(4, [None, None, 0.1, 0.9]), False),  # the bear still had something new
    (_debate(4, [None, None, 0.1, None]), False),  # an unjudged turn keeps it going
    (_debate(3, [None, None, 0.1]), False),        # mid-round: the bear has not answered
    (_debate(2, [None, None]), False),             # round 1 never converges
    (_debate(4, [0.1, 0.1]), False),               # scores missing for the round
    (_debate(4, []), False),
    ({"count": 4}, False),                         # state from before fit 3
])
def test_converged_needs_a_full_round_with_nothing_new(debate, expected):
    assert dj.converged(debate, speakers=2) is expected


@pytest.mark.unit
def test_threshold_and_min_rounds_come_from_the_policy():
    debate = _debate(4, [None, None, 0.35, 0.35])
    assert not dj.converged(debate, 2)
    assert dj.converged(debate, 2, dj.DebatePolicy(new_argument_min=0.4))
    assert not dj.converged(_debate(4, [None, None, 0.1, 0.1]), 2, dj.DebatePolicy(min_rounds=3))


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_debate_router_stops_a_converged_debate_before_its_rounds_run_out():
    logic = ConditionalLogic(max_debate_rounds=4)
    state = {"investment_debate_state": {
        "count": 4, "current_response": "Bear Analyst: ...", "new_argument": [None, None, 0.1, 0.1],
    }}
    assert logic.should_continue_debate(state) == "Research Manager"
    state["investment_debate_state"]["new_argument"] = [None, None, 0.1, 0.9]
    assert logic.should_continue_debate(state) == "Bull Researcher"


@pytest.mark.unit
def test_risk_router_stops_a_converged_debate_before_its_rounds_run_out():
    logic = ConditionalLogic(max_risk_discuss_rounds=3)
    state = {"risk_debate_state": {
        "count": 6, "latest_speaker": "Neutral", "new_argument": [None] * 3 + [0.1] * 3,
    }}
    assert logic.should_continue_risk_analysis(state) == "Portfolio Manager"
    state["risk_debate_state"]["new_argument"] = [None] * 3 + [0.1, 0.9, 0.1]
    assert logic.should_continue_risk_analysis(state) == "Aggressive Analyst"


# ---------------------------------------------------------------------------
# Debates end once a round adds nothing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_without_jev_the_debate_runs_every_configured_round():
    debate = _run_investment_debate(ConditionalLogic(max_debate_rounds=3), [], [])
    assert debate["count"] == 6
    assert debate["new_argument"] == [None] * 6


@pytest.mark.unit
def test_investment_debate_stops_after_a_round_with_nothing_new(fake_jev):
    debate = _run_investment_debate(
        ConditionalLogic(max_debate_rounds=4),
        ["bull opens", f"bull again {REPEAT}"],
        ["bear opens", f"bear again {REPEAT}"],
    )
    assert debate["count"] == 4  # two of four rounds held
    assert debate["new_argument"] == [None, None, 0.1, 0.1]
    assert len(fake_jev.requests) == 2  # round 1 is never asked about


@pytest.mark.unit
def test_one_new_argument_earns_the_other_side_a_reply(fake_jev):
    debate = _run_investment_debate(
        ConditionalLogic(max_debate_rounds=4),
        ["bull opens", f"bull again {REPEAT}", f"bull third {REPEAT}"],
        ["bear opens", "bear finds a lawsuit", f"bear third {REPEAT}"],
    )
    assert debate["count"] == 6
    assert debate["new_argument"] == [None, None, 0.1, 0.9, 0.1, 0.1]


@pytest.mark.unit
def test_a_debate_that_never_converges_still_ends_at_its_rounds(fake_jev):
    debate = _run_investment_debate(
        ConditionalLogic(max_debate_rounds=3),
        ["b1", "b2", "b3"], ["r1", "r2", "r3"],
    )
    assert debate["count"] == 6
    # Round 3 ends the debate anyway, so its turns are not asked about.
    assert debate["new_argument"] == [None, None, 0.9, 0.9, None, None]
    assert len(fake_jev.requests) == 2


@pytest.mark.unit
def test_a_turn_is_judged_against_the_turns_before_it(fake_jev):
    _run_investment_debate(
        ConditionalLogic(max_debate_rounds=3),
        ["bull opens", "bull second"], ["bear opens", "bear second"],
    )
    (first, questions), (second, _) = fake_jev.requests
    assert questions == {"new_argument"}
    assert first == {
        "prior_turns": "Bull Analyst: bull opens\nBear Analyst: bear opens",
        "latest_turn": "Bull Analyst: bull second",
    }
    assert second["prior_turns"].endswith("Bull Analyst: bull second")
    assert second["latest_turn"] == "Bear Analyst: bear second"


@pytest.mark.unit
def test_risk_debate_stops_after_a_round_with_nothing_new(fake_jev):
    debate = _run_risk_debate(
        ConditionalLogic(max_risk_discuss_rounds=4),
        ["a1", f"a2 {REPEAT}"], ["c1", f"c2 {REPEAT}"], ["n1", f"n2 {REPEAT}"],
    )
    assert debate["count"] == 6  # two of four rounds held
    assert debate["new_argument"] == [None] * 3 + [0.1] * 3


@pytest.mark.unit
def test_a_failed_check_keeps_the_debate_going(monkeypatch, caplog):
    pytest.importorskip("typesafe_sdk")
    client = FakeJev(fail=True)
    monkeypatch.setattr(dj, "jev_client", lambda: client)
    with caplog.at_level(logging.WARNING):
        debate = _run_investment_debate(
            ConditionalLogic(max_debate_rounds=3),
            [f"b {REPEAT}"] * 3, [f"r {REPEAT}"] * 3,
        )
    assert debate["count"] == 6
    assert debate["new_argument"] == [None] * 6
    assert "holding the configured rounds" in caplog.text


# ---------------------------------------------------------------------------
# Long debates fit Jev's input limit
# ---------------------------------------------------------------------------

_TURNS = ["Bull Analyst: " + "a" * 50, "Bear Analyst: " + "b" * 50, "Bull Analyst: " + "c" * 50]
_LONG = "\n" + "\n".join(_TURNS)  # as the debaters build ``history``


@pytest.mark.unit
def test_a_debate_that_fits_is_sent_whole():
    assert dj.latest_turns(_LONG, len(_LONG)) == _LONG.strip()


@pytest.mark.unit
def test_a_long_debate_keeps_its_latest_whole_turns():
    last_two = "\n".join(_TURNS[1:])
    budget = len(dj.OMITTED) + 1 + len(last_two)
    # Exactly room for the last two turns: the turn starting at the cut is kept.
    assert dj.latest_turns(_LONG, budget) == f"{dj.OMITTED}\n{last_two}"
    # One character less: the cut falls inside it, and it goes whole.
    assert dj.latest_turns(_LONG, budget - 1) == f"{dj.OMITTED}\n{_TURNS[2]}"


@pytest.mark.unit
def test_a_turn_longer_than_the_budget_is_cut_from_its_start():
    trimmed = dj.latest_turns(_LONG, len(dj.OMITTED) + 21)
    assert trimmed == f"{dj.OMITTED}\n{'c' * 20}"


@pytest.mark.unit
def test_a_long_debate_is_judged_against_its_latest_turns(fake_jev, monkeypatch):
    monkeypatch.setattr(dj, "MAX_STATE_CHARS", 230)  # each turn is 74 characters
    _run_investment_debate(
        ConditionalLogic(max_debate_rounds=3),
        ["b" * 60, "b" * 60], ["r" * 60, "r" * 60],
    )
    (first, _), (second, _) = fake_jev.requests
    assert first["prior_turns"] == f"Bull Analyst: {'b' * 60}\nBear Analyst: {'r' * 60}"
    # Three turns before the fourth pass the budget; the openings go.
    assert second["prior_turns"] == f"{dj.OMITTED}\nBull Analyst: {'b' * 60}"
    assert len(second["prior_turns"]) + len(second["latest_turn"]) <= 230


@pytest.mark.unit
def test_each_side_gets_half_the_budget(fake_jev, monkeypatch):
    monkeypatch.setattr(dj, "MAX_STATE_CHARS", 200)
    bull = "\n" + "\n".join(f"Bull Analyst: point {i} " + "x" * 30 for i in range(5))
    bear = "\n" + "\n".join(f"Bear Analyst: point {i} " + "y" * 30 for i in range(5))
    assert dj.stronger_side(bull, bear) is not None
    [(state, _)] = fake_jev.requests
    for side in ("bull_case", "bear_case"):
        assert state[side].startswith(dj.OMITTED)
        assert len(state[side]) <= 100
        assert state[side].endswith("point 4 " + ("x" if side == "bull_case" else "y") * 30)


# ---------------------------------------------------------------------------
# The Research Manager's hint
# ---------------------------------------------------------------------------


def _rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "\nBull Analyst: up\nBear Analyst: down",
            "bull_history": "\nBull Analyst: up",
            "bear_history": "\nBear Analyst: down",
            "current_response": "Bear Analyst: down",
            "judge_decision": "",
            "count": 4,
            "new_argument": [None, None, 0.1, 0.1],
        },
    }


def _run_rm(state):
    captured = {}
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("free text")
    llm.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or MagicMock(content="**Recommendation**: Hold")
    )
    result = create_research_manager(llm)(state)
    return captured["prompt"], result["investment_debate_state"]


@pytest.mark.unit
def test_research_manager_without_jev_gets_no_hint():
    prompt, debate = _run_rm(_rm_state())
    assert "Independent evidence check" not in prompt
    assert "Bear Analyst: down\n\n## Output" in prompt  # the prompt is as before
    assert debate["stronger_side"] == {}
    assert debate["new_argument"] == [None, None, 0.1, 0.1]  # kept for the run log


@pytest.mark.unit
def test_research_manager_gets_the_stronger_side_as_a_hint(fake_jev):
    prompt, debate = _run_rm(_rm_state())
    assert (
        "judged the bull case better supported (bull 60% · bear 30% · evenly matched 10%)"
        in prompt
    )
    assert "a hint, not a verdict" in prompt
    assert debate["stronger_side"] == {"bull": 0.6, "bear": 0.3, "even": 0.1}
    [(state, questions)] = fake_jev.requests
    assert questions == {"stronger_side"}
    assert state == {"bull_case": "Bull Analyst: up", "bear_case": "Bear Analyst: down"}


@pytest.mark.unit
def test_research_manager_hint_reads_even_when_neither_side_leads(fake_jev):
    fake_jev.sides = {"bull": 0.2, "bear": 0.3, "even": 0.5}
    prompt, _ = _run_rm(_rm_state())
    assert "judged the two cases evenly matched" in prompt


@pytest.mark.unit
def test_research_manager_hint_names_no_side_on_a_narrow_lead(fake_jev):
    # A live answer on two well-evidenced cases (2026-09-24): a lead of a few points.
    fake_jev.sides = {"bull": 0.27, "bear": 0.39, "even": 0.34}
    prompt, _ = _run_rm(_rm_state())
    assert "found no clear winner (bull 27% · bear 39% · evenly matched 34%)" in prompt


@pytest.mark.unit
def test_research_manager_decides_without_a_hint_when_jev_fails(monkeypatch):
    pytest.importorskip("typesafe_sdk")
    monkeypatch.setattr(dj, "jev_client", lambda: FakeJev(fail=True))
    prompt, debate = _run_rm(_rm_state())
    assert "Independent evidence check" not in prompt
    assert debate["stronger_side"] == {}


@pytest.mark.unit
def test_no_side_check_when_a_side_never_spoke(fake_jev):
    state = _rm_state()
    state["investment_debate_state"]["bear_history"] = ""
    prompt, debate = _run_rm(state)
    assert fake_jev.requests == []
    assert debate["stronger_side"] == {}


@pytest.mark.unit
def test_a_missing_sdk_is_reported_once_not_per_turn(monkeypatch, caplog):
    import builtins

    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-key")
    real_import = builtins.__import__

    def no_sdk(name, *a, **k):
        if name == "typesafe_sdk":
            raise ImportError("no typesafe_sdk")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_sdk)
    jev._warn_sdk_missing.cache_clear()
    with caplog.at_level(logging.WARNING):
        debate = _run_investment_debate(ConditionalLogic(max_debate_rounds=4), [], [])
    assert debate["new_argument"] == [None] * 8
    assert caplog.text.count("typesafe-sdk is not installed") == 1


@pytest.mark.unit
def test_portfolio_manager_keeps_the_risk_scores():
    state = {
        **_REPORTS,
        "investment_plan": "plan",
        "risk_debate_state": {
            "history": "h", "aggressive_history": "a", "conservative_history": "c",
            "neutral_history": "n", "latest_speaker": "Neutral",
            "current_aggressive_response": "a", "current_conservative_response": "c",
            "current_neutral_response": "n", "judge_decision": "", "count": 3,
            "new_argument": [None, None, None],
        },
    }
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("free text")
    llm.invoke.return_value = MagicMock(content="**Rating**: Hold")
    result = create_portfolio_manager(llm)(state)
    assert result["risk_debate_state"]["new_argument"] == [None, None, None]


# ---------------------------------------------------------------------------
# The questions themselves
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_questions_are_valid_sdk_questions():
    pytest.importorskip("typesafe_sdk")
    from typesafe_sdk import Choice, Noul

    questions = dj._questions()
    assert isinstance(questions["turn"]["new_argument"], Noul)
    sides = questions["sides"]["stronger_side"]
    assert isinstance(sides, Choice)
    assert tuple(sides.criteria) == dj.SIDES
