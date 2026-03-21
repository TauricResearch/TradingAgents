from __future__ import annotations

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
    ranked by absolute 1-month performance (largest absolute move first).

    The sector performance table looks like:

        | Technology | +0.45% | +1.20% | +5.67% | +12.3% |

    We parse the 1-month column (index 3) and sort by absolute value.

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

    if not rows:
        return VALID_SECTOR_KEYS[:top_n]

    # Sort by absolute 1-month move (biggest mover first)
    rows.sort(key=lambda r: abs(r[1]), reverse=True)
    return [r[0] for r in rows[:top_n]]


def create_industry_deep_dive(llm):
    def industry_deep_dive_node(state):
        scan_date = state["scan_date"]

        tools = [get_industry_performance, get_topic_news]

        sector_report = state.get("sector_performance_report", "")
        top_sectors = _extract_top_sectors(sector_report, top_n=3)

        # Inject Phase 1 context so the LLM can decide which sectors to drill into
        phase1_context = f"""## Phase 1 Scanner Reports (for your reference)

### Geopolitical Report:
{state.get("geopolitical_report", "Not available")}

### Market Movers Report:
{state.get("market_movers_report", "Not available")}

### Sector Performance Report:
{sector_report or "Not available"}
"""

        sector_list_str = ", ".join(f"'{s}'" for s in top_sectors)
        all_keys_str = ", ".join(f"'{s}'" for s in VALID_SECTOR_KEYS)

        system_message = (
            "You are a senior research analyst performing an industry deep dive.\n\n"
            "## Your task\n"
            "Based on the Phase 1 reports below, drill into the most interesting sectors "
            "using the tools provided and write a detailed analysis.\n\n"
            "## IMPORTANT — You MUST call tools before writing your report\n"
            f"1. Call get_industry_performance for EACH of these top sectors: {sector_list_str}\n"
            "2. Call get_topic_news for at least 2 sector-specific topics "
            "(e.g., 'semiconductor industry', 'renewable energy stocks').\n"
            "3. After receiving tool results, write your detailed report.\n\n"
            f"Valid sector_key values for get_industry_performance: {all_keys_str}\n\n"
            "## Report structure\n"
            "(1) Why these industries were selected (link to Phase 1 findings)\n"
            "(2) Top companies within each industry and their recent performance\n"
            "(3) Industry-specific catalysts and risks\n"
            "(4) Cross-references between geopolitical events and sector opportunities\n\n"
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
