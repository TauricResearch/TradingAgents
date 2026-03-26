from langchain_core.messages import HumanMessage, RemoveMessage

from tradingagents.dataflows.config import get_config

# Providers whose APIs do not support tool/function calling.
_NO_TOOL_CALLING_PROVIDERS = frozenset({"perplexity"})


def supports_tool_calling() -> bool:
    """Check if the current LLM provider supports tool calling."""
    config = get_config()
    return config.get("llm_provider", "openai").lower() not in _NO_TOOL_CALLING_PROVIDERS


def prefetch_tool_data(tools, tool_args_list) -> str:
    """Pre-call tools and return formatted results for prompt injection.

    Used as a fallback for providers that don't support tool calling.
    """
    results = []
    for tool, args in zip(tools, tool_args_list):
        try:
            data = tool.invoke(args)
            results.append(f"=== {tool.name} ===\n{data}")
        except Exception as e:
            results.append(f"=== {tool.name} ===\n[Error fetching data: {e}]")
    return "\n\n".join(results)


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


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
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


        
