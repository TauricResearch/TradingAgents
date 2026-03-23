from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.prediction_market.agents.utils.pm_agent_utils import (
    get_news,
    search_markets,
)


def create_sentiment_analyst(llm):
    def sentiment_analyst_node(state):
        current_date = state["trade_date"]
        market_id = state["market_id"]
        market_question = state["market_question"]

        tools = [
            get_news,
            search_markets,
        ]

        system_message = (
            "You are a Sentiment Analyst for prediction markets. Your task is to analyze public opinion, "
            "social media discussions, and crowd sentiment around the prediction market event. "
            "Use the available tools to search for news sentiment and related market activity. "
            "Your analysis should cover:\n"
            "1. Public opinion and social media sentiment around the event\n"
            "2. Polls, surveys, or expert forecasts related to the predicted outcome\n"
            "3. Expert vs crowd divergence - where do domain experts disagree with market prices?\n"
            "4. Narrative momentum - is sentiment shifting in a particular direction?\n"
            "5. Sentiment extremes that may signal contrarian opportunities\n"
            "6. Related market sentiment and cross-market signals\n"
            "Do not simply state that the sentiment is mixed, provide detailed and finegrained analysis "
            "and insights that may help traders make decisions."
            """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL PREDICTION: **YES/NO** or deliverable,"
                    " prefix your response with FINAL PREDICTION: **YES/NO** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. Market ID: {market_id}. Question: {market_question}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(market_id=market_id)
        prompt = prompt.partial(market_question=market_question)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return sentiment_analyst_node
