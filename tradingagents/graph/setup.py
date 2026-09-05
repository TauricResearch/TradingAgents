# TradingAgents/graph/setup.py

import random
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_factor_extractor,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_sentiment_analyst,
    create_trader,
)
from tradingagents.agents.utils.agent_states import AgentState

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic

# Every target a shared conditional router can return. Each edge driven by the
# router maps all of them, so a fall-through return (e.g. under prompt/i18n/
# refactor drift in the speaker labels) can never hit a missing path_map entry
# and crash LangGraph mid-run (#1088).
DEBATE_PATH_MAP = {
    "Bull Researcher": "Bull Researcher",
    "Bear Researcher": "Bear Researcher",
    "Research Manager": "Research Manager",
}
RISK_ANALYSIS_PATH_MAP = {
    "Aggressive Analyst": "Aggressive Analyst",
    "Conservative Analyst": "Conservative Analyst",
    "Neutral Analyst": "Neutral Analyst",
    "Portfolio Manager": "Portfolio Manager",
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        decision_mode: str = "debate",
        debate_first_speaker: str = "bull",
    ):
        """Initialize with required components.

        decision_mode: "debate" (default) runs Bull/Bear Researcher + Research
        Manager synthesis. "off" skips that layer entirely, Trader reads the
        analysts' reports directly (the original ablation). "structured"
        (trading-workspace TradingAgents#19) replaces it with a single Factor
        Extractor LLM call + a deterministic scorer (decision_model.py) --
        the LLM extracts named factors, a fixed formula makes the call.

        debate_first_speaker: "bull" (default here -- deterministic, for
        direct/test callers), "bear", or "random" -- who opens the research
        debate in "debate" mode. should_continue_debate() (conditional_logic.py)
        just alternates away from whoever last spoke, so this one flag also
        determines who gets the LAST word before Research Manager synthesizes.

        trading-workspace#26 finding (2026-09-04/05): a fixed order (Bull
        always opens, so Bear always speaks last) measurably skews ratings
        bearish -- a 15-ticker paired probe (bull-first vs bear-first, same
        inputs) cut Underweight calls from 4/15 to 1/15 just by swapping who
        speaks last. Neither fixed order is neutral; "random" (resolved HERE,
        once per GraphSetup instance -- i.e. once per decision, since each
        real decision constructs a fresh TradingAgentsGraph/GraphSetup) is
        the actual fix, so neither side gets a structural speaking-order
        advantage over many decisions. DEFAULT_CONFIG's own default is
        "random" (default_config.py) -- "bull" is kept as this constructor's
        own default only for direct callers/tests that want deterministic
        graph shape. Only "debate" mode reads this; "structured"/"off" have
        no researcher debate.
        """
        if decision_mode not in ("debate", "off", "structured"):
            raise ValueError(f"Unknown decision_mode: {decision_mode!r}")
        if debate_first_speaker not in ("bull", "bear", "random"):
            raise ValueError(f"Unknown debate_first_speaker: {debate_first_speaker!r}")
        if debate_first_speaker == "random":
            debate_first_speaker = random.choice(("bull", "bear"))
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.decision_mode = decision_mode
        self.debate_first_speaker = debate_first_speaker

    def setup_graph(
        self, selected_analysts=("market", "social", "news", "fundamentals")
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        plan = build_analyst_execution_plan(selected_analysts)

        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm),
        }

        # Create researcher and manager nodes (skipped entirely below when
        # decision_mode != "debate" -- the ablation, per the workspace's TradingAgents
        # fix-plan, needs a real graph-structural bypass, not max_debate_rounds=0,
        # which does NOT skip Bull Researcher -- see conditional_logic.py).
        if self.decision_mode == "debate":
            bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
            bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
            research_manager_node = create_research_manager(self.deep_thinking_llm)
        elif self.decision_mode == "structured":
            factor_extractor_node = create_factor_extractor(self.quick_thinking_llm)
        # Trader reads state["investment_plan"] in both "debate" and "structured"
        # modes (populated by the Research Manager or the Factor Extractor's
        # deterministic scorer respectively) -- only "off" reads analyst reports
        # directly.
        trader_node = create_trader(self.quick_thinking_llm, debate_enabled=self.decision_mode != "off")

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for spec in plan.specs:
            workflow.add_node(spec.agent_node, analyst_factories[spec.key]())
            workflow.add_node(spec.clear_node, create_msg_delete())
            workflow.add_node(spec.tool_node, self.tool_nodes[spec.key])

        # Add other nodes
        if self.decision_mode == "debate":
            workflow.add_node("Bull Researcher", bull_researcher_node)
            workflow.add_node("Bear Researcher", bear_researcher_node)
            workflow.add_node("Research Manager", research_manager_node)
        elif self.decision_mode == "structured":
            workflow.add_node("Factor Extractor", factor_extractor_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Define edges
        # Start with the first analyst
        workflow.add_edge(START, plan.specs[0].agent_node)

        # Connect analysts in sequence
        for i, spec in enumerate(plan.specs):
            current_analyst = spec.agent_node
            current_tools = spec.tool_node
            current_clear = spec.clear_node

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst, or to the decision layer's entry point
            # if this is the last analyst: Bull Researcher ("debate"), Factor
            # Extractor ("structured"), or straight to Trader ("off").
            if i < len(plan.specs) - 1:
                workflow.add_edge(current_clear, plan.specs[i + 1].agent_node)
            else:
                next_node = {
                    "debate": "Bear Researcher" if self.debate_first_speaker == "bear" else "Bull Researcher",
                    "structured": "Factor Extractor",
                    "off": "Trader",
                }[self.decision_mode]
                workflow.add_edge(current_clear, next_node)

        if self.decision_mode == "debate":
            # Both research-debate edges share the complete DEBATE_PATH_MAP (#1088).
            for debate_node in ("Bull Researcher", "Bear Researcher"):
                workflow.add_conditional_edges(
                    debate_node,
                    self.conditional_logic.should_continue_debate,
                    DEBATE_PATH_MAP,
                )
            workflow.add_edge("Research Manager", "Trader")
        elif self.decision_mode == "structured":
            # Single pass, no debate loop -- straight to Trader.
            workflow.add_edge("Factor Extractor", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        # All three risk edges share the complete RISK_ANALYSIS_PATH_MAP (#1088).
        for risk_node in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
            workflow.add_conditional_edges(
                risk_node,
                self.conditional_logic.should_continue_risk_analysis,
                RISK_ANALYSIS_PATH_MAP,
            )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
