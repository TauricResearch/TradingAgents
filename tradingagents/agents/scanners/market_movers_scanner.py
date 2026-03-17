from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import get_market_movers, get_market_indices
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_market_movers_scanner(llm):
    def market_movers_scanner_node(state):
        scan_date = state["scan_date"]

        tools = [get_market_movers, get_market_indices]

        system_message = (
            "You are a market analyst scanning for unusual activity and momentum signals. "
            "Use get_market_movers to fetch today's top gainers, losers, and most active stocks. "
            "Use get_market_indices to check major index performance. "
            "Analyze the results and write a report covering: "
            "(1) Unusual movers and potential catalysts, "
            "(2) Volume anomalies, "
            "(3) Index trends and breadth, "
            "(4) Sector concentration in movers. "
            "Include a summary table of the most significant moves."
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
            "market_movers_report": report,
            "sender": "market_movers_scanner",
        }

    return market_movers_scanner_node
