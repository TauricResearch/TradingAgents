"""Tests for the debate_enabled=False ablation (workspace TradingAgents fix-plan,
2026-08-16): whether the Bull/Bear Researcher debate + Research Manager
synthesis layer itself adds value, versus a backbone-model change, per
independent literature (arXiv:2603.27539) finding the debate layer -- not
model quality -- drives most of TradingAgents/FinCon's reported edge.

max_debate_rounds=0 does NOT skip the debate layer -- the graph unconditionally
routes through Bull Researcher once before should_continue_debate's round-count
check ever applies (conditional_logic.py), so rounds=0 gives one uncontested
bull argument with no bear rebuttal, not "no debate." debate_enabled=False is
a real graph-structural bypass instead: Bull/Bear Researcher and Research
Manager are never added to the graph at all, and the Trader reads the four
analysts' reports directly.
"""
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.schemas import TraderAction, TraderProposal
from tradingagents.agents.trader.trader import create_trader
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup

_DEBATE_NODES = {"Bull Researcher", "Bear Researcher", "Research Manager"}


def _build_graph(decision_mode: str):
    """Builds a real compiled graph with mocked LLM/tool-node objects -- node
    *factories* like create_bull_researcher(llm) just build closures, they
    never call the LLM, so this is free and needs no API key."""
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    tool_nodes = {k: MagicMock() for k in ("market", "social", "news", "fundamentals")}
    llm = MagicMock()
    gs = GraphSetup(llm, llm, tool_nodes, cl, decision_mode=decision_mode)
    workflow = gs.setup_graph(("market",))
    return workflow.compile()


@pytest.mark.unit
class TestDebateAblationGraphStructure:
    def test_debate_enabled_true_includes_debate_nodes(self):
        graph = _build_graph(decision_mode="debate")
        nodes = set(graph.get_graph().nodes.keys())
        assert nodes >= _DEBATE_NODES

    def test_debate_enabled_false_excludes_debate_nodes(self):
        graph = _build_graph(decision_mode="off")
        nodes = set(graph.get_graph().nodes.keys())
        assert not (_DEBATE_NODES & nodes)
        # Everything else must still be present -- this ablates ONLY the
        # debate/coordination layer, not the analysts or risk debate.
        assert {"Trader", "Portfolio Manager", "Aggressive Analyst",
                "Conservative Analyst", "Neutral Analyst"} <= nodes

    def test_default_graph_setup_still_includes_debate(self):
        """decision_mode's default ("debate") must not silently change existing
        callers that don't pass it at all."""
        cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        tool_nodes = {k: MagicMock() for k in ("market", "social", "news", "fundamentals")}
        llm = MagicMock()
        gs = GraphSetup(llm, llm, tool_nodes, cl)  # no decision_mode kwarg
        graph = gs.setup_graph(("market",)).compile()
        assert set(graph.get_graph().nodes.keys()) >= _DEBATE_NODES


@pytest.mark.unit
class TestStructuredDecisionModeGraphStructure:
    """decision_mode="structured" (trading-workspace TradingAgents#19): a
    third arm alongside debate on/off -- Factor Extractor replaces the
    debate nodes, single pass straight to Trader, no debate loop."""

    def test_structured_mode_includes_factor_extractor_excludes_debate_nodes(self):
        graph = _build_graph(decision_mode="structured")
        nodes = set(graph.get_graph().nodes.keys())
        assert "Factor Extractor" in nodes
        assert not (_DEBATE_NODES & nodes)
        assert {"Trader", "Portfolio Manager", "Aggressive Analyst",
                "Conservative Analyst", "Neutral Analyst"} <= nodes

    def test_unknown_decision_mode_raises(self):
        cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        tool_nodes = {k: MagicMock() for k in ("market", "social", "news", "fundamentals")}
        llm = MagicMock()
        with pytest.raises(ValueError, match="Unknown decision_mode"):
            GraphSetup(llm, llm, tool_nodes, cl, decision_mode="bogus")


