from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_news,
        ]

        system_message = (
            "You are a Social Media Analyst focused on RETAIL SENTIMENT trends for the next 1-2 weeks. "
            "Gauge the crowd's psychological state. Look for Momentum (Hype) or Reversals (Extreme Panic/Euphoria). "
            "Determine if the volume of discussion is rising (indicating incoming volatility)."
            "Use the get_news tool to search for social media discussions and sentiment data."
            + "\n\nDECISION LOGIC:"
            + "\n- LONG: Rising organic hype (Momentum) OR Extreme Panic (Contrarian Buy)."
            + "\n- SHORT: 'Sell the news' sentiment OR Extreme Euphoria (Contrarian Sell)."
            + "\n- HOLD: Neutral sentiment, low social volume, or bots/spam noise."
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
                    "For your reference, the current date is {current_date}. The current company we want to analyze is {ticker}",
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
