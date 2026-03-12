from langchain_core.messages import HumanMessage, RemoveMessage, AIMessage, ToolMessage

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

def filter_messages_for_analyst(messages, analyst_tool_names):
    """
    Filter shared state messages to only include conversations relevant to this analyst.

    In parallel analyst execution, all analysts share state["messages"]. When analyst A
    makes tool_use calls, those get merged into shared state. When analyst B runs its
    second iteration, it sees orphaned tool_use blocks from analyst A without matching
    tool_results, causing anthropic.BadRequestError (400).

    This function keeps only:
    - Non-tool messages (HumanMessage etc.)
    - AIMessages whose tool_calls ALL belong to this analyst's tools
    - ToolMessages whose tool_call_id matches this analyst's tool calls
    """
    analyst_tool_call_ids = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] in analyst_tool_names:
                    analyst_tool_call_ids.add(tc["id"])

    result = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            if all(tc["name"] in analyst_tool_names for tc in msg.tool_calls):
                result.append(msg)
            # Skip AI messages containing tool_calls from other parallel analysts
        elif isinstance(msg, ToolMessage):
            if msg.tool_call_id in analyst_tool_call_ids:
                result.append(msg)
        else:
            result.append(msg)

    return result


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