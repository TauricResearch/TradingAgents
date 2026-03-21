from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.scanner_tools import get_topic_news
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_geopolitical_scanner(llm):
    def geopolitical_scanner_node(state):
        scan_date = state["scan_date"]

        tools = [get_topic_news]

        system_message = (
            "You are a geopolitical analyst scanning global news for risks and opportunities affecting financial markets. "
            "Use get_topic_news to search for news on: geopolitics, trade policy, sanctions, central bank decisions, "
            "energy markets, and military conflicts. Analyze the results and write a concise report covering: "
            "(1) Major geopolitical events and their market impact, "
            "(2) Central bank policy signals, "
            "(3) Trade/sanctions developments, "
            "(4) Energy and commodity supply risks. "
            "Include a risk assessment table at the end."
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
            "geopolitical_report": report,
            "sender": "geopolitical_scanner",
        }

    return geopolitical_scanner_node
