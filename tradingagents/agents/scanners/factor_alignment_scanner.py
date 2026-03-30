from datetime import datetime, timedelta, timezone

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import get_earnings_calendar, get_topic_news
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_factor_alignment_scanner(llm):
    def factor_alignment_scanner_node(state):
        scan_date = state["scan_date"]
        tools = [get_topic_news, get_earnings_calendar]

        sector_context = state.get("sector_performance_report", "")
        sector_section = (
            f"\n\nSector rotation context from the Sector Scanner:\n{sector_context}"
            if sector_context
            else ""
        )

        try:
            start_date = datetime.strptime(scan_date, "%Y-%m-%d").date()
        except ValueError:
            start_date = datetime.now(timezone.utc).date()
        end_date = start_date + timedelta(days=21)

        system_message = (
            "You are a factor strategist looking for global 1-3 month drift signals from analyst sentiment and "
            "earnings revision flow. Stay market-wide: do not deep-dive individual tickers one by one.\n\n"
            "You MUST perform these bounded searches:\n"
            "1. Call get_topic_news on analyst upgrades/downgrades and recommendation changes.\n"
            "2. Call get_topic_news on earnings estimate revisions, raised guidance, and estimate cuts.\n"
            f"3. Call get_earnings_calendar from {start_date.isoformat()} to {end_date.isoformat()}.\n\n"
            "Then write a concise report covering:\n"
            "(1) sectors/themes seeing the strongest positive revision breadth,\n"
            "(2) sectors/themes with deteriorating revision pressure,\n"
            "(3) 5-8 globally surfaced tickers that appear repeatedly in the analyst/revision flow,\n"
            "(4) how this factor evidence aligns or conflicts with the sector-tailwind backdrop.\n"
            "Prefer names that show both positive analyst tone and upward earnings expectation drift."
            f"{sector_section}"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=scan_date)

        chain = prompt | llm.bind_tools(tools)
        result = run_tool_loop(chain, state["messages"], tools)

        return {
            "messages": [result],
            "factor_alignment_report": result.content or "",
            "sender": "factor_alignment_scanner",
        }

    return factor_alignment_scanner_node