@pytest.mark.unit
class TestDebateFirstSpeaker:
    """trading-workspace#26 (2026-09-05): a fixed Bull-first/Bear-last debate
    order measurably skews ratings bearish (a 15-ticker paired probe cut
    Underweight calls 4/15 -> 1/15 by swapping who spoke last). Fix is
    debate_first_speaker="random" (DEFAULT_CONFIG's own default), resolved
    once per GraphSetup instance -- i.e. once per decision."""

    def _entry_node(self, debate_first_speaker):
        cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        tool_nodes = {k: MagicMock() for k in ("market", "social", "news", "fundamentals")}
        llm = MagicMock()
        gs = GraphSetup(llm, llm, tool_nodes, cl, decision_mode="debate",
                         debate_first_speaker=debate_first_speaker)
        graph = gs.setup_graph(("market",)).compile()
        targets = [e.target for e in graph.get_graph().edges if e.source == "Msg Clear Market"]
        assert len(targets) == 1
        return targets[0], gs.debate_first_speaker

    def test_bull_first_enters_at_bull_researcher(self):
        entry, resolved = self._entry_node("bull")
        assert entry == "Bull Researcher"
        assert resolved == "bull"

    def test_bear_first_enters_at_bear_researcher(self):
        entry, resolved = self._entry_node("bear")
        assert entry == "Bear Researcher"
        assert resolved == "bear"

    def test_random_resolves_to_a_valid_concrete_choice(self):
        """"random" must never leak through to the graph itself -- setup_graph's
        next_node lookup only knows "bull"/"bear" for decision_mode="debate"."""
        entry, resolved = self._entry_node("random")
        assert resolved in ("bull", "bear")
        assert entry == ("Bull Researcher" if resolved == "bull" else "Bear Researcher")

    def test_random_hits_both_branches_over_many_draws(self):
        """A real distribution check, not just a valid-value check -- guards
        against e.g. a copy-paste that always returns the same branch."""
        seen = {self._entry_node("random")[1] for _ in range(50)}
        assert seen == {"bull", "bear"}

    def test_default_graph_setup_still_uses_bull(self):
        """GraphSetup's OWN default stays deterministic ("bull") for direct/
        test callers -- only DEFAULT_CONFIG's default is "random" (that's a
        trading_graph.py-level choice, not this constructor's)."""
        cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        tool_nodes = {k: MagicMock() for k in ("market", "social", "news", "fundamentals")}
        llm = MagicMock()
        gs = GraphSetup(llm, llm, tool_nodes, cl, decision_mode="debate")  # no debate_first_speaker kwarg
        assert gs.debate_first_speaker == "bull"

    def test_unknown_debate_first_speaker_raises(self):
        cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        tool_nodes = {k: MagicMock() for k in ("market", "social", "news", "fundamentals")}
        llm = MagicMock()
        with pytest.raises(ValueError, match="Unknown debate_first_speaker"):
            GraphSetup(llm, llm, tool_nodes, cl, decision_mode="debate", debate_first_speaker="bogus")


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    if proposal is None:
        proposal = TraderProposal(action=TraderAction.BUY, reasoning="Strong setup.")
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderDebateAblation:
    def test_debate_enabled_reads_investment_plan(self):
        """Existing (default) behavior: reads the Research Manager's plan,
        not the raw analyst reports."""
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm, debate_enabled=True)
        state = {"company_of_interest": "NVDA", "investment_plan": "**Recommendation**: Buy"}
        result = trader(state)
        prompt = captured["prompt"]
        assert any("Proposed Investment Plan" in m["content"] for m in prompt)
        # debate_enabled=True must NOT overwrite investment_plan -- it's the
        # Research Manager's real output, not the ablation sentinel.
        assert "investment_plan" not in result

    def test_debate_disabled_reads_analyst_reports_directly(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm, debate_enabled=False)
        state = {
            "company_of_interest": "NVDA",
            "market_report": "RSI 70, overbought.",
            "sentiment_report": "Bullish social chatter.",
            "news_report": "Guidance raised.",
            "fundamentals_report": "P/E 45x.",
        }
        trader(state)
        prompt = captured["prompt"]
        user_content = " ".join(m["content"] for m in prompt if m["role"] == "user")
        assert "RSI 70, overbought." in user_content
        assert "Bullish social chatter." in user_content
        assert "Guidance raised." in user_content
        assert "P/E 45x." in user_content
        assert "Proposed Investment Plan" not in user_content

    def test_debate_disabled_sets_investment_plan_sentinel(self):
        """Portfolio Manager reads state["investment_plan"] unconditionally --
        without this, a debate-off run would KeyError deep in a downstream
        node instead of failing clearly at the point the step was skipped."""
        llm = _structured_trader_llm({})
        trader = create_trader(llm, debate_enabled=False)
        state = {"company_of_interest": "NVDA", "market_report": "", "sentiment_report": "",
                  "news_report": "", "fundamentals_report": ""}
        result = trader(state)
        assert "investment_plan" in result
        assert "debate" in result["investment_plan"].lower()
