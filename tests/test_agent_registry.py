"""Tests for AgentRegistry — lazy instantiation and failure recovery."""

from __future__ import annotations

import pytest

from tradingagents.agents.base_agent import BaseAgent
from tradingagents.agents.registry import AgentRegistry
from tradingagents.agents.utils.schemas import AgentInput, AgentOutput


class _DummyAgent(BaseAgent):
    name = "dummy"

    def __init__(self, llm=None):
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(
            rating="hold",
            confidence=0.5,
            price_targets={"base": 100.0},
            thesis="test",
            risk_factors=["none"],
        )


class _FailOnceAgent(BaseAgent):
    """Agent whose constructor fails on the first call, succeeds after."""

    name = "fail_once"
    _call_count = 0

    def __init__(self):
        _FailOnceAgent._call_count += 1
        if _FailOnceAgent._call_count == 1:
            raise RuntimeError("transient init failure")

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(
            rating="buy",
            confidence=0.9,
            price_targets={"base": 200.0},
            thesis="recovered",
            risk_factors=[],
        )


class TestAgentRegistry:
    def test_register_and_get_class(self):
        reg = AgentRegistry()
        reg.register("dummy", _DummyAgent)
        agent = reg.get("dummy")
        assert isinstance(agent, _DummyAgent)

    def test_register_and_get_instance(self):
        reg = AgentRegistry()
        inst = _DummyAgent(llm="fake")
        reg.register("dummy", inst)
        assert reg.get("dummy") is inst

    def test_get_unknown_raises(self):
        reg = AgentRegistry()
        with pytest.raises(KeyError, match="no_such"):
            reg.get("no_such")

    def test_factory_survives_failed_instantiation(self):
        """If the constructor throws, the factory must remain so retry works."""
        _FailOnceAgent._call_count = 0
        reg = AgentRegistry()
        reg.register("flaky", _FailOnceAgent)

        with pytest.raises(RuntimeError, match="transient"):
            reg.get("flaky")

        # Factory should still be registered — retry succeeds
        agent = reg.get("flaky")
        assert isinstance(agent, _FailOnceAgent)
        assert agent.name == "fail_once"

    def test_factory_removed_after_success(self):
        """After successful instantiation, factory is cleaned up."""
        reg = AgentRegistry()
        reg.register("dummy", _DummyAgent)
        reg.get("dummy")
        # Factory dict should be empty, instance dict should have it
        assert "dummy" not in reg._factories
        assert "dummy" in reg._instances

    def test_list_and_contains(self):
        reg = AgentRegistry()
        reg.register("a", _DummyAgent)
        reg.register("b", _DummyAgent(llm="x"))
        assert "a" in reg
        assert "b" in reg
        assert reg.list() == ["a", "b"]
        assert len(reg) == 2

    def test_re_register_replaces(self):
        reg = AgentRegistry()
        reg.register("x", _DummyAgent)
        agent1 = reg.get("x")
        reg.register("x", _DummyAgent, llm="new")
        agent2 = reg.get("x")
        assert agent1 is not agent2

    def test_register_invalid_type(self):
        reg = AgentRegistry()
        with pytest.raises(TypeError, match="Expected BaseAgent"):
            reg.register("bad", "not_an_agent")  # type: ignore[arg-type]
