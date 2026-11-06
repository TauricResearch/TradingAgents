from typing import Annotated

from langgraph.graph import MessagesState
from typing_extensions import TypedDict

from tradingagents.agents.schemas import FactorExtraction


# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]
    history: Annotated[str, "Conversation history"]
    current_response: Annotated[str, "Latest response"]
    count: Annotated[int, "Length of the current conversation"]


# Risk management team state
class RiskDebateState(TypedDict):
    aggressive_history: Annotated[
        str, "Aggressive Agent's Conversation history"
    ]
    conservative_history: Annotated[
        str, "Conservative Agent's Conversation history"
    ]
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]
    history: Annotated[str, "Conversation history"]
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[
        str, "Latest response by the aggressive analyst"
    ]
    current_conservative_response: Annotated[
        str, "Latest response by the conservative analyst"
    ]
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]
    count: Annotated[int, "Length of the current conversation"]


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    asset_type: Annotated[str, "Asset type under analysis such as stock, crypto, or commodity"]
    instrument_context: Annotated[str, "Deterministic ticker identity resolved at run start"]
    trade_date: Annotated[str, "The analysis date; data is served as of it"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Sentiment Analyst"]
    news_report: Annotated[str, "Report from the News Analyst on company and world news"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Analyst"]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Investment plan from the Research Manager"]

    # decision_mode="structured" only: factors extracted from the analyst
    # reports by factor_extractor.py, scored deterministically by
    # decision_model.py into investment_plan above. Not present in "debate"
    # or "off" mode runs.
    extracted_factors: Annotated[
        FactorExtraction | None, "Structured factors extracted for the deterministic scorer"
    ]

    # The scorer's own outputs, kept as data alongside the prose it renders
    # into investment_plan. Threshold calibration (#19 step 4) needs the number
    # and which gate fired; the Trader's write-up only sometimes restates the
    # score, so deriving them from prose afterwards does not work.
    structured_rating: Annotated[str | None, "Rating decision_model.py assigned"]
    structured_score: Annotated[
        float | None, "Combined confidence-weighted score, post risk-flag damping"
    ]
    structured_reason: Annotated[
        str | None, "Which gate fired, or the score breakdown that set the rating"
    ]

    trader_investment_plan: Annotated[str, "Transaction proposal from the Trader"]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    final_trade_decision: Annotated[str, "Final decision from the Portfolio Manager"]
    final_rating: Annotated[str, "The Portfolio Manager's 5-tier rating, or REVIEW when it has none"]
    past_context: Annotated[str, "Memory log context for the Portfolio Manager (same-ticker decisions + cross-ticker lessons), written by the Memory Log step"]
    memory_note: Annotated[str, "What the Memory Log step could not settle or read this run, for the report; empty when all went well"]
    portfolio_context: Annotated[str, "Caller-supplied holdings and cash, rendered at run start; empty when not provided"]
    external_signal_context: Annotated[str, "Prior signal from an external scanner injected at run start (trading-workspace#37) — informational, not authoritative"]
    external_signal_direction: Annotated[str, "'up' / 'down' / '' -- explicit direction of the external signal (TradingAgents#30); a prior the Trader/PM must justify contradicting, and a signed prior in decision_model.py"]
