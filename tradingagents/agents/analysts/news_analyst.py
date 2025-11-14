from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.agents.utils.logging_utils import log_report_preview
from tradingagents.agents.utils.tool_runner import (
    extract_text_from_content,
    run_chain_with_tools,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        scheduled_list = state.get("scheduled_analysts", []) or []
        scheduled_plan_list = state.get("scheduled_analysts_plan", []) or []
        scheduled_plan = {item.lower() for item in scheduled_plan_list}
        action = state.get("orchestrator_action", "").lower()
        ticker = state.get("target_ticker") or state["company_of_interest"]
        if (scheduled_plan and "news" not in scheduled_plan) or action not in ("", "monitor", "escalate", "trade", "execute"):
            return {
                "news_report": "News analyst skipped by orchestrator directive.",
                "scheduled_analysts": [item for item in scheduled_list if item.lower() != "news"],
                "scheduled_analysts_plan": scheduled_plan_list,
            }
        current_date = state["trade_date"]

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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
        try:
            print(f"[News Analyst] Running analysis for {ticker} | scheduled={scheduled_list}")
        except Exception:
            pass

        try:
            result, message_history, tool_runs = run_chain_with_tools(
                chain,
                tools,
                state["messages"],
            )
        except Exception as exc:
            updated_schedule = [item for item in scheduled_list if item.lower() != "news"]
            report = f"News analyst failed: {exc}"
            return {
                "messages": state["messages"],
                "news_report": report,
                "scheduled_analysts": updated_schedule,
                "scheduled_analysts_plan": scheduled_plan_list,
            }

        report = extract_text_from_content(getattr(result, "content", "")) or "News analyst produced no narrative."
        updated_schedule = [item for item in scheduled_list if item.lower() != "news"]

        payload = {
            "messages": message_history,
            "news_report": report,
            "scheduled_analysts": updated_schedule,
            "scheduled_analysts_plan": scheduled_plan_list,
        }
        log_report_preview("News Analyst", ticker, report)
        try:
            print(
                f"[News Analyst] Completed step for {ticker} | tool_runs={tool_runs} | report_len={len(report) if report else 0}"
            )
        except Exception:
            pass

        return payload

    return news_analyst_node
