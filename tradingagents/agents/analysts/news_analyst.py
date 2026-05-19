from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_caixin_news,
    get_company_announcements,
    get_company_event_signals,
    get_decision_signal_summary,
    get_global_news,
    get_language_instruction,
    get_market_activity,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        market_region = str(get_config().get("market_region", "us")).lower()
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [
            get_news,
            get_global_news,
        ]
        if market_region == "cn_a" and asset_type == "stock":
            tools.extend([
                get_company_announcements,
                get_company_event_signals,
                get_market_activity,
                get_decision_signal_summary,
                get_caixin_news,
            ])

        if market_region == "cn_a" and asset_type == "stock":
            system_message = (
                "You are an A-share news researcher tasked with analyzing recent company, market, and policy developments over the past week. "
                f"Use `get_news` for {asset_label}-specific information packs, `get_global_news` for broader China market and policy context, "
                "`get_company_announcements` for official exchange disclosures, `get_company_event_signals` for event summaries, "
                "`get_market_activity` for capital-flow / northbound / margin context, `get_decision_signal_summary` for a consolidated event-and-flow read, and `get_caixin_news` for supplementary financial journalism when available. "
                "Weight official announcements and policy headlines heavily, because they often matter more than social chatter in A-share trading. "
                "Highlight catalysts such as earnings pre-announcements, shareholder changes, regulation, sector policy, and trading suspensions when present. "
                "Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                + get_language_instruction()
            )
        else:
            system_message = (
                f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
                + get_language_instruction()
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
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
