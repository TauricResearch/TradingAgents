from langgraph.graph import MessagesState
from typing_extensions import TypedDict


class InvestDebateState(TypedDict):
    """State for the YES/NO/Timing investment debate."""
    yes_history: str
    no_history: str
    timing_history: str
    history: str
    current_yes_response: str
    current_no_response: str
    current_timing_response: str
    latest_speaker: str
    judge_decision: str
    count: int


class RiskDebateState(TypedDict):
    """State for the Aggressive/Conservative/Neutral risk debate."""
    aggressive_history: str
    conservative_history: str
    neutral_history: str
    history: str
    latest_speaker: str
    current_aggressive_response: str
    current_conservative_response: str
    current_neutral_response: str
    judge_decision: str
    count: int


class AgentState(MessagesState):
    """Main agent state for Polymarket prediction analysis."""
    event_id: str
    event_question: str
    trade_date: str
    sender: str
    odds_report: str
    sentiment_report: str
    news_report: str
    event_report: str
    investment_debate_state: InvestDebateState
    investment_plan: str
    trader_plan: str
    risk_debate_state: RiskDebateState
    final_decision: str
