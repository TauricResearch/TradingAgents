from collections.abc import Mapping
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_global_news,
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
)
from tradingagents.dataflows import config


def build_news_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the complete news analyst system message without I/O.

    ``get_language_instruction()`` remains available for legacy callers.
    """
    current_date = state["trade_date"]
    asset_label = "company" if state.get("asset_type", "stock") == "stock" else "asset"
    instrument_context = get_instrument_context_from_state(state)
    body = (
        f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(ticker, start_date, end_date) for {asset_label}-specific news by ticker symbol, get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news, get_macro_indicators(indicator, curr_date, look_back_days) to ground macro commentary in actual data from FRED (e.g. 'cpi', 'core_pce', 'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve'), and get_prediction_markets(topic, limit) for live market-implied probabilities of forward-looking events (e.g. 'Fed rate cut', 'recession 2026', geopolitical or sector events). Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
        + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
        + get_language_instruction(output_language)
    )
    return (
        "You are a helpful AI assistant, collaborating with other assistants."
        " Use the provided tools to progress towards answering the question."
        " If you are unable to fully answer, that's OK; another assistant with different tools"
        " will help where you left off. Execute what you can to make progress."
        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
        " You have access to the following tools: get_news, get_global_news, get_macro_indicators, get_prediction_markets."
        f" Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
        + body
    )


def create_news_analyst(llm):
    def news_analyst_node(state):
        tools = [get_news, get_global_news, get_macro_indicators, get_prediction_markets]
        language = config.get_config().get("output_language", "English")
        prompt = ChatPromptTemplate.from_messages(
            [("system", "{system_message}"), MessagesPlaceholder(variable_name="messages")]
        ).partial(system_message=build_news_prompt(state, output_language=language))
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        report = ""
        if len(result.tool_calls) == 0:
            report = result.content
        return {"messages": [result], "news_report": report}

    return news_analyst_node
