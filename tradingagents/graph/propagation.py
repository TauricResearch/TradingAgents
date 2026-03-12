# -*- coding: utf-8 -*-
# TradingAgentsX/graph/propagation.py

from typing import Dict, Any
import json
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.interface import route_to_vendor



class Propagator:
    """
    處理狀態在圖中的初始化和傳播。
    這個類別負責建立圖執行的初始狀態，並提供圖呼叫所需的參數。
    """

    def __init__(self, max_recur_limit=200):
        """
        使用設定參數進行初始化。

        Args:
            max_recur_limit (int): 圖的最大遞迴深度限制，以防止無限循環。
        """
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, company_name: str, trade_date: str
    ) -> Dict[str, Any]:
        """
        為代理圖建立初始狀態。
        這個狀態字典包含了執行開始時所需的所有資訊。

        Args:
            company_name (str): 感興趣的公司名稱或股票代碼。
            trade_date (str): 交易日期。

        Returns:
            Dict[str, Any]: 初始狀態的字典。
        """
        # 防呆：將股票代碼轉換為大寫並去除空白
        company_name = company_name.strip().upper()
        
        # 獲取真實公司名稱（從Alpha Vantage獲取公司概況）
        ticker = company_name  # company_name實際上是ticker
        actual_company_name = ticker  # 預設值為ticker
        
        try:
            # 嘗試從fundamentals數據中獲取公司全名
            fundamentals_data = route_to_vendor("get_fundamentals", ticker, trade_date)
            if fundamentals_data:
                # 解析JSON數據
                data = json.loads(fundamentals_data) if isinstance(fundamentals_data, str) else fundamentals_data
                if isinstance(data, dict) and "Name" in data:
                    actual_company_name = data["Name"]
                    print(f"成功獲取公司名稱：{ticker} -> {actual_company_name}")
                else:
                    print(f"警告：無法從fundamentals數據中提取公司名稱，使用ticker: {ticker}")
        except Exception as e:
            print(f"警告：獲取公司名稱時發生錯誤：{e}，使用ticker: {ticker}")
        
        return {
            "messages": [("human", ticker)],  # 初始訊息，觸發第一個代理
            "company_of_interest": ticker,  # 股票代碼
            "company_name": actual_company_name,  # 真實公司全名
            "trade_date": str(trade_date),  # 交易日期
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),  # 投資辯論的初始狀態
            "risk_debate_state": RiskDebateState(
                {
                    "risky_history": "",
                    "safe_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_risky_response": "",
                    "current_safe_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),  # 風險辯論的初始狀態
            "market_report": "",  # 市場報告的初始值
            "fundamentals_report": "",  # 基本面報告的初始值
            "sentiment_report": "",  # 情緒報告的初始值
            "news_report": "",  # 新聞報告的初始值
        }


    def get_graph_args(self) -> Dict[str, Any]:
        """
        獲取圖呼叫的參數。
        這些參數控制著圖的執行方式，例如串流模式和遞迴限制。

        Returns:
            Dict[str, Any]: 用於圖呼叫的參數字典。
        """
        return {
            "stream_mode": "values",  # 設定串流模式為 "values"，以獲取每個節點的輸出
            "config": {"recursion_limit": self.max_recur_limit},  # 設定遞迴限制
        }