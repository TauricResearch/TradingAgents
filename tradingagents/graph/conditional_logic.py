# -*- coding: utf-8 -*-
# TradingAgentsX/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """
    處理用於確定圖流程的條件邏輯。
    這個類別定義了在圖中不同節點之間轉換的規則，
    例如，決定下一個應該執行的代理或是否繼續一個循環。
    """

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """
        使用設定參數進行初始化。

        Args:
            max_debate_rounds (int): 投資辯論的最大回合數。
            max_risk_discuss_rounds (int): 風險討論的最大回合數。
        """
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        """
        判斷市場分析是否應該繼續。
        如果最後一條訊息包含工具呼叫，則表示代理需要使用工具，
        流程應該轉到市場工具節點。否則，分析完成。

        Args:
            state (AgentState): 當前的代理狀態。

        Returns:
            str: 下一個節點的名稱。
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """
        判斷社群媒體分析是否應該繼續。
        邏輯與 `should_continue_market` 類似。

        Args:
            state (AgentState): 當前的代理狀態。

        Returns:
            str: 下一個節點的名稱。
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """
        判斷新聞分析是否應該繼續。
        邏輯與 `should_continue_market` 類似。

        Args:
            state (AgentState): 當前的代理狀態。

        Returns:
            str: 下一個節點的名稱。
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """
        判斷基本面分析是否應該繼續。
        邏輯與 `should_continue_market` 類似。

        Args:
            state (AgentState): 當前的代理狀態。

        Returns:
            str: 下一個節點的名稱。
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(self, state: AgentState) -> str:
        """
        判斷投資辯論是否應該繼續。
        如果辯論回合數達到上限，則由研究經理做出最終決定。
        否則，在看漲和看跌研究員之間輪流進行。

        Args:
            state (AgentState): 當前的代理狀態。

        Returns:
            str: 下一個節點的名稱。
        """
        # 2 個代理之間的來回辯論
        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):
            return "Research Manager"
        # 檢查中文或英文前綴（根據報告語言）
        current_response = state["investment_debate_state"]["current_response"]
        # Chinese: "看漲" (Bullish), English: "Bull" or "Bullish"
        if current_response.startswith("看漲") or current_response.lower().startswith("bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """
        判斷風險分析是否應該繼續。
        如果討論回合數達到上限，則由風險裁判做出最終決定。
        否則，在激進、保守和中立分析師之間輪流進行。

        Args:
            state (AgentState): 當前的代理狀態。

        Returns:
            str: 下一個節點的名稱。
        """
        # 3 個代理之間的來回討論
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):
            return "Risk Judge"
        if state["risk_debate_state"]["latest_speaker"].startswith("Risky"):
            return "Safe Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Safe"):
            return "Neutral Analyst"
        return "Risky Analyst"