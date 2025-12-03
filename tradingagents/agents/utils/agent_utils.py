from langchain_core.messages import HumanMessage, RemoveMessage

# Import all tools from the new registry-based system
from tradingagents.tools.generator import ALL_TOOLS

# Re-export tools for backward compatibility
get_stock_data = ALL_TOOLS["get_stock_data"]
validate_ticker = ALL_TOOLS["validate_ticker"]  # Fixed: was validate_ticker_tool
get_indicators = ALL_TOOLS["get_indicators"]
get_fundamentals = ALL_TOOLS["get_fundamentals"]
get_balance_sheet = ALL_TOOLS["get_balance_sheet"]
get_cashflow = ALL_TOOLS["get_cashflow"]
get_income_statement = ALL_TOOLS["get_income_statement"]
get_recommendation_trends = ALL_TOOLS["get_recommendation_trends"]
get_news = ALL_TOOLS["get_news"]
get_global_news = ALL_TOOLS["get_global_news"]
get_insider_sentiment = ALL_TOOLS["get_insider_sentiment"]
get_insider_transactions = ALL_TOOLS["get_insider_transactions"]

# Legacy alias for backward compatibility
validate_ticker_tool = validate_ticker

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


        