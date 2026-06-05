from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.agents.utils.prompt_cache import stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


FUNDAMENTALS_SYSTEM_MESSAGE = (
    "You are a researcher tasked with analyzing fundamental information over the past week about "
    "the instrument. Write a comprehensive report covering financial documents, profile, basic "
    "financials, and financial history to inform traders. Include as much detail as the data "
    "supports. Provide specific, actionable insights with supporting evidence. Append a Markdown "
    "table at the end of the report to organize key points. Use the available tools: "
    "get_fundamentals for comprehensive analysis, get_balance_sheet, get_cashflow, and "
    "get_income_statement for specific financial statements."
)


def build_fundamentals_user_prompt(*, current_date: str, instrument_context: str) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            (
                "Current Task",
                "Use the available fundamentals tools to produce the fundamentals report.",
            ),
        ]
    )


def create_fundamentals_analyst(llm, persona=None):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = apply_fragment(
            FUNDAMENTALS_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_fundamentals_user_prompt(
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
