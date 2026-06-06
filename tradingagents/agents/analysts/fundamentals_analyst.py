from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.agents.utils.tool_fallback import bind_tools_or_none, safe_tool_text


def _prefetch_fundamentals_data(ticker: str, current_date: str) -> str:
    """Gather the fundamentals the tools would return, for tool-less providers."""
    fundamentals = safe_tool_text(
        "comprehensive fundamentals",
        lambda: get_fundamentals.func(ticker, current_date),
    )
    balance_sheet = safe_tool_text(
        "balance sheet",
        lambda: get_balance_sheet.func(ticker, curr_date=current_date),
    )
    cashflow = safe_tool_text(
        "cash flow statement",
        lambda: get_cashflow.func(ticker, curr_date=current_date),
    )
    income = safe_tool_text(
        "income statement",
        lambda: get_income_statement.func(ticker, curr_date=current_date),
    )

    return (
        "### Comprehensive fundamentals\n"
        f"{fundamentals}\n\n"
        "### Balance sheet\n"
        f"{balance_sheet}\n\n"
        "### Cash flow statement\n"
        f"{cashflow}\n\n"
        "### Income statement\n"
        f"{income}"
    )


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = str(state["company_of_interest"])
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction()
        )

        bound_llm = bind_tools_or_none(llm, tools, "Fundamentals Analyst")

        if bound_llm is not None:
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

            chain = prompt | bound_llm

            result = chain.invoke(state["messages"])

            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

            return {
                "messages": [result],
                "fundamentals_report": report,
            }

        # Tool-free fallback: pre-fetch the financial statements and inject them
        # into the prompt for providers (e.g. codex) that cannot bind tools.
        fundamentals_data = _prefetch_fundamentals_data(ticker, current_date)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " The fundamental data you need has ALREADY been gathered for you and is included below;"
                    " do NOT call any tools and disregard any instruction below to call a tool —"
                    " base your report only on the provided data."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "=== Pre-fetched fundamentals ===\n{fundamentals_data}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(fundamentals_data=fundamentals_data)

        formatted_messages = prompt.format_messages(messages=state["messages"])
        result = llm.invoke(formatted_messages)

        return {
            "messages": [result],
            "fundamentals_report": result.content,
        }

    return fundamentals_analyst_node
