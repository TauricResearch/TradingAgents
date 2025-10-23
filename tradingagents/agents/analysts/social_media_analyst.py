from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_news


def create_social_media_analyst(llm, config):
    """Create the social media analyst node with language support."""

    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_news,
        ]

        language = config["output_language"]
        language_prompts = {
            "en": "",
            "zh-tw": "Use Traditional Chinese as the output.",
            "zh-cn": "Use Simplified Chinese as the output.",
        }
        language_prompt = language_prompts.get(language, "")

        system_message = (
            """
                You are a social media and company-specific news analyst. Your goal is to evaluate the company's public sentiment and perception over the past 7 days.
                Analyze trending social media posts, sentiment dynamics, and relevant company news to identify shifts in market sentiment, brand reputation, and potential investor implications.
                Use the tool get_news(query, start_date, end_date) to gather company-specific social media and news data. Extract qualitative and quantitative trends across sources.
                Your analysis should explain *why* sentiment changes, *who* is influencing discourse (e.g., media, influencers, customers), and *how* it may impact investor behavior.
                Avoid vague summaries such as 'public opinion is mixed'; support claims with examples, sentiment ratios, or trend direction.
                End with a structured Markdown table summarizing key daily sentiment, major social trends, and investment-relevant insights.
                Use objective, professional, and journalistic tone, but focus on financial implications.
                Cite quantitative data where possible, and avoid overly general statements.
                
                Use the available tools to search for company-specific and global macro news:
                    - get_news(query, start_date, end_date) → targeted or company-level analysis
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
