"""Tests for benchmark_agent / benchmark_agents **kwargs forwarding."""

from __future__ import annotations

from unittest.mock import patch

from tradingagents.agents.base_agent import BaseAgent
from tradingagents.agents.benchmark import (
    BenchmarkReport,
    LLMBackend,
    benchmark_agent,
    benchmark_agents,
)
from tradingagents.agents.utils.schemas import AgentInput, AgentOutput

_DUMMY_OUTPUT = AgentOutput(
    rating="HOLD", confidence=0.5, thesis="test", risk_factors=[]
)
_INPUT = AgentInput(ticker="TEST", date="2026-01-01")
_BACKENDS = [LLMBackend(provider="openai", model="gpt-test")]


class SimpleAgent(BaseAgent):
    """Agent that only takes llm."""

    name = "simple"

    def __init__(self, llm):
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return _DUMMY_OUTPUT


class KwargsAgent(BaseAgent):
    """Agent that requires extra kwargs."""

    name = "kwargs_agent"

    def __init__(self, llm, *, tools=None, system_prompt="default"):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return _DUMMY_OUTPUT


class BrokenAgent(BaseAgent):
    """Agent whose constructor always raises."""

    name = "broken"

    def __init__(self, llm, **kwargs):
        raise RuntimeError("constructor failed")

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        raise NotImplementedError


@patch("tradingagents.agents.benchmark._make_llm", return_value="fake_llm")
def test_simple_agent_backward_compat(mock_llm):
    report = benchmark_agent(SimpleAgent, _INPUT, _BACKENDS)
    assert len(report.results) == 1
    assert report.results[0].output == _DUMMY_OUTPUT
    assert report.results[0].error is None


@patch("tradingagents.agents.benchmark._make_llm", return_value="fake_llm")
def test_agent_with_kwargs(mock_llm):
    report = benchmark_agent(
        KwargsAgent, _INPUT, _BACKENDS, tools=["t1"], system_prompt="custom"
    )
    assert len(report.results) == 1
    assert report.results[0].error is None


@patch("tradingagents.agents.benchmark._make_llm", return_value="fake_llm")
def test_constructor_error_captured(mock_llm):
    report = benchmark_agent(BrokenAgent, _INPUT, _BACKENDS)
    assert len(report.results) == 1
    assert report.results[0].error == "constructor failed"
    assert report.results[0].output is None


@patch("tradingagents.agents.benchmark._make_llm", return_value="fake_llm")
def test_benchmark_agents_forwards_kwargs(mock_llm):
    report = benchmark_agents(
        [SimpleAgent, KwargsAgent], _INPUT, _BACKENDS, tools=["t1"]
    )
    assert len(report.results) == 2
    # SimpleAgent ignores extra kwargs (TypeError), but KwargsAgent uses them.
    # SimpleAgent doesn't accept **kwargs so it will error.
    # Actually SimpleAgent doesn't accept **kwargs — let's verify the error is captured.
    simple_result = report.results[0]
    kwargs_result = report.results[1]
    # SimpleAgent will fail because it doesn't accept 'tools' kwarg
    assert simple_result.error is not None
    # KwargsAgent should succeed
    assert kwargs_result.error is None
    assert kwargs_result.output == _DUMMY_OUTPUT
