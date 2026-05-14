from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    ANALYST_PREAMBLE,
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_range_stats,
    get_stock_data,
)
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_range_stats,
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            """You are a trading assistant. Select up to **8 complementary indicators** (no redundancy) from this menu and analyze the stock.

Available indicators (use exact names — wrong names will fail):
- Trend: close_50_sma, close_200_sma, close_10_ema
- MACD: macd, macds (signal), macdh (histogram)
- Momentum: rsi
- Volatility: boll (middle/20-SMA), boll_ub (upper), boll_lb (lower), atr
- Volume: vwma

Workflow:
1. Call `get_range_stats` first — anchors today's price/volume against 52w/6m/3m/1m ranges (e.g. 52-week high, near 1-month low). Weave this into the trend narrative.
2. Call `get_stock_data` for the CSV.
3. Call `get_indicators` with your chosen indicator names.

Briefly justify why each chosen indicator fits the current market context. Write a detailed, nuanced report with actionable insights, and end with a Markdown summary table."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANALYST_PREAMBLE),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
