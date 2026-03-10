from langchain_core.messages import HumanMessage, RemoveMessage

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
    get_insider_transactions,
    get_global_news
)

def get_language_instruction() -> str:
    """Return a language instruction string based on the configured output_language.
    Returns an empty string for English (default), or a Chinese instruction string."""
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "en")
    if lang == "zh":
        return "\n\nIMPORTANT: You must respond entirely in Simplified Chinese (简体中文). All analysis, reports, recommendations, and outputs must be written in Chinese."
    return ""


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


        