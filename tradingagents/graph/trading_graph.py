# -*- coding: utf-8 -*-
# TradingAgentsX/graph/trading_graph.py

import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

# 匯入各種 LLM 的聊天模型
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

# 從 langgraph 匯入 ToolNode，用於將工具轉換為圖中的節點
from langgraph.prebuilt import ToolNode

# 匯入專案內部的代理、設定和狀態管理模組
from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# 從 agent_utils 匯入新的抽象工具方法
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news
)

# 匯入圖的其他組件
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsXGraph:
    """
    協調交易代理框架的主要類別。
    這個類別整合了所有組件，包括 LLM、記憶體、工具和圖的邏輯，
    以執行一個完整的金融分析和交易決策流程。
    """

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
    ):
        """
        初始化交易代理圖和組件。

        Args:
            selected_analysts (list): 要包含的分析師類型列表。
            debug (bool): 是否以除錯模式執行。
            config (Dict[str, Any]): 設定字典。如果為 None，則使用預設設定。
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG

        # 更新介面的設定
        set_config(self.config)

        # 建立必要的目錄
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # 初始化 LLM
        # 初始化 LLM
        provider = self.config["llm_provider"].lower()
        
        # Get base URLs from config, defaulting to backend_url for backward compatibility
        deep_base_url = self.config.get("deep_think_base_url", self.config.get("backend_url"))
        quick_base_url = self.config.get("quick_think_base_url", self.config.get("backend_url"))
        
        # Get API keys from config
        deep_api_key = self.config.get("deep_think_api_key", os.getenv("OPENAI_API_KEY"))
        quick_api_key = self.config.get("quick_think_api_key", os.getenv("OPENAI_API_KEY"))
        
        # Helper to initialize LLM based on model name/provider
        def _create_llm(model: str, base_url: str, api_key: str):
            # Anthropic models require ChatAnthropic (different auth header: x-api-key)
            if model.startswith("claude-"):
                return ChatAnthropic(
                    model=model,
                    anthropic_api_key=api_key,
                    max_tokens=16384,
                )
            # Google Gemini models use ChatGoogleGenerativeAI
            elif model.startswith("gemini-"):
                return ChatGoogleGenerativeAI(
                    model=model,
                    google_api_key=api_key,
                    max_output_tokens=16384,
                )
            # All other providers (OpenAI, Grok, DeepSeek, Qwen, custom) use OpenAI-compatible API
            else:
                return ChatOpenAI(
                    model=model,
                    base_url=base_url,
                    openai_api_key=api_key,
                    max_tokens=16384,
                )

        # Initialize LLMs independently
        print(f"DEBUG: Initializing Deep Thinking LLM: Model={self.config['deep_think_llm']}, BaseURL={deep_base_url}, Key=**********")
        self.deep_thinking_llm = _create_llm(
            self.config["deep_think_llm"],
            deep_base_url,
            deep_api_key
        )
        
        print(f"DEBUG: Initializing Quick Thinking LLM: Model={self.config['quick_think_llm']}, BaseURL={quick_base_url}, Key=**********")
        self.quick_thinking_llm = _create_llm(
            self.config["quick_think_llm"],
            quick_base_url,
            quick_api_key
        )

        # 初始化記憶體
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

        # 建立工具節點
        self.tool_nodes = self._create_tool_nodes()
        
        # Extract language from config (default: zh-TW for backward compatibility)
        self.language = self.config.get("language", "zh-TW")

        # 初始化組件
        self.conditional_logic = ConditionalLogic()
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
            self.language,  # Pass language for agent reports
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # 狀態追蹤
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # 日期到完整狀態字典的映射

        # 設定圖
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """使用抽象方法為不同的資料來源建立工具節點。"""
        return {
            "market": ToolNode(
                [
                    # 核心股票數據工具
                    get_stock_data,
                    # 技術指標
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # 用於社群媒體分析的新聞工具
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # 新聞和內部資訊
                    get_news,
                    get_global_news,
                    get_insider_sentiment,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # 基本面分析工具
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
        }

    def propagate(self, company_name, trade_date):
        """
        在特定日期為某家公司執行交易代理圖。

        Args:
            company_name (str): 公司名稱或股票代碼。
            trade_date (str): 交易日期。

        Returns:
            tuple: 包含最終狀態和處理後信號的元組。
        """
        # 防呆：將股票代碼轉換為大寫並去除空白
        company_name = company_name.strip().upper()
        
        self.ticker = company_name

        # 初始化狀態
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
        )
        args = self.propagator.get_graph_args()

        if self.debug:
            # 帶有追蹤的除錯模式
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            final_state = trace[-1]
        else:
            # 不帶追蹤的標準模式
            final_state = self.graph.invoke(init_agent_state, **args)

        # 儲存當前狀態以供反思
        self.curr_state = final_state

        # 記錄狀態
        self._log_state(trade_date, final_state)

        # 返回決策和處理後的信號
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """將最終狀態記錄到 JSON 檔案中。"""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "risky_history": final_state["risk_debate_state"]["risky_history"],
                "safe_history": final_state["risk_debate_state"]["safe_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # 儲存到檔案
        directory = Path(f"eval_results/{self.ticker}/TradingAgentsXStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.ticker}/TradingAgentsXStrategy_logs/full_states_log_{trade_date}.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """
        根據回報反思決策並更新記憶。
        這個方法會觸發對每個相關代理的決策進行反思的過程。
        """
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal):
        """
        處理信號以提取核心決策。
        將原始的 LLM 輸出轉換為標準化的交易信號（例如，BUY, SELL, HOLD）。
        """
        return self.signal_processor.process_signal(full_signal)