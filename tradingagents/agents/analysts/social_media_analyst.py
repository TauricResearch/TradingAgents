from langchain_core.messages import HumanMessage, SystemMessage
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.tool_utils import dispatch_tool_calls
from tradingagents.agents.prompts import load_prompt


def create_social_media_analyst(llm):

    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news]
        llm_with_tools = llm.bind_tools(tools)
        tool_map = {t.name: t for t in tools}

        system_message = load_prompt("social_media_analyst") + get_language_instruction()

        messages = [
            SystemMessage(
                content=(
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    f" You have access to the following tools: {', '.join(tool_map)}.\n{system_message}"
                    f" For your reference, the current date is {current_date}. {instrument_context}"
                )
            ),
            HumanMessage(content=state["company_of_interest"]),
        ]

        while True:
            result = llm_with_tools.invoke(messages)
            messages.append(result)
            if not result.tool_calls:
                break
            messages.extend(dispatch_tool_calls(tool_map, result.tool_calls))

        return {"analyst_reports": {"social": result.content}}

    return social_media_analyst_node
