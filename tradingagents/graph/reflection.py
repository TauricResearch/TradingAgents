# TradingAgents/graph/reflection.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
import json
import re


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

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        """Extract the current market situation from the state."""
        curr_market_report = current_state["market_report"]
        curr_sentiment_report = current_state["sentiment_report"]
        curr_news_report = current_state["news_report"]
        curr_fundamentals_report = current_state["fundamentals_report"]

        return f"{curr_market_report}\n\n{curr_sentiment_report}\n\n{curr_news_report}\n\n{curr_fundamentals_report}"

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

    @staticmethod
    def generate_final_report(final_state: dict) -> str:
        """
        Generate a final, comprehensive report from the final state, ensuring
        all parts are combined into a single, valid JSON object.
        """
        final_report_json = {
            "company_info": {
                "ticker": final_state.get('company_of_interest', 'N/A'),
                "analysis_date": final_state.get('trade_date', 'N/A')
            },
            "reports": {},
            "final_decision": {}
        }

        def extract_json(text: str) -> dict:
            """Extracts a JSON object from a string, even if it's embedded in other text."""
            if not isinstance(text, str):
                return {} # Return empty dict if not a string
            
            # Find the start and end of the JSON object
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return {"error": "Failed to decode JSON", "original_text": json_str}
            return {"error": "No JSON object found", "original_text": text}

        # Process each report
        report_keys = ['market_report', 'sentiment_report', 'news_report', 'fundamentals_report']
        for key in report_keys:
            if final_state.get(key):
                report_name = key.replace('_report', '')
                final_report_json['reports'][report_name] = extract_json(final_state[key])

        # Add investment debate summary
        if final_state.get('investment_debate_state'):
            final_report_json['reports']['investment_debate'] = {
                "summary": final_state['investment_debate_state'].get('judge_decision', 'N/A')
            }

        # Add final plan and decision
        if final_state.get('investment_plan'):
            final_report_json['final_decision']['investment_plan'] = final_state['investment_plan']
        
        if final_state.get('final_trade_decision'):
            # Extract the final proposal (BUY/HOLD/SELL)
            proposal_match = re.search(r'FINAL TRANSACTION PROPOSAL:\s*\*{2}(.*?)\*{2}', final_state['final_trade_decision'])
            proposal = proposal_match.group(1) if proposal_match else 'N/A'
            final_report_json['final_decision']['final_proposal'] = proposal
            final_report_json['final_decision']['full_text'] = final_state['final_trade_decision']

        return json.dumps(final_report_json, ensure_ascii=False, indent=4)
