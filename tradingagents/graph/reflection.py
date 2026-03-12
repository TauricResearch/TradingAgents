# TradingAgents/graph/reflection.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from tradingagents.agents.utils.korean_prompt import KOREAN_INVESTOR_GUIDE


class Reflector:
    """Handles reflection on trading decisions and updating memory."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = f"""You are an expert swing trading analyst reviewing past trading decisions.

Analyze the decision and provide:
1. **Reasoning**: Was the decision correct? What factors contributed?
2. **Improvement**: For incorrect decisions, propose specific corrections.
3. **Summary**: Key lessons learned for future swing trades.
4. **Query**: Condensed insights (max 1000 tokens) for memory storage.

Consider: technical indicators, price action, news catalysts, fundamental health, entry/exit timing, position sizing.
{KOREAN_INVESTOR_GUIDE}

[반성 출력 가이드]
- 최종 출력은 한국어로 작성한다.
- 잘한 점/실수/재발 방지 액션 아이템을 명확히 분리해 제시한다.
"""

    def _extract_situation(self, state: Dict[str, Any]) -> str:
        market = state.get("market_report", "")
        news = state.get("news_report", "")
        fundamentals = state.get("fundamentals_report", "")
        return f"{market}\n\n{news}\n\n{fundamentals}"

    def reflect_trader(self, current_state, returns_losses, trader_memory):
        """Reflect on trader's decision and update memory."""
        situation = self._extract_situation(current_state)
        trader_decision = current_state.get("trader_decision", "")

        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\n\nTrading Decision: {trader_decision}\n\nMarket Reports: {situation}",
            ),
        ]

        result = self.quick_thinking_llm.invoke(messages).content
        trader_memory.add_situations([(situation, result)])
