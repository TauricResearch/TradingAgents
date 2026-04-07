from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import get_gatekeeper_universe
from tradingagents.agents.utils.tool_runner import run_tool_loop
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    save_node_report,
)


def create_gatekeeper_scanner(llm):
    def gatekeeper_scanner_node(state):
        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "gatekeeper_universe_report")
        if existing_report:
            return {
                "gatekeeper_universe_report": existing_report,
                "sender": "gatekeeper_scanner",
            }

        scan_date = state["scan_date"]

        tools = [get_gatekeeper_universe]

        system_message = (
            "You are a Senior Investment Economist and your objective is to define the boundary conditions for the investable stock universe. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "You MUST call get_gatekeeper_universe before writing your report. "
            "Report must include: "
            "(1) Universe scale and quality metrics (liquidity, capitalization floors), "
            "(2) Sector distribution deltas, "
            "(3) List of 10-15 primary liquid benchmarks within the universe, "
            "(4) Identified concentration risks. "
            "Do not introduce out-of-universe tickers."
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
            save_node_report(state, "gatekeeper_universe_report", report)

        return {
            "messages": [result],
            "gatekeeper_universe_report": report,
            "sender": "gatekeeper_scanner",
        }

    return gatekeeper_scanner_node
