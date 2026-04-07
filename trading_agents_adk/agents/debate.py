"""Debate orchestration using ADK SequentialAgent and LoopAgent.

Maps the LangGraph conditional debate loops to ADK workflow agents:
- Investment Debate: Bull <-> Bear (LoopAgent) -> Research Manager
- Risk Debate: Aggressive -> Conservative -> Neutral (LoopAgent)
"""

from google.adk.agents import SequentialAgent, LoopAgent

from .researchers import create_bull_researcher, create_bear_researcher, create_research_manager
from .risk_analysts import create_aggressive_analyst, create_conservative_analyst, create_neutral_analyst


def create_investment_debate(
    model: str = "gemini-2.5-flash",
    deep_model: str = "gemini-2.5-pro",
    max_rounds: int = 1,
) -> SequentialAgent:
    """Create the investment debate pipeline.

    Structure:
      LoopAgent(Bull -> Bear, max_iterations=max_rounds) -> Research Manager

    The Bull and Bear researchers take turns debating, then the Research Manager
    judges the debate and produces an investment plan.

    Args:
        model: Model for the bull/bear researchers
        deep_model: Model for the research manager (needs deeper reasoning)
        max_rounds: Number of debate rounds (each round = 1 bull + 1 bear turn)

    Returns:
        A SequentialAgent that runs the full investment debate.
    """
    bull = create_bull_researcher(model)
    bear = create_bear_researcher(model)

    debate_loop = LoopAgent(
        name="InvestmentDebateLoop",
        sub_agents=[bull, bear],
        max_iterations=max_rounds,
    )

    manager = create_research_manager(deep_model)

    return SequentialAgent(
        name="InvestmentDebate",
        sub_agents=[debate_loop, manager],
    )


def create_risk_debate(
    model: str = "gemini-2.5-flash",
    max_rounds: int = 1,
) -> LoopAgent:
    """Create the risk management debate pipeline.

    Structure:
      LoopAgent(Aggressive -> Conservative -> Neutral, max_iterations=max_rounds)

    Three risk analysts with different perspectives take turns debating
    the trader's proposal.

    Args:
        model: Model for the risk analysts
        max_rounds: Number of full debate rounds

    Returns:
        A LoopAgent that runs the risk debate.
    """
    aggressive = create_aggressive_analyst(model)
    conservative = create_conservative_analyst(model)
    neutral = create_neutral_analyst(model)

    return LoopAgent(
        name="RiskDebate",
        sub_agents=[aggressive, conservative, neutral],
        max_iterations=max_rounds,
    )
