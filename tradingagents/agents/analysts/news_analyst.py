from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.news_data_tools import get_global_news, get_news
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        # ── Pre-fetch company-specific and global news in parallel ────────────
        trade_date = datetime.strptime(current_date, "%Y-%m-%d")
        start_date = (trade_date - timedelta(days=7)).strftime("%Y-%m-%d")

        prefetched = prefetch_tools_parallel(
            [
                {
                    "tool": get_news,
                    "args": {
                        "ticker": ticker,
                        "start_date": start_date,
                        "end_date": current_date,
                    },
                    "label": "Company-Specific News (Last 7 Days)",
                },
                {
                    "tool": get_global_news,
                    "args": {
                        "curr_date": current_date,
                        "look_back_days": 7,
                        "limit": 5,
                    },
                    "label": "Global Macroeconomic News (Last 7 Days)",
                },
            ]
        )
        prefetched_context = format_prefetched_context(prefetched)

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over "
            "the past week.\n\n"
            "## Pre-loaded Data\n\n"
            "Both company-specific news and global macroeconomic news for the past 7 days "
            "have already been fetched and are provided in the **Pre-loaded Context** section "
            "below. Do NOT call `get_news` or `get_global_news` — the data is already available.\n\n"
            "## Your Task\n\n"
            "Synthesize the pre-loaded news feeds into a comprehensive report covering the "
            "current state of the world as it is relevant to trading and macroeconomics. "
            "Cross-reference company-specific developments with the broader macro backdrop. "
            "Provide specific, actionable insights with supporting evidence to help traders "
            "make informed decisions. "
            "Make sure to append a Markdown table at the end of the report to organise key "
            "points, making it easy to read."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        # No tools remain — use direct invocation (no bind_tools, no tool loop)
        chain = prompt | llm

        result = chain.invoke(state["messages"])

        report = result.content or ""

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
