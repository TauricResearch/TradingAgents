# TradingAgents/graph/setup.py

from typing import Any, Callable, Dict, List
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.structured import extract_analyst_signal

from .conditional_logic import ConditionalLogic
from .signal_fusion import create_signal_fusion_node, equal_weights


# Mapping from the user-facing analyst selector keys to the graph
# node-name "label" (capitalised, used in compiled node IDs) and the
# per-analyst messages-channel key used in the parallel graph.
_ANALYST_META = {
    "market": {
        "label": "Market",
        "messages_key": "market_messages",
        "factory": "create_market_analyst",
        "report_field": "market_report",
        "channel_name": "market",
    },
    "social": {
        # The "social" wire-value is kept for back-compat with saved
        # configs; the underlying agent is create_sentiment_analyst.
        "label": "Social",
        "messages_key": "sentiment_messages",
        "factory": "create_sentiment_analyst",
        "report_field": "sentiment_report",
        "channel_name": "social",
    },
    "news": {
        "label": "News",
        "messages_key": "news_messages",
        "factory": "create_news_analyst",
        "report_field": "news_report",
        "channel_name": "news",
    },
    "fundamentals": {
        "label": "Fundamentals",
        "messages_key": "fundamentals_messages",
        "factory": "create_fundamentals_analyst",
        "report_field": "fundamentals_report",
        "channel_name": "fundamentals",
    },
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph.

    Two topologies are supported, picked by ``signal_fusion_enabled``:

    - **Parallel + fusion** (default): the four analysts run concurrently
      from ``START``, each on its own ``*_messages`` channel; each
      analyst's tool loop ends in an ``Extract <Analyst>`` node that
      converts its markdown report to an ``AnalystSignal``; all four
      extractors fan into ``SignalFusion`` which computes the composite
      score before handing off to the Bull Researcher.

    - **Legacy serial** (``signal_fusion_enabled=False``): the v0.2.5
      topology is reproduced verbatim — analysts run in sequence, share
      the ``messages`` channel, no extraction, no fusion. This path
      exists for two reasons: it preserves v0.2.4 / v0.2.5 checkpoint
      compatibility, and it gives the user a clean A/B comparison when
      evaluating whether the fusion layer is paying for itself.
    """

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        *,
        signal_fusion_enabled: bool = True,
        weight_fn: Callable[[List[str]], Dict[str, float]] | None = None,
        weight_estimator=None,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.signal_fusion_enabled = signal_fusion_enabled
        self.weight_fn = weight_fn or equal_weights
        self.weight_estimator = weight_estimator

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")
        for a in selected_analysts:
            if a not in _ANALYST_META:
                raise ValueError(
                    f"Trading Agents Graph Setup Error: unknown analyst '{a}'. "
                    f"Valid options: {list(_ANALYST_META.keys())}"
                )

        if self.signal_fusion_enabled:
            return self._build_parallel_graph(selected_analysts)
        return self._build_legacy_serial_graph(selected_analysts)

    # ------------------------------------------------------------------
    # Shared builders
    # ------------------------------------------------------------------

    def _build_post_analysis_pipeline(self, workflow: StateGraph) -> None:
        """Add the Bull/Bear → RM → Trader → Risk → PM pipeline.

        Identical in both topologies — fusion vs serial only differs
        upstream of the Bull Researcher.
        """
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_edge("Portfolio Manager", END)

    # ------------------------------------------------------------------
    # Parallel + SignalFusion path (default)
    # ------------------------------------------------------------------

    def _build_parallel_graph(self, selected_analysts: list[str]) -> StateGraph:
        workflow = StateGraph(AgentState)

        # Build & wire each analyst sub-pipeline.
        for analyst in selected_analysts:
            meta = _ANALYST_META[analyst]
            factory = globals()[meta["factory"]]
            analyst_node = factory(
                self.quick_thinking_llm,
                messages_key=meta["messages_key"],
                channel_name=meta["channel_name"],
            )
            extractor_node = self._make_extractor_node(analyst, meta)

            analyst_label = f"{meta['label']} Analyst"
            tools_label = f"tools_{analyst}"
            extract_label = f"Extract {meta['label']}"

            workflow.add_node(analyst_label, analyst_node)
            workflow.add_node(extract_label, extractor_node)
            workflow.add_node(tools_label, self.tool_nodes[analyst])

            workflow.add_edge(START, analyst_label)
            workflow.add_conditional_edges(
                analyst_label,
                getattr(self.conditional_logic, f"should_continue_{analyst}"),
                [tools_label, extract_label],
            )
            workflow.add_edge(tools_label, analyst_label)
            workflow.add_edge(extract_label, "Signal Fusion")

        # The SignalFusion node fans in all four extractors and writes
        # composite signal fields. With equal_weights this commit is
        # behavior-neutral upstream of the Bull/Bear prompt; commit 2
        # swaps in a real estimator and rewires the prompts.
        workflow.add_node(
            "Signal Fusion",
            create_signal_fusion_node(
                weight_fn=self.weight_fn,
                weight_estimator=self.weight_estimator,
            ),
        )
        workflow.add_edge("Signal Fusion", "Bull Researcher")

        self._build_post_analysis_pipeline(workflow)
        return workflow

    def _make_extractor_node(self, analyst: str, meta: dict):
        """Return a node that idempotently writes a fallback ``AnalystSignal``.

        The analyst node already calls ``extract_analyst_signal`` inline
        when its tool loop ends (see the four analyst factories), so under
        normal flow the signal is already present in
        ``state['analyst_signals']`` by the time this node runs. The
        extractor node is a *safety net*: when the analyst exited
        without producing a structured signal (budget hit before the
        final markdown was ever produced, or a provider hiccup), this
        node guarantees the channel still appears in
        ``state['analyst_signals']`` so SignalFusion's key set is
        predictable.
        """
        report_field = meta["report_field"]
        channel = meta["channel_name"]

        def _extractor(state):
            signals = state.get("analyst_signals") or {}
            if channel in signals:
                return {}
            report = state.get(report_field) or ""
            if not report:
                # No markdown to extract from — let SignalFusion treat
                # this channel as missing rather than emitting a
                # noise-floor signal.
                return {}
            signal = extract_analyst_signal(
                llm=self.quick_thinking_llm,
                markdown_report=report,
                analyst_name=f"{meta['label']} Analyst",
                ticker=state["company_of_interest"],
            )
            return {"analyst_signals": {channel: signal}}

        return _extractor

    # ------------------------------------------------------------------
    # Legacy serial path (signal_fusion_enabled=False)
    # ------------------------------------------------------------------

    def _build_legacy_serial_graph(self, selected_analysts: list[str]) -> StateGraph:
        """Reconstruct the v0.2.5 serial topology verbatim.

        Used for the kill-switch path and for resuming pre-fusion
        SqliteSaver checkpoints. No extraction, no fusion, shared
        ``messages`` channel.
        """
        analyst_nodes = {}
        delete_nodes = {}

        for analyst in selected_analysts:
            meta = _ANALYST_META[analyst]
            factory = globals()[meta["factory"]]
            # Legacy: shared "messages" channel, no AnalystSignal extraction.
            analyst_nodes[analyst] = factory(
                self.quick_thinking_llm,
                messages_key="messages",
                channel_name=None,
            )
            delete_nodes[analyst] = create_msg_delete()

        workflow = StateGraph(AgentState)

        for analyst in selected_analysts:
            meta = _ANALYST_META[analyst]
            workflow.add_node(f"{meta['label']} Analyst", analyst_nodes[analyst])
            workflow.add_node(f"Msg Clear {meta['label']}", delete_nodes[analyst])
            workflow.add_node(f"tools_{analyst}", self.tool_nodes[analyst])

        first_analyst = selected_analysts[0]
        first_label = _ANALYST_META[first_analyst]["label"]
        workflow.add_edge(START, f"{first_label} Analyst")

        for i, analyst in enumerate(selected_analysts):
            meta = _ANALYST_META[analyst]
            current_analyst = f"{meta['label']} Analyst"
            current_tools = f"tools_{analyst}"
            current_clear = f"Msg Clear {meta['label']}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_meta = _ANALYST_META[selected_analysts[i + 1]]
                workflow.add_edge(current_clear, f"{next_meta['label']} Analyst")
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        self._build_post_analysis_pipeline(workflow)
        return workflow
