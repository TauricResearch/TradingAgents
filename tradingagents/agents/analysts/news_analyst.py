from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
    supports_tool_calls,
)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        if supports_tool_calls(llm):
            return _tool_call_path(llm, state, current_date, ticker, instrument_context)
        return _prefetch_path(llm, state, current_date, ticker, instrument_context)

    return news_analyst_node


# ── Tool-call path (API providers) ────────────────────────────────────────

def _tool_call_path(llm, state, current_date, ticker, instrument_context):
    """Original flow: bind_tools → LLM selects and calls tools."""
    tools = [get_news, get_global_news]

    system_message = (
        "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
        + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
        + get_language_instruction()
    )

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

    chain = prompt | llm.bind_tools(tools)
    result = chain.invoke(state["messages"])

    report = ""
    if len(result.tool_calls) == 0:
        report = result.content

    return {
        "messages": [result],
        "news_report": report,
    }


# ── Pre-fetch path (CLI provider) ────────────────────────────────────────

def _prefetch_path(llm, state, current_date, ticker, instrument_context):
    """Pre-fetch news data and inject into prompt (no tool-calling needed)."""
    start_date = _seven_days_back(current_date)

    # Fetch ticker-specific news
    try:
        ticker_news = get_news.func(ticker, start_date, current_date)
    except Exception as e:
        ticker_news = f"<unavailable: {e}>"

    # Fetch global macro news
    try:
        global_news = get_global_news.func(current_date, None, None)
    except Exception as e:
        global_news = f"<unavailable: {e}>"

    system_message = _build_prefetch_system_message(
        ticker=ticker,
        start_date=start_date,
        end_date=current_date,
        ticker_news=ticker_news,
        global_news=global_news,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                "\n{system_message}\n"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(current_date=current_date)
    prompt = prompt.partial(instrument_context=instrument_context)

    chain = prompt | llm
    result = chain.invoke(state["messages"])

    return {
        "messages": [result],
        "news_report": result.content,
    }


# ── System message for pre-fetch path ────────────────────────────────────

def _build_prefetch_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    ticker_news: str,
    global_news: str,
) -> str:
    """Assemble the news analyst system message with pre-fetched data."""
    return f"""You are a news researcher tasked with analyzing recent news and trends over the past week for {ticker}, covering {start_date} to {end_date}. All news data has been pre-fetched and is included below.

## Data sources (pre-fetched, in this prompt)

### Ticker-specific news — {ticker}
Company-specific news, earnings, product announcements, analyst ratings.

<start_of_ticker_news>
{ticker_news}
<end_of_ticker_news>

### Global / macroeconomic news
Broader market, Fed policy, GDP, geopolitical, sector-wide trends.

<start_of_global_news>
{global_news}
<end_of_global_news>

## Instructions

1. Analyze the ticker-specific news for material events, catalysts, and sentiment shifts.
2. Analyze the global news for macroeconomic factors that impact {ticker} and its sector.
3. Identify connections between ticker-specific and macro news (e.g., sector rotation, policy impact).
4. Write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics.
5. Provide specific, actionable insights with supporting evidence to help traders make informed decisions.
6. Append a Markdown table at the end summarizing key points, organized and easy to read.

{get_language_instruction()}"""
