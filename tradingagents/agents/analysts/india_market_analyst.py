from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.utils.india_market_tools import get_india_stock_data, get_india_technical_snapshot


def create_india_market_analyst(llm):
    def india_market_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        tools = [get_india_stock_data, get_india_technical_snapshot]
        system_message = (
            "You are the India Market Technical Analyst for IndiaMarketAgents. "
            "Analyze only Indian listed equities or Indian indices. Cover price trend, volume, "
            "20/50/200 DMA where available, RSI, MACD, Bollinger Bands, ATR, liquidity, "
            "relative performance versus Nifty/Sensex or a verified sector benchmark, and "
            "corporate-action caveats. Do not invent support/resistance, delivery-volume data, "
            "or chart patterns unless a tool result supports the exact dates and prices. "
            "Output a concise thesis, technical table, risk levels, data-quality note, and confidence. "
            "Use research-view language, not live trade execution language."
            + get_language_instruction()
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a serious buy-side India-market research assistant. "
                    "Use the provided tools and report unavailable data explicitly. "
                    "Tools: {tool_names}.\n{system_message}\n"
                    "Current date: {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        result = (prompt | llm.bind_tools(tools)).invoke(state["messages"])
        report = "" if result.tool_calls else result.content
        return {"messages": [result], "market_report": report, "india_market_report": report}

    return india_market_node
