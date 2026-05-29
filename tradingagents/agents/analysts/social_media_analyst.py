from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
    get_options_chain,
)
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_options_chain,
        ]

        system_message = (
            "You are a sentiment analyst focused on short-term market psychology. Use get_news to search for company-specific news and sentiment discussions. "
            "Make two searches: one covering the past 1-3 days, and one covering the past 5-7 days, then compare them to detect direction of change. "
            "Also call get_options_chain once: treat Put/Call volume ratio, near-expiry IV skew, and unusual-activity rows as hard-data sentiment signals — "
            "they reveal positioning by participants who put real money behind their view, which often leads narrative sentiment. "
            "Cross-check the options signal against the news tone: alignment strengthens conviction, divergence is itself an important signal (e.g. positive news + put-heavy options = smart-money skepticism). "
            "Structure your report as five sections: "
            "(1) Current sentiment tone (past 1-3 days): positive, negative, or neutral with supporting evidence; "
            "(2) Sentiment momentum: is sentiment improving or deteriorating compared to last week — direction of change matters more than absolute level; "
            "(3) Notable shifts: any sudden tone changes in the past 24-48 hours and the specific catalysts behind them; "
            "(4) Options-implied positioning: put/call ratios, IV skew direction, and any unusual single-contract activity — translate the raw numbers into 'crowd is leaning long/short/hedging'; "
            "(5) Confluence vs divergence: where do options-implied positioning and news-driven sentiment agree, and where do they conflict — flag the divergences as the highest-information items for downstream decision agents. "
            "Append a Markdown summary table at the end."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Use the provided tools to gather data and write your report."
                    " If you cannot fully answer, that's OK — your report will be used by downstream agents."
                    " Tools: {tool_names}.\n{system_message}"
                    " Current date: {current_date}. Strict-cutoff: use only data and events dated on or before this current date; never use later information. {instrument_context}",
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
