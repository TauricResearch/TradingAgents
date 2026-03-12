from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Simplified state for swing trading pipeline.

    Flow: Analysts → Trader → Done
    No debate states needed.
    """

    company_of_interest: Annotated[str, "Company/ticker we are analyzing"]
    trade_date: Annotated[str, "Trading date"]
    sender: Annotated[str, "Agent that sent this message"]

    # Analyst reports
    market_report: Annotated[str, "Report from the Market Analyst"]
    news_report: Annotated[str, "Report from the News Analyst"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Analyst"]

    # Screening context (from screener pipeline)
    screening_context: Annotated[str, "Why this stock was flagged by screener"]
    portfolio_context: Annotated[str, "Current portfolio state summary"]

    # Trader output
    trader_decision: Annotated[str, "Trader's final swing decision"]
    swing_order: Annotated[
        str, "Structured order: action, entry, stop_loss, take_profit, size, hold_days"
    ]
