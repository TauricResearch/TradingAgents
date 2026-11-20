"""Graph-wiring contract for the deterministic Safety Gate (Candidate B).

Written BEFORE implementation and expected to genuinely FAIL until wired:
Portfolio Manager -> Safety Gate -> END, with no direct Portfolio Manager -> END,
for every analyst selection. Required report keys must follow
build_analyst_execution_plan, not a hardcoded all-four set.

Coverage: REQ-SG-01, REQ-SG-06; INV-SG-01.
"""

from __future__ import annotations

import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup

END, PM, GATE = "__end__", "Portfolio Manager", "Safety Gate"
SELECTIONS = [("market", "social", "news", "fundamentals"), ("market", "news"), ("fundamentals",)]


class _DummyLLM:
    """Minimal stand-in: satisfies structured-bind inspection, never runs.

    Explicit methods only: an unexpected call raises, so accidental runtime use
    cannot be silently accepted.
    """

    def with_structured_output(self, *a, **k):
        return self

    def bind_tools(self, *a, **k):
        raise AssertionError("wiring setup must not bind tools")


def _edges(selected):
    setup = GraphSetup(_DummyLLM(), _DummyLLM(),
                       ConditionalLogic(DEFAULT_CONFIG["max_debate_rounds"],
                                        DEFAULT_CONFIG["max_risk_discuss_rounds"]),
                       DEFAULT_CONFIG["max_tool_rounds"])
    graph = setup.setup_graph(selected).compile().get_graph()
    return {(e.source, e.target) for e in graph.edges}, set(graph.nodes)


@pytest.mark.unit
@pytest.mark.parametrize("selected", SELECTIONS)
def test_gate_between_pm_and_end_without_bypass(selected):
    edges, nodes = _edges(selected)

    assert GATE in nodes, "the Safety Gate node must exist"
    assert (PM, GATE) in edges, "Portfolio Manager must flow into the Safety Gate"
    assert (GATE, END) in edges, "the Safety Gate must terminate the graph"
    assert (PM, END) not in edges, "a direct Portfolio Manager -> END bypasses the gate"
