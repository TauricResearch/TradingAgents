from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.scanner_tools import get_sector_performance
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_sector_scanner(llm):
    def sector_scanner_node(state):
        scan_date = state["scan_date"]

        tools = [get_sector_performance]

        system_message = (
            "You are a Senior Quantitative Economist performing sector rotation analysis. "
            "Use get_sector_performance to analyze all 11 GICS sectors. "
            "Your objective is to produce a clinical, data-dense report on sector performance deltas. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "Report must include: "
            "(1) Sector momentum rankings (1-day, 1-week, 1-month, YTD), "
            "(2) Rotation signals (quantified capital flows between sectors), "
            "(3) Defensive vs Cyclical delta-positioning, "
            "(4) Acceleration/Deceleration metrics. "
            "Include a ranked performance table."
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

        return {
            "messages": [result],
            "sector_performance_report": report,
            "sender": "sector_scanner",
        }

    return sector_scanner_node
