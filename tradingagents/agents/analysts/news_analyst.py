from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.prompt_cache import stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


NEWS_SYSTEM_MESSAGE = (
    "You are a news researcher tasked with analyzing recent news and trends over the past week. "
    "Write a comprehensive report of the current state of the world that is relevant for trading "
    "and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for "
    "instrument-specific or targeted news searches, and get_global_news(curr_date, look_back_days, "
    "limit) for broader macroeconomic news. Provide specific, actionable insights with supporting "
    "evidence to help traders make informed decisions. Append a Markdown table at the end of the "
    "report to organize key points."
)


def build_news_user_prompt(*, current_date: str, instrument_context: str) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            (
                "Current Task",
                "Use targeted and global news tools to produce the news and macro report.",
            ),
        ]
    )


def create_news_analyst(llm, persona=None):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = apply_fragment(
            NEWS_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_news_user_prompt(
            current_date=current_date,
            instrument_context=instrument_context,
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
                    " You have access to the following tools: {tool_names}.\n{system_message}",
                ),
                ("human", "{user_prompt}"),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(user_prompt=user_prompt)

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
