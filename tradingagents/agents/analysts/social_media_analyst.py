from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.agents.utils.logging_utils import log_report_preview
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        scheduled_list = state.get("scheduled_analysts", []) or []
        scheduled_plan_list = state.get("scheduled_analysts_plan", []) or []
        scheduled_plan = {item.lower() for item in scheduled_plan_list}
        action = state.get("orchestrator_action", "").lower()
        ticker = state.get("target_ticker") or state["company_of_interest"]
        if (scheduled_plan and "social" not in scheduled_plan) or action not in ("", "monitor", "escalate", "trade", "execute"):
            return {
                "sentiment_report": "Social media analyst skipped by orchestrator directive.",
                "scheduled_analysts": [item for item in scheduled_list if item.lower() != "social"],
                "scheduled_analysts_plan": scheduled_plan_list,
            }
        current_date = state["trade_date"]
        company_name = ticker

        tools = [
            get_news,
        ]

        system_message = (
            "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.""",
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

        try:
            print(f"[Social Analyst] Running analysis for {ticker} | scheduled={scheduled_list}")
        except Exception:
            pass

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        updated_schedule = [item for item in scheduled_list if item.lower() != "social"]

        payload = {
            "messages": [result],
            "sentiment_report": report,
            "scheduled_analysts": updated_schedule,
            "scheduled_analysts_plan": scheduled_plan_list,
        }
        if report is not None:
            log_report_preview("Social Analyst", ticker, report)
        try:
            print(f"[Social Analyst] Completed step for {ticker} | tool_calls={len(result.tool_calls)} | report_len={len(report) if report else 0}")
        except Exception:
            pass

        return payload

    return social_media_analyst_node
