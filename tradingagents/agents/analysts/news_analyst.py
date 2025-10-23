from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_news, get_global_news


def create_news_analyst(llm, config):
    """Create the news analyst node with language support."""

    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_news,
            get_global_news,
        ]

        language = config["output_language"]
        language_prompts = {
            "en": "",
            "zh-tw": "Use Traditional Chinese as the output.",
            "zh-cn": "Use Simplified Chinese as the output.",
        }
        language_prompt = language_prompts.get(language, "")

        system_message = (
            f"""
You are a news researcher tasked with analyzing recent news and trends over the past week. 
Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. 
Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. 
Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions.
Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.
"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"""
You are a helpful AI assistant, collaborating with other assistants.
Use the provided tools to progress towards answering the question.
If you are unable to fully answer, that's OK; another assistant with different tools will help where you left off. Execute what you can to make progress.
If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable, prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop.

You have access to the following tools: {tools}.

{system_message}

For your reference, the current date is {current_date}. 
The company we want to look at is {ticker}

Output language: ***{language_prompt}***
""",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

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
