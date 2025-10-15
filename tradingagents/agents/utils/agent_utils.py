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
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news
)

# Import crypto-specific tools
from tradingagents.agents.utils.crypto_tools import (
    get_onchain_metrics,
    get_exchange_flows,
    get_whale_activity,
    get_crypto_market_data,
    get_crypto_ticker,
    get_crypto_fundamentals,
    get_crypto_news,
    get_order_book_analysis,
    get_tokenomics,
    get_market_overview
)

# XAU-specific tools (Gold)
from tradingagents.dataflows.fred_api import (
    get_dxy_data,
    get_real_yields,
    get_inflation_data,
    get_fred_series,
)
from tradingagents.dataflows.cot_data import (
    get_cot_positioning,
    analyze_cot_extremes,
)
from tradingagents.dataflows.etf_flows import (
    get_gold_etf_summary,
    get_gold_etf_flows,
    analyze_etf_divergence,
)
from tradingagents.dataflows.correlation_tools import (
    calculate_asset_correlation,
    analyze_gold_macro_correlations,
    check_correlation_regime,
    get_rolling_correlations,
)


def create_msg_delete():
    """
    Clear all messages in the provided state and insert a minimal placeholder message for compatibility.
    
    Parameters:
        state (dict): Mutable state containing a "messages" key with an iterable of message objects. Each message object must have an `id` attribute used to build removal operations.
    
    Returns:
        dict: A mapping with the key "messages" whose value is a list consisting of RemoveMessage removal operations for each existing message followed by a single HumanMessage placeholder with content "Continue".
    """
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


        