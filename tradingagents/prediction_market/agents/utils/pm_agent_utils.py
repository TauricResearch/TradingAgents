from langchain_core.messages import HumanMessage, RemoveMessage

from tradingagents.prediction_market.agents.utils.pm_tools import (
    get_market_info,
    get_market_price_history,
    get_order_book,
    get_resolution_criteria,
    get_event_context,
    get_related_markets,
    search_markets,
)

# Re-export news tools from the existing stock module (news is useful for PM too)
from tradingagents.agents.utils.agent_utils import get_news, get_global_news


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility."""
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": removal_operations + [placeholder]}

    return delete_messages
