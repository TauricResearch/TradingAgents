from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
)

# Upper bound on agent -> tools -> agent rounds inside the analyst branch.
# The branch is now a single self-contained node (so the four analysts can run
# concurrently and converge once), and this cap keeps a tool-happy model from
# looping forever.
MAX_ANALYST_TOOL_ROUNDS = 8


def create_fundamentals_analyst(llm, tool_node=None):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
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
            + get_language_instruction(),
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
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="fundamentals_messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        # Self-contained branch loop: run the LLM, execute any tool calls it
        # requests via the branch ToolNode, and repeat until it produces a
        # final report (or the round cap is hit).
        messages = list(state["fundamentals_messages"])
        result = None
        for _ in range(MAX_ANALYST_TOOL_ROUNDS):
            result = chain.invoke(messages)
            if not getattr(result, "tool_calls", None):
                break
            if tool_node is None:
                break
            # ToolNode returns only the newly produced ToolMessages; append
            # them to the running history so the next LLM round still sees the
            # preceding AIMessage(tool_calls) that each ToolMessage answers.
            messages = messages + [result]
            output = tool_node.invoke({"fundamentals_messages": messages})
            messages = messages + list(output["fundamentals_messages"])
        report = result.content if result is not None else ""

        return {
            "fundamentals_messages": messages,
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
