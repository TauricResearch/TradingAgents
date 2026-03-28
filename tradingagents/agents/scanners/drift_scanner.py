from datetime import datetime, timedelta, timezone

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import (
    get_earnings_calendar,
    get_gap_candidates,
    get_topic_news,
)
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_drift_scanner(llm):
    def drift_scanner_node(state):
        scan_date = state["scan_date"]
        tools = [get_gap_candidates, get_topic_news, get_earnings_calendar]

        market_context = state.get("market_movers_report", "")
        sector_context = state.get("sector_performance_report", "")
        context_chunks = []
        if market_context:
            context_chunks.append(f"Market movers context:\n{market_context}")
        if sector_context:
            context_chunks.append(f"Sector rotation context:\n{sector_context}")
        context_section = f"\n\n{'\n\n'.join(context_chunks)}" if context_chunks else ""

        try:
            start_date = datetime.strptime(scan_date, "%Y-%m-%d").date()
        except ValueError:
            start_date = datetime.now(timezone.utc).date()
        end_date = start_date + timedelta(days=14)

        system_message = (
            "You are a drift-window scanner focused on 1-3 month continuation setups. "
            "Stay global and bounded: use the existing market movers context, then confirm whether those moves "
            "look like the start of a sustained drift rather than one-day noise.\n\n"
            "You MUST perform these bounded searches:\n"
            "1. Call get_gap_candidates to retrieve real market-data gap candidates.\n"
            "2. Call get_topic_news for earnings beats, raised guidance, and positive post-event follow-through.\n"
            f"3. Call get_earnings_calendar from {start_date.isoformat()} to {end_date.isoformat()}.\n\n"
            "Then write a concise report covering:\n"
            "(1) which current movers look most likely to sustain a 1-3 month drift,\n"
            "(2) which sectors show the cleanest drift setup rather than short-covering noise,\n"
            "(3) 5-8 candidate tickers surfaced globally from the mover context plus catalyst confirmation,\n"
            "(4) the key evidence for continuation risk versus reversal risk."
            f"{context_section}"
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
            "drift_opportunities_report": result.content or "",
            "sender": "drift_scanner",
        }

    return drift_scanner_node
