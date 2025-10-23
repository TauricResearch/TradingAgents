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
                You are a senior news and macroeconomic researcher. Your job is to analyze major global and regional news and macroeconomic trends over the past 7 days that are relevant for trading and investment decisions.
                Use the available tools to search for company-specific and global macro news:
                    - get_news(query, start_date, end_date) → targeted or company-level analysis
                    - get_global_news(curr_date, look_back_days, limit) → broad macroeconomic overview
                Your report must be data-driven, concise, and actionable — highlight causal relationships, policy context, and potential market implications.
                Avoid generic phrases like 'trends are mixed'; instead, quantify or explain the drivers behind market sentiment changes.
                Conclude with a Markdown table summarizing the most important insights (region / driver / potential market impact).
            """
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"""
                        You are a helpful AI assistant collaborating with other domain experts.
                        Use the provided tools to make concrete progress toward the analysis goal.
                        If the deliverable includes a final trading stance (BUY/HOLD/SELL), prefix your message clearly with:
                        FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**
                        You have access to the following tools: {tools}.
                        {system_message}
                        Current date: {current_date} | Target company: {ticker}
                        Output language: ***{language_prompt}***
                    """
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
