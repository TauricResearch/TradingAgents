from collections.abc import Callable
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.report_quality import tag_report
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    save_node_report,
)
from tradingagents.agents.utils.scanner_tools import get_market_indices
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_market_movers_scanner(llm: Any) -> Callable[[AgentState], dict[str, Any]]:
    def market_movers_scanner_node(state: AgentState) -> dict[str, Any]:
        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "market_movers_report")
        if existing_report:
            return {
                "market_movers_report": existing_report,
                "sender": "market_movers_scanner",
            }

        scan_date = state["scan_date"]

        tools = [get_market_indices]

        system_message = (
            "You are a Senior Quantitative Analyst performing market regime assessment. "
            "Use get_market_indices to quantify broad index and risk-appetite conditions. "
            "Your objective is to produce a clinical, data-dense report on regime deltas. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "Report must include: "
            "(1) Index trends and breadth metrics, "
            "(2) Risk regime classification (Risk-On/Risk-Off/Neutral), "
            "(3) Cap-size participation deltas (Small vs Large), "
            "(4) Tape support for gap-continuation probability. "
            "Do not nominate stocks."
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
        initial_messages = state["messages"][:1] if state["messages"] else []
        result = run_tool_loop(
            chain,
            initial_messages,
            tools,
            require_tool_result=True,
            node_name="market_movers_scanner",
            min_report_length=800,
            max_tool_output_chars=5000,
        )

        report = tag_report(
            result.content or "",
            node_name="market_movers_scanner",
            tools_used="get_market_indices",
        )

        # 3. Resumability: Save after completion
        if report:
            save_node_report(state, "market_movers_report", report)

        return {
            "messages": [result],
            "market_movers_report": report,
            "sender": "market_movers_scanner",
        }

    return market_movers_scanner_node
