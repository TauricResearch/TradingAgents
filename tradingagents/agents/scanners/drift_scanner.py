from datetime import datetime, timedelta, timezone

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import (
    get_earnings_calendar,
    get_gap_candidates,
    get_topic_news,
)
from tradingagents.agents.utils.tool_runner import run_tool_loop
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    save_node_report,
)


def create_drift_scanner(llm):
    def drift_scanner_node(state):
        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "drift_opportunities_report")
        if existing_report:
            return {
                "drift_opportunities_report": existing_report,
                "sender": "drift_scanner",
            }

        scan_date = state["scan_date"]
        tools = [get_gap_candidates, get_topic_news, get_earnings_calendar]

        gatekeeper_context = state.get("gatekeeper_universe_report", "")
        market_context = state.get("market_movers_report", "")
        sector_context = state.get("sector_performance_report", "")
        context_chunks = []
        if gatekeeper_context:
            context_chunks.append(f"Gatekeeper universe:\n{gatekeeper_context}")
        if market_context:
            context_chunks.append(f"Market regime context:\n{market_context}")
        if sector_context:
            context_chunks.append(f"Sector rotation context:\n{sector_context}")
        context_section = ""
        if context_chunks:
            joined_context = "\n\n".join(context_chunks)
            context_section = f"\n\n{joined_context}"

        try:
            start_date = datetime.strptime(scan_date, "%Y-%m-%d").date()
        except ValueError:
            start_date = datetime.now(timezone.utc).date()
        end_date = start_date + timedelta(days=14)

        system_message = (
            "You are a Senior Quantitative Strategist specializing in drift-window analysis. "
            "Your objective is to identify 1-3 month continuation setups within the gatekeeper universe. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "You MUST perform these bounded searches: "
            "1. get_gap_candidates for technical event filtering, "
            "2. get_topic_news for fundamental catalyst verification (beats, guidance), "
            f"3. get_earnings_calendar from {start_date.isoformat()} to {end_date.isoformat()}. "
            "Report must include: "
            "(1) Gatekeeper tickers with maximum 1-3 month drift probability, "
            "(2) Sector-level drift vs noise assessment, "
            "(3) 5-8 primary candidate tickers with validated catalysts, "
            "(4) Continuation vs Reversal risk deltas. "
            f"Market Context: {market_context[:300]}... Sector Context: {sector_context[:300]}..."
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
            save_node_report(state, "drift_opportunities_report", report)

        return {
            "messages": [result],
            "drift_opportunities_report": report,
            "sender": "drift_scanner",
        }

    return drift_scanner_node
