from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_economic_indicators,
    get_fed_calendar,
    get_yield_curve,
)


def _merge_with_news_report(existing_report: str, macro_report: str) -> str:
    if not macro_report:
        return existing_report
    if not existing_report:
        return macro_report
    return f"{existing_report.rstrip()}\n\n## Macro Economic Overlay\n\n{macro_report}"


def create_macro_analyst(llm):
    def macro_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_economic_indicators,
            get_yield_curve,
            get_fed_calendar,
        ]

        system_message = (
            "You are a macroeconomic analyst responsible for turning Federal Reserve "
            "data, inflation data, labor data, and the Treasury curve into a trading "
            "usable macro view. Use `get_economic_indicators` to establish the growth, "
            "inflation, and labor backdrop, `get_yield_curve` to explain the rates "
            "curve and recession signal, and `get_fed_calendar` to summarize the policy "
            "path. Focus on regime identification, likely policy direction, cross-asset "
            "implications, and concrete risks that other analysts should incorporate."
            " Append a Markdown table that summarizes the major macro signals and their "
            "market implications."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "macro_report": report,
            "news_report": _merge_with_news_report(state.get("news_report", ""), report),
        }

    return macro_analyst_node
