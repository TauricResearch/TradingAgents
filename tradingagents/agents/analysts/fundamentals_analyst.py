from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_peer_comparison,
    get_sector_relative,
    get_ttm_analysis,
)
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        # ── Pre-fetch the four mandatory foundational datasets in parallel ────
        # get_ttm_analysis, get_fundamentals, get_peer_comparison, and
        # get_sector_relative are always called — pre-fetching them removes
        # 4 LLM round-trips.  The raw financial statements (balance sheet,
        # cashflow, income statement) stay iterative: the LLM may request them
        # only if it spots anomalies worth investigating in the pre-loaded data.
        prefetched = prefetch_tools_parallel(
            [
                {
                    "tool": get_ttm_analysis,
                    "args": {"ticker": ticker, "curr_date": current_date},
                    "label": "TTM Analysis (8-Quarter Trend)",
                },
                {
                    "tool": get_fundamentals,
                    "args": {"ticker": ticker, "curr_date": current_date},
                    "label": "Fundamental Ratios Snapshot",
                },
                {
                    "tool": get_peer_comparison,
                    "args": {"ticker": ticker, "curr_date": current_date},
                    "label": "Peer Comparison",
                },
                {
                    "tool": get_sector_relative,
                    "args": {"ticker": ticker, "curr_date": current_date},
                    "label": "Sector Relative Performance",
                },
            ]
        )
        prefetched_context = format_prefetched_context(prefetched)

        # ── Only the raw statement tools remain iterative ─────────────────────
        tools = [get_balance_sheet, get_cashflow, get_income_statement]

        system_message = (
            "You are a researcher tasked with performing deep fundamental analysis of a company "
            "over the last 8 quarters (2 years) to support medium-term investment decisions.\n\n"
            "## Pre-loaded Foundational Data\n\n"
            "The following datasets have already been fetched and are provided in the "
            "**Pre-loaded Context** section below. Do NOT call `get_ttm_analysis`, "
            "`get_fundamentals`, `get_peer_comparison`, or `get_sector_relative` — "
            "that data is already available:\n\n"
            "- **TTM Analysis**: 8-quarter Trailing Twelve Months trends — revenue growth "
            "(QoQ and YoY), margin trajectories (gross, operating, net), ROE trend, "
            "debt/equity trend, and free cash flow.\n"
            "- **Fundamental Ratios**: Latest snapshot of key ratios (PE, PEG, price-to-book, "
            "beta, 52-week range).\n"
            "- **Peer Comparison**: How the company ranks against sector peers over 1-week, "
            "1-month, 3-month, and 6-month periods.\n"
            "- **Sector Relative Performance**: The company's alpha vs its sector ETF benchmark.\n\n"
            "## Your Task\n\n"
            "Interpret the pre-loaded data analytically. Look for:\n"
            "- Revenue and margin inflection points — acceleration, deceleration, or trend reversals\n"
            "- Suspicious deviations in FCF vs reported net income (earnings quality signals)\n"
            "- Peer divergence — is the company outperforming or underperforming its sector?\n"
            "- Valuation anomalies vs growth trajectory (PEG vs actual growth rate)\n\n"
            "If you identify anything suspicious in the TTM or fundamentals data that warrants "
            "deeper investigation — for example, a margin inflection without an obvious revenue "
            "driver, an FCF deviation from net income, or an unusual balance-sheet move — you "
            "may call `get_balance_sheet`, `get_cashflow`, or `get_income_statement` to examine "
            "the raw quarterly data directly.\n\n"
            "## CRITICAL ABORT TRIGGER\n\n"
            "If you detect any of the following CATASTROPHIC conditions, you MUST immediately "
            "prepend `[CRITICAL ABORT]` to your report and provide specific reasoning:\n\n"
            "### Bankruptcy and Financial Distress:\n"
            "- Bankruptcy filing or Chapter 11/7 proceedings\n"
            "- Negative gross margins (gross margin < 0%)\n"
            "- Negative operating margins (operating margin < 0%)\n"
            "- Negative net income with no path to recovery\n"
            "- Negative book value or negative equity\n"
            "- Cash flow from operations < 0 with no turnaround plan\n\n"
            "### SEC and Regulatory Issues:\n"
            "- SEC enforcement action or investigation for material fraud\n"
            "- Impending SEC delisting (notice of non-compliance)\n"
            "- Going concern warning from auditor\n"
            "- Regulatory shutdown or cease-and-desist order\n\n"
            "### Material Fraud and Accounting Issues:\n"
            "- Evidence of accounting manipulation or earnings management\n"
            "- Revenue recognition violations\n"
            "- Material restatement of financial statements\n"
            "- Insider trading violations or SEC violations\n\n"
            "### Format Requirements:\n"
            "When triggering a critical abort, your report MUST start with:\n"
            "`[CRITICAL ABORT] Reason: <specific reason for abort>`\n\n"
            "Example: `[CRITICAL ABORT] Reason: Bankruptcy filing detected - negative gross margin of -15% with no path to recovery`\n\n"
            "## Normal Operation\n\n"
            "If no catastrophic conditions are detected, write a comprehensive report covering: "
            "multi-quarter revenue and margin trends, TTM metrics, relative valuation vs peers, "
            "sector outperformance or underperformance, and a clear medium-term fundamental thesis. "
            "Do not simply state trends are mixed — provide detailed, fine-grained analysis that "
            "identifies inflection points, acceleration or deceleration in growth, and specific "
            "risks and opportunities. "
            "Make sure to append a Markdown summary table at the end of the report organising "
            "key metrics for easy reference."
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
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        chain = prompt | llm.bind_tools(tools)

        result = run_tool_loop(chain, state["messages"], tools)

        report = result.content or ""

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
