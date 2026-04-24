# TradingAgents/graph/reflection.py

from typing import Any, Dict


class Reflector:
    """Handles reflection on decisions and updating memory."""

    def __init__(self, quick_thinking_llm: Any):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()

    def _get_reflection_prompt(self) -> str:
        """Get the system prompt for reflection."""
        return """
你是一位专业的金融分析师，负责审查交易决策/分析并提供全面、逐步的分析。你的目标是提供对投资决策的详细洞察并突出改进机会，严格遵循以下指南：

1. 推理：
   - 对于每个交易决策，判断它是否正确。正确的决策会导致回报增加，而错误的决策则相反。
   - 分析每个成功或错误的影响因素。考虑：
     - 市场情报
     - 技术指标
     - 技术信号
     - 价格走势分析
     - 整体市场数据分析
     - 新闻分析
     - 社交媒体和情绪分析
     - 基本面分析
     - 权衡每个因素在决策过程中的重要性

2. 改进：
   - 对于任何错误的决策，提出最大化回报的修改建议。
   - 提供纠正行动或改进的详细列表，包括具体建议（例如，在特定日期将决策从持有改为买入）。

3. 总结：
   - 总结从成功和错误中学到的教训。
   - 突出如何将这些教训适应于未来的交易场景，并建立类似情况之间的联系以应用所学知识。

4. 查询：
   - 将总结中的关键洞察提炼成不超过1000个字符的简明句子。
   - 确保提炼的句子捕捉到教训和推理的本质，便于参考。

严格遵循这些指示，确保你的输出详细、准确且可操作。你还将获得从价格走势、技术指标、新闻和情绪角度提供的市场客观描述，以提供更多分析背景。
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

    def reflect_portfolio_manager(self, current_state, returns_losses, portfolio_manager_memory):
        """Reflect on portfolio manager's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["risk_debate_state"]["judge_decision"]

        result = self._reflect_on_component(
            "PORTFOLIO MANAGER", judge_decision, situation, returns_losses
        )
        portfolio_manager_memory.add_situations([(situation, result)])
