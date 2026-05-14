from langchain_core.messages import HumanMessage, RemoveMessage

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
from tradingagents.agents.utils.range_stats_tool import (
    get_range_stats,
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def summarize_report(report: str, max_chars: int = 1800) -> str:
    """Compress an analyst report for downstream debaters.

    Each analyst report ends with a Markdown summary table. We keep the head
    (thesis + leading analysis) and the tail (which captures the table), since
    those carry the highest signal per token. Returns the report unchanged when
    it already fits the budget.
    """
    if not report:
        return ""
    text = report.strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.55)
    tail = max_chars - head - 32
    return f"{text[:head].rstrip()}\n\n... [truncated for context] ...\n\n{text[-tail:].lstrip()}"


def build_reports_block(state, max_chars_per_report: int = 1800) -> str:
    """Render the 4 analyst reports as a single compact block for debaters."""
    sections = [
        ("Market", state.get("market_report", "")),
        ("Sentiment", state.get("sentiment_report", "")),
        ("News", state.get("news_report", "")),
        ("Fundamentals", state.get("fundamentals_report", "")),
    ]
    parts = []
    for label, body in sections:
        digest = summarize_report(body, max_chars_per_report)
        if digest:
            parts.append(f"### {label} report\n{digest}")
    return "\n\n".join(parts)

ANALYST_PREAMBLE = (
    "You have access to these tools: {tool_names}.\n{system_message}"
    "Today's date is {current_date}. {instrument_context}"
)


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and replace with a directive that compels the next
        analyst to actually use its tools instead of free-writing from memory.

        A bare "Continue" placeholder was insufficient for weaker tool-callers
        (Qwen): they treated it as ambient text and skipped tool invocation.
        Re-stating the ticker plus an imperative reliably triggers function
        calls on every analyst node.
        """
        messages = state["messages"]
        ticker = state.get("company_of_interest", "the company")
        trade_date = state.get("trade_date", "today")

        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(
            content=(
                f"Continue the analysis of {ticker} for trading on "
                f"{trade_date}. Use the available data tools to fetch real "
                f"information before writing your report."
            )
        )

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
