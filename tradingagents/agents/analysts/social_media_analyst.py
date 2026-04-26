from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.sentiment_tools import get_reddit_sentiment, get_market_fear_greed
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_reddit_sentiment,
            get_market_fear_greed,
        ]

        system_message = (
            "You are a Sentiment Analyst. Your job is to gauge retail investor sentiment "
            "and macro market mood for a specific stock.\n\n"
            "Use get_reddit_sentiment(ticker, days) to fetch recent Reddit posts from "
            "r/wallstreetbets, r/stocks, and r/options. Analyse titles, scores, comment "
            "counts, upvote ratios, and the actual comments to assess retail mood.\n\n"
            "Use get_market_fear_greed(days) to fetch the CNN Fear & Greed Index — a "
            "market-wide macro signal. Use it to contextualise retail sentiment: bullish "
            "Reddit posts carry more weight in a Greed market; bearish posts in an Extreme "
            "Fear market may signal capitulation.\n\n"
            "If Reddit returns no posts (obscure or small-cap ticker), state that clearly — "
            "absence of retail coverage is itself a signal.\n\n"
            "Write a comprehensive sentiment report covering: overall retail mood (bullish / "
            "bearish / mixed), engagement level, notable narratives, current Fear & Greed "
            "reading, and implications for short-term trader sentiment. "
            "Append a Markdown table at the end summarising key data points."
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
