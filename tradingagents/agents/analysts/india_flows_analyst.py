from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.utils.india_market_tools import get_india_flows_context


def create_india_flows_analyst(llm):
    def india_flows_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        tools = [get_india_flows_context]
        system_message = (
            "You are the India Flows & Positioning Analyst. Cover FII/DII flows, index breadth, "
            "India VIX, F&O OI, Nifty/Bank Nifty context, liquidity/turnover, and block/bulk deals "
            "only if data exists. Output flows signal, positioning signal, confidence, and unavailable-data notes. "
            "Do not fake FII/DII or OI numbers."
            + get_language_instruction()
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a serious buy-side India-market research assistant. "
                    "Use the provided tools and report unavailable data explicitly. "
                    "Tools: {tool_names}.\n{system_message}\n"
                    "Current date: {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        result = (prompt | llm.bind_tools(tools)).invoke(state["messages"])
        report = "" if result.tool_calls else result.content
        return {"messages": [result], "india_flows_report": report}

    return india_flows_node
