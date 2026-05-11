"""BaseAgent implementations for the four analyst types.

Each class wraps the existing analyst logic behind the standardized
``BaseAgent.analyze(AgentInput) -> AgentOutput`` contract while the
original ``create_*`` factory functions remain unchanged for LangGraph
node compatibility.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from tradingagents.agents.base_agent import BaseAgent
from tradingagents.agents.utils.schemas import AgentInput, AgentOutput


def _invoke_structured(llm, role_prompt: str, agent_input: AgentInput) -> AgentOutput:
    """Ask *llm* to produce an ``AgentOutput`` via structured output.

    Schema enforcement is handled entirely by ``with_structured_output``,
    which uses the provider's native mechanism (tool-calling or JSON mode).
    """
    full_prompt = (
        f"{role_prompt}\n\n"
        f"Ticker: {agent_input.ticker}\n"
        f"Date: {agent_input.date}\n"
    )
    if agent_input.context:
        for k, v in agent_input.context.items():
            full_prompt += f"\n--- {k} ---\n{v}\n"

    structured_llm = llm.with_structured_output(AgentOutput)
    return structured_llm.invoke([HumanMessage(content=full_prompt)])


class FundamentalsAgent(BaseAgent):
    """Standardized fundamentals analyst."""

    name: str = "fundamentals_analyst"

    def __init__(self, llm) -> None:
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return _invoke_structured(
            self.llm,
            "You are a fundamentals analyst. Evaluate the company's financial health "
            "using balance sheets, cash flow, income statements, and key ratios.",
            agent_input,
        )


class SentimentAgent(BaseAgent):
    """Standardized sentiment / social-media analyst."""

    name: str = "sentiment_analyst"

    def __init__(self, llm) -> None:
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return _invoke_structured(
            self.llm,
            "You are a sentiment analyst. Evaluate public sentiment from social media, "
            "news headlines, and community discussions about the company.",
            agent_input,
        )


class NewsAgent(BaseAgent):
    """Standardized news analyst."""

    name: str = "news_analyst"

    def __init__(self, llm) -> None:
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return _invoke_structured(
            self.llm,
            "You are a news analyst. Evaluate recent news, macroeconomic events, "
            "and geopolitical developments relevant to the company.",
            agent_input,
        )


class TechnicalAgent(BaseAgent):
    """Standardized technical / market analyst."""

    name: str = "technical_analyst"

    def __init__(self, llm) -> None:
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        return _invoke_structured(
            self.llm,
            "You are a technical analyst. Evaluate price action, volume, moving averages, "
            "MACD, RSI, Bollinger Bands, and other technical indicators.",
            agent_input,
        )
