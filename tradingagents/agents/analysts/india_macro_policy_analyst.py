from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.utils.india_market_tools import get_india_macro_context, get_india_sector_context


def create_india_macro_policy_analyst(llm):
    def india_macro_policy_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        tools = [get_india_macro_context, get_india_sector_context]
        system_message = (
            "You are the India Macro & Policy Analyst. Cover RBI policy, inflation, INR, crude, "
            "liquidity, Budget/GST/tax policy, SEBI/RBI sector policy, and global factors relevant "
            "to India. Translate macro into sector impact and risk triggers. Output macro tailwinds, "
            "macro headwinds, sector impact, market regime, risk triggers, and data-quality notes."
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
        return {"messages": [result], "india_macro_policy_report": report}

    return india_macro_policy_node
