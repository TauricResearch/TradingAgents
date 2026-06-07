from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.utils.india_market_tools import get_india_corporate_announcements, get_local_filing_notes


def create_india_sentiment_analyst(llm):
    def india_sentiment_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        tools = [get_india_corporate_announcements, get_local_filing_notes]
        system_message = (
            "You are the India Sentiment Analyst. Focus on institutional sentiment from Indian market "
            "news, filings, exchange announcements, credible financial media if configured, and user-provided "
            "notes. Do not hallucinate Twitter, Telegram, WhatsApp, Reddit, or StockTwits sentiment. "
            "Output institutional sentiment, retail/chatter sentiment only if data exists, narrative shifts, "
            "and confidence. Use research-only language and explicitly label unsupported sentiment channels "
            "as unavailable instead of inferring them."
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
        return {"messages": [result], "sentiment_report": report, "india_sentiment_report": report}

    return india_sentiment_node
