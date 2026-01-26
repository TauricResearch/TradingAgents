from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_news,
            # get_global_news,
        ]

        system_message = (
            "You are a News Analyst focused on IMMEDIATE market impact (1-2 weeks). "
            "Interpret breaking news and upcoming macro events (CPI, Fed, Geopolitics) to determine short-term direction. "
            "Focus on the 'Narrative' — what story is the market telling itself right now? "
            "Use the available tools: get_news(query, start_date, end_date) for company-specific news. "
            "Filter out noise and old news. Prioritize news that changes the short-term outlook."
            + "\n\nDECISION LOGIC:"
            + "\n- LONG: Distinct positive news cycle, analyst upgrades, or strong macro tailwinds."
            + "\n- SHORT: Distinct negative news cycle, lawsuits, regulatory hits, or macro headwinds."
            + "\n- HOLD: Mixed news, stale news, or high uncertainty waiting for a major event."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + "\n\nYOU MUST CONCLUDE YOUR REPORT WITH: 'SIGNAL: [LONG/SHORT/HOLD]'"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **LONG/HOLD/SHORT** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **LONG/HOLD/SHORT** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. We are looking at the company {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

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
