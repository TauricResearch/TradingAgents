from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.prediction_market.agents.utils.pm_agent_utils import (
    get_news,
    get_global_news,
    get_related_markets,
)


def create_information_analyst(llm):
    def information_analyst_node(state):
        current_date = state["trade_date"]
        market_id = state["market_id"]
        market_question = state["market_question"]

        tools = [
            get_news,
            get_global_news,
            get_related_markets,
        ]

        system_message = (
            "You are an Information Analyst for prediction markets. Your task is to find and analyze news, "
            "data, and developments that are relevant to the outcome of the prediction market event. "
            "Use the available tools to search for news and related markets. Your analysis should cover:\n"
            "1. Recent news and developments directly related to the event being predicted\n"
            "2. Broader macro or contextual factors that could influence the outcome\n"
            "3. Information the market may not have priced in yet (information edge)\n"
            "4. Assessment of how new information impacts the probability of each outcome\n"
            "5. Related markets and what their prices signal about this event\n"
            "6. Key upcoming catalysts or data releases that could move the market\n"
            "Do not simply state that the information is mixed, provide detailed and finegrained analysis "
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
            "information_report": report,
        }

    return information_analyst_node
