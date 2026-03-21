# TradingAgents/graph/reflection.py

from typing import Dict, Any
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
You are an expert prediction market analyst tasked with reviewing trading decisions/analysis and providing a comprehensive, step-by-step analysis.
Your goal is to deliver detailed insights into prediction market decisions and highlight opportunities for improvement, adhering strictly to the following guidelines:

1. Reasoning:
   - For each prediction decision, determine whether it was correct or incorrect. A correct decision results in a positive return, while an incorrect decision does the opposite.
   - Analyze the contributing factors to each success or mistake. Consider:
     - Market odds and price movements.
     - Order book depth and whale activity.
     - News and event analysis.
     - Social media and sentiment analysis.
     - Timing and event resolution timeline.
     - Weight the importance of each factor in the decision-making process.

2. Improvement:
   - For any incorrect decisions, propose revisions to maximize returns.
   - Provide a detailed list of corrective actions or improvements, including specific recommendations (e.g., changing a decision from SKIP to YES on a particular event).

3. Summary:
   - Summarize the lessons learned from the successes and mistakes.
   - Highlight how these lessons can be adapted for future prediction market scenarios and draw connections between similar situations to apply the knowledge gained.

4. Query:
   - Extract key insights from the summary into a concise sentence of no more than 1000 tokens.
   - Ensure the condensed sentence captures the essence of the lessons and reasoning for easy reference.

Adhere strictly to these instructions, and ensure your output is detailed, accurate, and actionable. You will also be given objective descriptions of the market from an odds, news, and sentiment perspective to provide more context for your analysis.
"""

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        """Extract the current market situation from the state."""
        curr_odds_report = current_state["odds_report"]
        curr_sentiment_report = current_state["sentiment_report"]
        curr_news_report = current_state["news_report"]
        curr_event_report = current_state["event_report"]

        return f"{curr_odds_report}\n\n{curr_sentiment_report}\n\n{curr_news_report}\n\n{curr_event_report}"

    def _reflect_on_component(
        self, component_type: str, report: str, situation: str, returns_losses
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

    def reflect_yes_advocate(self, current_state, returns_losses, yes_memory):
        """Reflect on YES advocate's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        yes_debate_history = current_state["investment_debate_state"]["yes_history"]

        result = self._reflect_on_component(
            "YES", yes_debate_history, situation, returns_losses
        )
        yes_memory.add_situations([(situation, result)])

    def reflect_no_advocate(self, current_state, returns_losses, no_memory):
        """Reflect on NO advocate's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        no_debate_history = current_state["investment_debate_state"]["no_history"]

        result = self._reflect_on_component(
            "NO", no_debate_history, situation, returns_losses
        )
        no_memory.add_situations([(situation, result)])

    def reflect_timing_advocate(self, current_state, returns_losses, timing_memory):
        """Reflect on timing advocate's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        timing_debate_history = current_state["investment_debate_state"]["timing_history"]

        result = self._reflect_on_component(
            "TIMING", timing_debate_history, situation, returns_losses
        )
        timing_memory.add_situations([(situation, result)])

    def reflect_trader(self, current_state, returns_losses, trader_memory):
        """Reflect on trader's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state["trader_plan"]

        result = self._reflect_on_component(
            "TRADER", trader_decision, situation, returns_losses
        )
        trader_memory.add_situations([(situation, result)])

    def reflect_invest_judge(self, current_state, returns_losses, invest_judge_memory):
        """Reflect on investment judge's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["investment_debate_state"]["judge_decision"]

        result = self._reflect_on_component(
            "INVEST JUDGE", judge_decision, situation, returns_losses
        )
        invest_judge_memory.add_situations([(situation, result)])

    def reflect_risk_manager(self, current_state, returns_losses, risk_manager_memory):
        """Reflect on risk manager's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["risk_debate_state"]["judge_decision"]

        result = self._reflect_on_component(
            "RISK JUDGE", judge_decision, situation, returns_losses
        )
        risk_manager_memory.add_situations([(situation, result)])
