from langchain_core.messages import HumanMessage, RemoveMessage
from tradingagents.agents.utils.agent_states import AgentState

from tradingagents.agents.utils.polymarket_tools import (
    get_market_data,
    get_price_history,
    get_event_news,
    get_global_news,
    get_whale_activity,
    get_event_details,
    get_orderbook,
    get_market_stats,
    get_leaderboard_signals,
    get_social_sentiment,
    search_markets,
)


def create_msg_delete():
    """Create a message deletion node."""
    def msg_delete(state: AgentState):
        return {"messages": [RemoveMessage(id=m.id) for m in state["messages"]]}
    return msg_delete
