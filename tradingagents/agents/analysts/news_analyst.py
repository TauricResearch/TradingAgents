"""News Analyst — crypto-focused for the Kalshi pivot.

Uses RSS-aggregated headlines from reputable crypto outlets (CoinDesk,
CoinTelegraph, The Block, Decrypt, Bitcoin Magazine) plus broader
macro coverage. The job is to identify catalysts that could move the
underlying asset over the daily-resolution horizon: Fed/SEC actions,
ETF flow news, exchange announcements, regulatory shifts, hacks, etc.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news, get_global_news]

        system_message = (
            "You are the News Analyst on a Kalshi prediction-market research desk. "
            "Your job is to surface the recent crypto news that could move the "
            "resolution of the contract under analysis. Focus on catalysts likely "
            "to shift price over the next 24 hours: Fed / SEC actions, ETF flow news, "
            "regulatory rulings, exchange announcements, large outages or hacks, "
            "macro releases (CPI, NFP, FOMC), and notable on-chain events. "
            "Use `get_news(query, start_date, end_date)` for asset-specific or topic searches "
            "(e.g. query='bitcoin', 'SEC', 'ETF'); use `get_global_news(curr_date, look_back_days, limit)` "
            "for the broader macro/crypto headline tape. "
            "Provide specific, actionable insights with direct citations of the headlines."
            " Append a Markdown table at the end summarizing the top catalysts and their likely directional impact."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with other analysts on a Kalshi "
                    "prediction-market research desk. Use the provided tools to progress towards "
                    "answering the question. If you or any other assistant has the FINAL TRANSACTION "
                    "PROPOSAL: **YES/NO/PASS** or deliverable, prefix your response with FINAL "
                    "TRANSACTION PROPOSAL: **YES/NO/PASS** so the team knows to stop. "
                    "You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
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
            "news_report": report,
        }

    return news_analyst_node
