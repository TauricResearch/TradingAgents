# TradingAgents/graph/analyst_subgraph.py
"""Per-analyst ReAct subgraphs with isolated message channels.

The four analysts are independent: each reads the shared run inputs (ticker,
date, resolved identity) and writes exactly one ``*_report`` field, never
another analyst's output. Previously they ran as one sequential chain
sharing a single ``messages`` channel, cleared between each. Sharing that
channel is the only reason they could not run at once.

Each analyst is wrapped here in its own compiled subgraph with a private
``messages`` channel. The parent graph fans out to the wrapper nodes in a
single superstep (so they run concurrently) and fans back in at the Bull
Researcher. Only the analyst's ``report_key`` crosses back to the parent —
the tool-call scratchpad stays inside the subgraph and is discarded — so
concurrent analysts can never clobber each other's messages.
"""

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from tradingagents.agents.utils.agent_states import AgentState

from .analyst_execution import AnalystNodeSpec


def build_analyst_subgraph(
    spec: AnalystNodeSpec,
    analyst_node: Callable,
    tool_node: Any,
    should_continue: Callable,
):
    """Compile an isolated ReAct subgraph for one analyst.

    Mirrors the old inline wiring (analyst -> tools -> analyst loop) but with
    its own ``messages`` channel. ``should_continue`` returns either
    ``spec.tool_node`` (keep looping) or ``spec.clear_node`` (done) — the
    latter maps to END here, which discards the subgraph's messages instead of
    routing through a Msg Clear node.
    """
    sub = StateGraph(AgentState)
    sub.add_node(spec.agent_node, analyst_node)
    sub.add_node(spec.tool_node, tool_node)
    sub.add_edge(START, spec.agent_node)
    sub.add_conditional_edges(
        spec.agent_node,
        should_continue,
        {spec.tool_node: spec.tool_node, spec.clear_node: END},
    )
    sub.add_edge(spec.tool_node, spec.agent_node)
    return sub.compile()


def make_analyst_wrapper(compiled_subgraph, spec: AnalystNodeSpec) -> Callable:
    """Wrap a compiled analyst subgraph as a single parent-graph node.

    Builds a *fresh* input state for the subgraph (its own one-message seed),
    so the parent's ``messages`` channel is never touched and parallel wrappers
    share no mutable message state. Returns only the analyst's report field to
    the parent.
    """

    def analyst_wrapper_node(state):
        out = compiled_subgraph.invoke(
            {
                "messages": [("human", state["company_of_interest"])],
                "company_of_interest": state["company_of_interest"],
                "asset_type": state.get("asset_type", "stock"),
                "instrument_context": state.get("instrument_context", ""),
                "trade_date": state["trade_date"],
            }
        )
        return {spec.report_key: out.get(spec.report_key, "")}

    return analyst_wrapper_node
