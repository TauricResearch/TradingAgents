from langchain_core.messages import HumanMessage, RemoveMessage

# 從獨立的工具程式檔案匯入工具
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news
)

def create_msg_delete():
    """
    建立一個刪除訊息的函式。

    Returns:
        一個在 langgraph 中用於清除訊息的函式。
    """
    def delete_messages(state):
        """清除訊息並為 Anthropic 相容性新增佔位符"""
        messages = state["messages"]
        
        # 移除所有訊息
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # 新增一個最小的佔位符訊息
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages