from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
    supports_tool_calls,
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        if supports_tool_calls(llm):
            return _tool_call_path(llm, state, current_date, ticker, instrument_context)
        return _prefetch_path(llm, state, current_date, ticker, instrument_context)

    return fundamentals_analyst_node


# ── Tool-call path (API providers) ────────────────────────────────────────

def _tool_call_path(llm, state, current_date, ticker, instrument_context):
    """Original flow: bind_tools → LLM selects and calls tools."""
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
        "fundamentals_report": report,
    }


# ── Pre-fetch path (CLI provider) ────────────────────────────────────────

def _prefetch_path(llm, state, current_date, ticker, instrument_context):
    """Pre-fetch all financial data and inject into prompt."""
    def _safe_fetch(fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            return f"<unavailable: {e}>"

    fundamentals_data = _safe_fetch(get_fundamentals.func, ticker, current_date)
    balance_sheet_data = _safe_fetch(get_balance_sheet.func, ticker, "quarterly", current_date)
    cashflow_data = _safe_fetch(get_cashflow.func, ticker, "quarterly", current_date)
    income_data = _safe_fetch(get_income_statement.func, ticker, "quarterly", current_date)

    system_message = _build_prefetch_system_message(
        ticker=ticker,
        current_date=current_date,
        fundamentals_data=fundamentals_data,
        balance_sheet_data=balance_sheet_data,
        cashflow_data=cashflow_data,
        income_data=income_data,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                "\n{system_message}\n"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(current_date=current_date)
    prompt = prompt.partial(instrument_context=instrument_context)

    chain = prompt | llm
    result = chain.invoke(state["messages"])

    return {
        "messages": [result],
        "fundamentals_report": result.content,
    }


# ── System message for pre-fetch path ────────────────────────────────────

def _build_prefetch_system_message(
    *,
    ticker: str,
    current_date: str,
    fundamentals_data: str,
    balance_sheet_data: str,
    cashflow_data: str,
    income_data: str,
) -> str:
    """Assemble the fundamentals analyst system message with pre-fetched data."""
    return f"""You are a researcher tasked with analyzing fundamental information about {ticker} as of {current_date}. All financial data has been pre-fetched and is included below.

## Data sources (pre-fetched, in this prompt)

### Company Fundamentals
Comprehensive overview: profile, key metrics, valuation ratios, growth rates.

<start_of_fundamentals>
{fundamentals_data}
<end_of_fundamentals>

### Balance Sheet (Quarterly)

<start_of_balance_sheet>
{balance_sheet_data}
<end_of_balance_sheet>

### Cash Flow Statement (Quarterly)

<start_of_cashflow>
{cashflow_data}
<end_of_cashflow>

### Income Statement (Quarterly)

<start_of_income_statement>
{income_data}
<end_of_income_statement>

## Instructions

1. Analyze the company profile, sector positioning, and competitive landscape.
2. Evaluate financial health: liquidity, solvency, and profitability trends across quarters.
3. Assess cash flow quality: operating cash flow vs net income, capex trends, free cash flow.
4. Identify revenue growth trends, margin compression/expansion, and earnings quality.
5. Flag any red flags: declining margins, rising debt, cash burn, or accounting anomalies.
6. Write a comprehensive fundamental analysis report with specific, actionable insights.
7. Append a Markdown table at the end summarizing key financial metrics and their implications.

{get_language_instruction()}"""
