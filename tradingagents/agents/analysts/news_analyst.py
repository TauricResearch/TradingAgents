from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_global_news,
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
    get_news_research_bundle,
)
from tradingagents.skills import (
    build_role_report_contract,
    build_role_skill_prompt,
    build_skill_trigger_context,
    emit_methodology_artifact,
    finalize_role_report,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        skill_trigger_text = build_skill_trigger_context(state.get("messages", ()))
        emit_methodology_artifact("news_analyst", trigger_text=skill_trigger_text)
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_news,
            get_global_news,
            get_macro_indicators,
            get_news_research_bundle,
        ]

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(ticker, start_date, end_date) for {asset_label}-specific news by ticker symbol, get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news, get_macro_indicators(indicator, curr_date, look_back_days) to ground macro commentary in actual data from FRED (e.g. 'cpi', 'core_pce', 'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve'). When company news and a macro view are both useful, prefer get_news_research_bundle(symbol, curr_date, request): it maps a plain-language request only to reviewed capabilities, fetches a bounded subset concurrently, and returns capability-level provenance plus public error categories. It cannot select providers or invoke arbitrary tools. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )
        system_message += build_role_skill_prompt(
            "news_analyst", trigger_text=skill_trigger_text
        )
        system_message += build_role_report_contract("news_analyst")

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
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        methodology_artifact = None

        if len(result.tool_calls) == 0:
            report, methodology_artifact = finalize_role_report("news_analyst", result.content)

        output = {
            "messages": [result],
            "news_report": report,
        }
        if methodology_artifact is not None:
            output["methodology_reports"] = {
                **state.get("methodology_reports", {}),
                "news_analyst": methodology_artifact,
            }
        return output

    return news_analyst_node
