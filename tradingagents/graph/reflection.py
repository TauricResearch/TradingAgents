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
You are an expert financial analyst tasked with reviewing trading decisions/analysis.
Your goal is to deliver detailed insights AND **tunable parameter updates**.

1. Reasoning:
   - Determine if the decision was correct based on the OUTCOME (Returns).
   - Analyze which factor (News, Technicals, Fundamentals) was the primary driver.

2. Improvement:
   - For incorrect decisions, propose revisions.

3. Summary:
   - Summarize lessons learned.

4. PARAMETER OPTIMIZATION (CRITICAL):
   - You have control over specific system parameters.
   - If the strategy failed due to being too slow/fast, adjust them.
   - **YOU MUST OUTPUT A JSON BLOCK** at the end of your response if changes are needed.
   - Available Parameters:
     - `rsi_period` (Default 14): Lower to 7 for faster reaction, raise to 21 for noise filtering.
     - `risk_multiplier_cap` (Default 1.5): Lower if drawdowns are too high.
     - `stop_loss_pct` (Default 0.10): Tighten (e.g., 0.05) if getting stopped out too late.
   
   - FORMAT:
     ```json
     {
       "UPDATE_PARAMETERS": {
         "rsi_period": 7,
         "stop_loss_pct": 0.08
       }
     }
     ```
   - If no changes are needed, do not output the JSON block.

Adhere strictly to these instructions.
"""

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        """
        Extract the current market situation from the state.
        CRITICAL FIX: Now includes Regime Context so the Reflector knows WHY rules were applied.
        """
        # Standard Reports
        curr_market_report = current_state.get("market_report", "No Market Report")
        curr_sentiment_report = current_state.get("sentiment_report", "No Sentiment Report")
        curr_news_report = current_state.get("news_report", "No News Report")
        curr_fundamentals_report = current_state.get("fundamentals_report", "No Fundamental Report")

        # 🛑 CRITICAL CONTEXT: The Regime Data
        market_regime = current_state.get("market_regime", "UNKNOWN")
        broad_regime = current_state.get("broad_market_regime", "UNKNOWN")
        volatility = current_state.get("volatility_score", "N/A")

        # Format the Situation String
        situation_str = (
            f"=== MARKET REGIME CONTEXT ===\n"
            f"Target Asset Regime: {market_regime}\n"
            f"Broad Market (SPY) Regime: {broad_regime}\n"
            f"Volatility Score: {volatility}\n\n"
            f"=== ANALYST REPORTS ===\n"
            f"TECHNICAL: {curr_market_report}\n\n"
            f"SENTIMENT: {curr_sentiment_report}\n\n"
            f"NEWS: {curr_news_report}\n\n"
            f"FUNDAMENTALS: {curr_fundamentals_report}"
        )

        return situation_str

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

    def reflect_bull_researcher(self, current_state, returns_losses, bull_memory):
        """Reflect on bull researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bull_debate_history = current_state["investment_debate_state"]["bull_history"]

        result = self._reflect_on_component(
            "BULL", bull_debate_history, situation, returns_losses
        )
        bull_memory.add_situations([(situation, result)])

    def reflect_bear_researcher(self, current_state, returns_losses, bear_memory):
        """Reflect on bear researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bear_debate_history = current_state["investment_debate_state"]["bear_history"]

        result = self._reflect_on_component(
            "BEAR", bear_debate_history, situation, returns_losses
        )
        bear_memory.add_situations([(situation, result)])

    def reflect_trader(self, current_state, returns_losses, trader_memory):
        """Reflect on trader's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state["trader_investment_plan"]

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
