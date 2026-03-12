from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import (
    get_news,
    get_global_news,
    get_korean_news,
    get_korean_global_news,
    get_dart_disclosures,
)
from tradingagents.agents.utils.korean_prompt import (
    KOREAN_INVESTOR_GUIDE,
    KOREAN_REPORT_FORMAT_GUIDE,
    SWING_TRADING_CONTEXT,
    SWING_PORTFOLIO_CONTEXT,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        config = get_config()
        market = config.get("market", "US") if config else "US"

        if market == "KRX":
            tools = [
                get_korean_news,
                get_korean_global_news,
                get_dart_disclosures,
            ]
        else:
            tools = [
                get_news,
                get_global_news,
            ]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + KOREAN_INVESTOR_GUIDE
            + KOREAN_REPORT_FORMAT_GUIDE
            + SWING_TRADING_CONTEXT
            + SWING_PORTFOLIO_CONTEXT
        )

        # Inject swing context if available
        screening_ctx = state.get("screening_context", "")
        portfolio_ctx = state.get("portfolio_context", "")
        position_status = state.get("position_status", "NONE")
        if screening_ctx or portfolio_ctx:
            system_message += f"\n\n[현재 분석 컨텍스트]\n포지션 상태: {position_status}\n"
            if screening_ctx:
                system_message += f"스크리닝 선정 이유: {screening_ctx}\n"
            if portfolio_ctx:
                system_message += f"\n{portfolio_ctx}\n"

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/PASS** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/PASS** so the team knows to stop."
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
