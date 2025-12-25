from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_crypto_tools import (
    get_crypto_data
)
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data,
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators,
    get_indicators_bulk
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_whitepaper,
    get_market_cap
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news
)
from tradingagents.agents.utils.sentiment_tools import (
    get_fear_and_greed,
)

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


        