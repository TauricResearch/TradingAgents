from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import get_gatekeeper_universe
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_gatekeeper_scanner(llm):
    def gatekeeper_scanner_node(state):
        scan_date = state["scan_date"]

        tools = [get_gatekeeper_universe]

        system_message = (
            "You are the gatekeeper scanner for the market-wide search graph. "
            "Your job is to define the only stock universe that downstream agents are allowed to consider.\n\n"
            "You MUST call get_gatekeeper_universe before writing your report.\n"
            "Then write a concise report covering:\n"
            "(1) the size and quality of the eligible universe,\n"
            "(2) which sectors dominate the gatekeeper set,\n"
            "(3) 10-15 representative liquid names worth monitoring,\n"
            "(4) any obvious universe concentration risks.\n\n"
            "Do not introduce stocks outside the gatekeeper universe."
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
            "gatekeeper_universe_report": result.content or "",
            "sender": "gatekeeper_scanner",
        }

    return gatekeeper_scanner_node
