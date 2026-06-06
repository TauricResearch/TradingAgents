from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_global_news,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.tool_fallback import bind_tools_or_none, safe_tool_text


# Company-news window pre-fetched for the tool-free path, in calendar days
# back from the trade date. Global/macro news uses the configured default
# window (global_news_lookback_days) via the tool's own defaults.
_NEWS_LOOKBACK_DAYS = 7


def _prefetch_news_data(ticker: str, current_date: str) -> str:
    """Gather the news the tools would return, for tool-less providers."""
    start_date = (
        datetime.strptime(current_date, "%Y-%m-%d") - timedelta(days=_NEWS_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d")

    company_news = safe_tool_text(
        "company-specific news",
        lambda: get_news.func(ticker, start_date, current_date),
    )
    global_news = safe_tool_text(
        "global / macroeconomic news",
        lambda: get_global_news.func(current_date),
    )

    return (
        f"### Company-specific news ({start_date} → {current_date})\n"
        f"{company_news}\n\n"
        "### Global / macroeconomic news\n"
        f"{global_news}"
    )


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = str(state["company_of_interest"])
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        bound_llm = bind_tools_or_none(llm, tools, "News Analyst")

        if bound_llm is not None:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " Use the provided tools to progress towards answering the question."
                        " If you are unable to fully answer, that's OK; another assistant with different tools"
                        " will help where you left off. Execute what you can to make progress."
                        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                        " You have access to the following tools: {tool_names}.\n{system_message}"
                        "For your reference, the current date is {current_date}. {instrument_context}",
                    ),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            prompt = prompt.partial(system_message=system_message)
            prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
            prompt = prompt.partial(current_date=current_date)
            prompt = prompt.partial(instrument_context=instrument_context)

            chain = prompt | bound_llm
            result = chain.invoke(state["messages"])

            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

            return {
                "messages": [result],
                "news_report": report,
            }

        # Tool-free fallback: pre-fetch the news and inject it into the prompt
        # for providers (e.g. codex) that cannot bind LangChain tools.
        news_data = _prefetch_news_data(ticker, current_date)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " The news you need has ALREADY been gathered for you and is included below;"
                    " do NOT call any tools and disregard any instruction below to call a tool —"
                    " base your report only on the provided news."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "=== Pre-fetched news ===\n{news_data}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(news_data=news_data)

        formatted_messages = prompt.format_messages(messages=state["messages"])
        result = llm.invoke(formatted_messages)

        return {
            "messages": [result],
            "news_report": result.content,
        }

    return news_analyst_node
