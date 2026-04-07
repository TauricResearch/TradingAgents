from datetime import datetime, timedelta, timezone

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import get_earnings_calendar, get_topic_news
from tradingagents.agents.utils.tool_runner import run_tool_loop
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    save_node_report,
)


def create_factor_alignment_scanner(llm):
    def factor_alignment_scanner_node(state):
        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "factor_alignment_report")
        if existing_report:
            return {
                "factor_alignment_report": existing_report,
                "sender": "factor_alignment_scanner",
            }

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
            "You are a Senior Factor Strategist and Economist analyzing 1-3 month drift signals. "
            "Your objective is to quantify analyst sentiment and earnings revision flow at a market-wide scale. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "You MUST perform these bounded searches: "
            "1. get_topic_news for analyst recommendation deltas, "
            "2. get_topic_news for earnings estimate and guidance revisions, "
            f"3. get_earnings_calendar from {start_date.isoformat()} to {end_date.isoformat()}. "
            "Report must include: "
            "(1) Sectors with maximum positive revision breadth, "
            "(2) Sectors with deteriorating revision pressure, "
            "(3) 5-8 primary tickers surfaced from aggregate revision flow, "
            "(4) Factor alignment/divergence vs current sector tailwinds. "
            f"Sector Context: {sector_context[:500]}..." # Truncated to avoid bloat
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

        report = result.content or ""

        # 3. Resumability: Save after completion
        if report:
            save_node_report(state, "factor_alignment_report", report)

        return {
            "messages": [result],
            "factor_alignment_report": report,
            "sender": "factor_alignment_scanner",
        }

    return factor_alignment_scanner_node
