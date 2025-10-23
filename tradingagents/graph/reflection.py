# TradingAgents/graph/reflection.py

from typing import Dict, Any

from langchain_core.language_models.chat_models import BaseChatModel


class Reflector:
    """Handles reflection on decisions and updating memory."""

    def __init__(self, quick_thinking_llm: BaseChatModel, config):
        """Initialize the reflector with an LLM."""
        language = config["output_language"]
        language_prompts = {
            "en": "",
            "zh-tw": "Use Traditional Chinese as the output.",
            "zh-cn": "Use Simplified Chinese as the output.",
        }
        self.language_prompt = language_prompts.get(language, "")

        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()

    def _get_reflection_prompt(self) -> str:
        """Get the system prompt for reflection."""
        return f"""
                You are an expert financial analyst tasked with reviewing trading decisions and providing a comprehensive, step‑by‑step analysis. 
                Deliver detailed insights and actionable improvements under the following rules.
                
                Reasoning:
                    - Outcome definition: For each decision, judge correctness against its intended holding horizon and benchmark. A decision is “correct” if it achieves positive excess return versus the stated benchmark over the decision’s horizon, or meets predefined risk‑adjusted targets (e.g., positive Sharpe/Sortino relative to the plan). If horizon/benchmark is missing, infer a reasonable one from context and state the assumption.
                    - Signal vs. judgment vs. action: Separate data signals (price/volume, indicators, news/sentiment, fundamentals), the interpretation/assumptions made, and the executed trade rules (timing, sizing, risk controls). Identify which layer succeeded or failed.
                    - Factor evaluation: For each contributing factor, specify direction, evidence level (primary/secondary/inferred), recency, and weight of influence (low/medium/high). Consider:
                        - Market intelligence and regime context.
                        - Technical indicators and signals.
                        - Price action and path dependency.
                        - News flow and event risk.
                        - Social media and sentiment.
                        - Fundamental metrics and valuation.
                        - Liquidity/volatility conditions impacting execution quality.
                
                Improvement:
                    - For incorrect or suboptimal decisions, propose revisions tied to observable conditions:
                        - Entry/exit rule adjustments with explicit triggers and invalidations.
                        - Timing refinements (avoid chop, wait for confirmation).
                        - Sizing/risk limits aligned to volatility or conviction.
                        - Data/confirmation requirements (e.g., two‑source validation of key KPIs).
                    - Make at least one concrete, testable recommendation per error (e.g., “Change HOLD to BUY when [condition] occurs; if not observed by [date/event], maintain HOLD”).
                    
                Summary:
                    - Distill lessons into reusable rules: what to repeat, what to avoid, what to monitor. Map each rule to the error layer it fixes (signal, judgment, or action) and the metric that will verify adherence next time.
                    
                Query:
                    - Produce one concise sentence (≤1000 tokens) that captures the core lessons and decision rules, including at least one observable trigger and one invalidation condition.
                    
                Quality and constraints:
                    - Be specific, evidence‑based, and time‑aware. Explicitly state assumptions, horizons, and benchmarks used for evaluation.
                    - If inputs are missing or contradictory, flag limitations, state the minimal viable assumption, and proceed with a conservative evaluation.
                    - Avoid generic statements such as “trends are mixed”; tie claims to concrete signals, data points, or catalysts.
                    - The analysis should be detailed, accurate, and directly actionable. You will also be provided objective descriptions of price movements, technical indicators, news, and sentiment to ground your evaluation.
                
                Output language: ***{self.language_prompt}***
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
