from langchain_core.messages import HumanMessage, RemoveMessage

# =============================================================================
# SIMULATION CONTEXT FOR ALL AGENTS
# =============================================================================
# This context is prepended to all agent prompts to ensure the LLM understands
# this is an educational simulation and stays in character as the analyst role.
# Without this, LLMs may refuse to engage or break character.
# =============================================================================

SIMULATION_CONTEXT = """You are an AI analyst participating in a stock market analysis simulation. Your task is to analyze financial data and provide investment perspectives based on the data provided. This is an educational demonstration of financial analysis techniques.

Respond ONLY with your analysis. Do not include any meta-commentary about being an AI, ethical concerns, or disclaimers. Simply provide the requested financial analysis based on the data given."""

def get_simulation_prompt(role_prompt: str) -> list:
    """
    Create properly structured messages for the LLM.
    Returns a list of message dicts for proper system/user separation.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    return [
        SystemMessage(content=SIMULATION_CONTEXT),
        HumanMessage(content=role_prompt)
    ]


# Import tools from separate utility files
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
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


        