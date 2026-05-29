from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
from tradingagents.agents.utils.options_data_tools import (
    get_options_chain,
)


DEBATE_EVIDENCE_GUARDRAIL = (
    "\n\nEvidence discipline (REQUIRED):\n"
    "- Cite at least 2 specific data points from the reports above — numbers, dates, "
    "or exact phrases. Generic claims like \"the trend is strong\" do not count.\n"
    "- Acknowledge at least ONE concrete piece of evidence that argues against your side. "
    "If you cannot find one, your case is too one-sided to be useful.\n"
    "- If a key input is unavailable (e.g. options chain missing for a historical date, "
    "no usable volume_ratio), say so explicitly rather than substitute speculation.\n"
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Call sites decide where to apply this (reports, debates, manager outputs).
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def truncate_history(history: str, max_chars: int = 3000) -> str:
    """Keep only the tail of a debate history string to bound token growth.

    Trims to the last max_chars characters and starts at a clean line boundary
    so the LLM never receives a half-sentence. Prefixes with an omission notice
    when truncation occurs.
    """
    if len(history) <= max_chars:
        return history
    tail = history[-max_chars:]
    newline = tail.find("\n")
    if newline != -1:
        tail = tail[newline + 1:]
    return "[...earlier history omitted...]\n" + tail


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def build_capital_context(holdings_info: dict | None) -> str:
    """Format portfolio NAV + ticker-level holdings for downstream prompts.

    Returns empty string when no NAV is present (e.g. backtest mode), so call
    sites can append unconditionally. NAV is the live-mode capital anchor that
    managers/trader/risk debators must use to size recommendations.
    """
    if not holdings_info:
        return ""
    nav = holdings_info.get("nav")
    if nav is None:
        return ""
    quantity = holdings_info.get("quantity")
    avg_buy_price = holdings_info.get("avg_buy_price")
    cost_basis = None
    if quantity and avg_buy_price:
        cost_basis = float(quantity) * float(avg_buy_price)

    parts = [f"Total portfolio NAV: {float(nav):,.2f}"]
    if quantity and avg_buy_price:
        parts.append(
            f"existing position in this ticker: {float(quantity):g} shares "
            f"at avg cost {float(avg_buy_price):g} (cost basis {cost_basis:,.2f}, "
            f"≈{cost_basis / float(nav):.0%} of NAV)"
        )
    else:
        parts.append("no existing position in this ticker (all NAV is allocatable)")

    return (
        "**Capital context:** "
        + "; ".join(parts)
        + ". Size every entry / add / take-profit / stop in absolute share counts AND as a percent of NAV; "
        "do not propose orders whose dollar value exceeds available NAV."
    )

def create_force_finalize(llm, report_key: str, analyst_label: str):
    """Build a node that forces an analyst to emit its final report without tools.

    Reached when the analyst's tool-call budget is exhausted but the LLM is
    still requesting tools. The node strips the dangling AIMessage(tool_calls=...)
    and re-invokes the LLM with no tools bound, feeding it the tool results
    already collected so it can write the report from the data it has.
    """
    def force_finalize_node(state):
        messages = state["messages"]
        tool_outputs = [
            f"Tool result:\n{m.content}"
            for m in messages
            if isinstance(m, ToolMessage)
        ]
        data_block = (
            "\n\n".join(tool_outputs)
            if tool_outputs
            else "(no tool data was collected before budget exhaustion)"
        )

        current_date = state.get("trade_date", "")
        instrument = build_instrument_context(state["company_of_interest"])

        system = (
            f"You are the {analyst_label}. Your tool-call budget is exhausted. "
            "Write the final report now using only the data already collected below. "
            "Do not request any more tools — none are available. "
            f"Begin the report with exactly this line: # As-of date: {current_date}. "
            f"{instrument}"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system),
            ("human", "Data collected so far:\n\n{data}\n\nWrite the report now."),
        ])

        result = (prompt | llm).invoke({"data": data_block})

        ops = []
        last = messages[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            ops.append(RemoveMessage(id=last.id))
        ops.append(result)

        return {
            "messages": ops,
            report_key: result.content,
        }

    return force_finalize_node


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
