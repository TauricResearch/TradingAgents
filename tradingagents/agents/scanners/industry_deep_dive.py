from __future__ import annotations

import re
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.scanner_tools import get_industry_performance, get_topic_news
from tradingagents.agents.utils.tool_runner import run_tool_loop

# All valid sector keys accepted by yfinance Sector() and get_industry_performance.
VALID_SECTOR_KEYS = [
    "technology",
    "healthcare",
    "financial-services",
    "energy",
    "consumer-cyclical",
    "consumer-defensive",
    "industrials",
    "basic-materials",
    "real-estate",
    "utilities",
    "communication-services",
]

# Map display names used in the sector performance report to valid keys.
_DISPLAY_TO_KEY = {
    "technology": "technology",
    "healthcare": "healthcare",
    "financials": "financial-services",
    "financial services": "financial-services",
    "energy": "energy",
    "consumer discretionary": "consumer-cyclical",
    "consumer staples": "consumer-defensive",
    "industrials": "industrials",
    "materials": "basic-materials",
    "basic materials": "basic-materials",
    "real estate": "real-estate",
    "utilities": "utilities",
    "communication services": "communication-services",
}


def _extract_top_sectors(sector_report: str, top_n: int = 3) -> list[str]:
    """Parse the sector performance report and return the *top_n* sector keys
    ranked by strongest positive 1-month performance.

    The sector performance table looks like:

        | Technology | +0.45% | +1.20% | +5.67% | +12.3% |

    We parse the 1-month column (index 3) and rank sectors by descending
    1-month performance so the deep dive follows sector tailwinds. When all
    sectors are weak, this still returns the least-bad leaders.
    If the report is not a table, it attempts to parse list formats
    (bullet points, numbered lists, or plain text).

    Returns a list of valid sector keys (e.g. ``["technology", "energy"]``).
    Falls back to a sensible default if parsing fails.
    """
    if not sector_report:
        return VALID_SECTOR_KEYS[:top_n]

    rows: list[tuple[str, float]] = []
    for line in sector_report.split("\n"):
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 4:
            continue
        sector_name = cols[0].lower()
        if sector_name in ("sector", "---", "") or "---" in sector_name:
            continue
        # Try to parse the 1-month column (index 3)
        try:
            month_str = cols[3].replace("%", "").replace("+", "").strip()
            month_val = float(month_str)
        except (ValueError, IndexError):
            continue
        key = _DISPLAY_TO_KEY.get(sector_name)
        if key:
            rows.append((key, month_val))

    if rows:
        rows.sort(key=lambda r: r[1], reverse=True)
        return [r[0] for r in rows[:top_n]]

    # Fallback to parsing text formats: bullet points, numbered lists, plain text
    sectors = []
    lines = sector_report.split("\n")
    for line in lines:
        line_clean = line.strip()
        # Regex to match list formats: e.g., "- Technology:", "1. Energy -", "* Healthcare:"
        match = re.match(r'^(?:-|\*|\d+\.)?\s*([a-zA-Z\s]+?)\s*[:\-]', line_clean)
        if match:
            sector_name = match.group(1).strip().lower()
            key = _DISPLAY_TO_KEY.get(sector_name)
            if key and key not in sectors:
                sectors.append(key)
                if len(sectors) == top_n:
                    return sectors

    # Final fallback for plain text search
    if not sectors:
        report_lower = sector_report.lower()

        found_sectors = []
        for disp_name, key in _DISPLAY_TO_KEY.items():
            idx = report_lower.find(disp_name)
            if idx != -1:
                found_sectors.append((idx, key))

        # Sort by appearance order
        found_sectors.sort(key=lambda x: x[0])
        for _, key in found_sectors:
            if key not in sectors:
                sectors.append(key)
                if len(sectors) == top_n:
                    return sectors

    if sectors:
        return sectors[:top_n]

    return VALID_SECTOR_KEYS[:top_n]


def create_industry_deep_dive(llm):
    def industry_deep_dive_node(state):
        scan_date = state["scan_date"]

        tools = [get_industry_performance, get_topic_news]

        sector_report = state.get("sector_performance_report", "")
        top_sectors = _extract_top_sectors(sector_report, top_n=3)
        sector_list_str = ", ".join(top_sectors)

        # Inject Phase 1 summaries for token efficiency
        phase1_context = f"""## Phase 1 Summaries
- Geopolitical: {state.get("geopolitical_summary", "N/A")}
- Market Movers: {state.get("market_movers_summary", "N/A")}
- Sector Analysis: {state.get("sector_summary", "N/A")}
- Factor Alignment: {state.get("factor_alignment_summary", "N/A")}
- Drift Opportunities: {state.get("drift_opportunities_summary", "N/A")}
- Smart Money: {state.get("smart_money_summary", "N/A")}
"""

        system_message = (
            "You are a Senior Research Analyst and Economist performing an industry deep dive. "
            "Your objective is to drill into high-conviction sectors using clinical, quantitative analysis. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "You MUST call these tools: "
            f"1. get_industry_performance for: {sector_list_str}, "
            "2. get_topic_news for at least 2 specific industry themes. "
            "Report must include: "
            "(1) Industry selection rationale linked to Phase 1 deltas, "
            "(2) Top-tier constituents and recent performance metrics, "
            "(3) Industry-specific catalysts and structural risks, "
            "(4) Macro-Industry cross-reference opportunities. "
            f"{phase1_context}"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=scan_date)

        chain = prompt | llm.bind_tools(tools)
        result = run_tool_loop(chain, state["messages"], tools)

        report = result.content or ""

        return {
            "messages": [result],
            "industry_deep_dive_report": report,
            "sender": "industry_deep_dive",
        }

    return industry_deep_dive_node
