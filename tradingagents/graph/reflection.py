# TradingAgents/graph/reflection.py

from typing import Any

from langchain_openai import ChatOpenAI


class Reflector:
    """Handles reflection on decisions and updating memory."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()

    def _get_reflection_prompt(self) -> str:
        """Get the system prompt for reflection."""
        return """
You are an expert financial analyst tasked with reviewing trading decisions/analysis and providing a comprehensive, step-by-step analysis. 
Your goal is to deliver detailed insights into investment decisions and highlight opportunities for improvement, adhering strictly to the following guidelines:

1. Reasoning:
   - For each trading decision, determine whether it was correct or incorrect. A correct decision results in an increase in returns, while an incorrect decision does the opposite.
   - Analyze the contributing factors to each success or mistake. Consider:
     - Market intelligence.
     - Technical indicators.
     - Technical signals.
     - Price movement analysis.
     - Overall market data analysis 
     - News analysis.
     - Social media and sentiment analysis.
     - Fundamental data analysis.
     - Weight the importance of each factor in the decision-making process.

2. Improvement:
   - For any incorrect decisions, propose revisions to maximize returns.
   - Provide a detailed list of corrective actions or improvements, including specific recommendations (e.g., changing a decision from HOLD to BUY on a particular date).

3. Summary:
   - Summarize the lessons learned from the successes and mistakes.
   - Highlight how these lessons can be adapted for future trading scenarios and draw connections between similar situations to apply the knowledge gained.

4. Query:
   - Extract key insights from the summary into a concise sentence of no more than 1000 tokens.
   - Ensure the condensed sentence captures the essence of the lessons and reasoning for easy reference.

Adhere strictly to these instructions, and ensure your output is detailed, accurate, and actionable. You will also be given objective descriptions of the market from a price movements, technical indicator, news, and sentiment perspective to provide more context for your analysis.
"""

    def _extract_current_situation(self, current_state: dict[str, Any]) -> str:
        """Extract the current market situation from the state."""
        curr_market_report = current_state["market_report"]
        curr_sentiment_report = current_state["sentiment_report"]
        curr_news_report = current_state["news_report"]
        curr_fundamentals_report = current_state["fundamentals_report"]

        return f"{curr_market_report}\n\n{curr_sentiment_report}\n\n{curr_news_report}\n\n{curr_fundamentals_report}"

    def _reflect_on_component(
        self, component_type: str, report: str, situation: str, returns_losses: float
    ) -> str:
        """Generate reflection for a component."""
        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]

        result = self.quick_thinking_llm.invoke(messages).content
        return result

    def _reflect(
        self,
        component_type: str,
        state_key: str | tuple[str, str],
        current_state: Any,
        returns_losses: float,
        memory: Any,
    ) -> None:
        """Run the reflect-and-remember cycle for one component.

        Args:
            component_type: Label identifying the component (e.g. "BULL", "TRADER").
            state_key: Key to extract the component's history from *current_state*.
                Pass a plain string for a top-level key (e.g. ``"trader_investment_plan"``).
                Pass a ``(outer_key, inner_key)`` tuple for nested access
                (e.g. ``("investment_debate_state", "bull_history")``).
            current_state: The final graph state dict containing all reports and histories.
            returns_losses: Numeric return/loss value used to evaluate the decision.
            memory: Memory store whose ``add_situations`` method records the reflection.
        """
        situation = self._extract_current_situation(current_state)
        if isinstance(state_key, tuple):
            history = current_state[state_key[0]][state_key[1]]
        else:
            history = current_state[state_key]
        result = self._reflect_on_component(component_type, history, situation, returns_losses)
        memory.add_situations([(situation, result)])

    def reflect_bull_researcher(
        self, current_state: Any, returns_losses: float, bull_memory: Any
    ) -> None:
        """Reflect on bull researcher's analysis and update memory."""
        self._reflect(
            "BULL",
            ("investment_debate_state", "bull_history"),
            current_state,
            returns_losses,
            bull_memory,
        )

    def reflect_bear_researcher(
        self, current_state: Any, returns_losses: float, bear_memory: Any
    ) -> None:
        """Reflect on bear researcher's analysis and update memory."""
        self._reflect(
            "BEAR",
            ("investment_debate_state", "bear_history"),
            current_state,
            returns_losses,
            bear_memory,
        )

    def reflect_trader(self, current_state: Any, returns_losses: float, trader_memory: Any) -> None:
        """Reflect on trader's decision and update memory."""
        self._reflect(
            "TRADER", "trader_investment_plan", current_state, returns_losses, trader_memory
        )

    def reflect_invest_judge(
        self, current_state: Any, returns_losses: float, invest_judge_memory: Any
    ) -> None:
        """Reflect on investment judge's decision and update memory."""
        self._reflect(
            "INVEST JUDGE",
            ("investment_debate_state", "judge_decision"),
            current_state,
            returns_losses,
            invest_judge_memory,
        )

    def reflect_portfolio_manager(
        self, current_state: Any, returns_losses: float, portfolio_manager_memory: Any
    ) -> None:
        """Reflect on portfolio manager's decision and update memory."""
        self._reflect(
            "PORTFOLIO MANAGER",
            ("risk_debate_state", "judge_decision"),
            current_state,
            returns_losses,
            portfolio_manager_memory,
        )
