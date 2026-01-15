from typing import Annotated, Sequence
from datetime import date, timedelta, datetime
from typing_extensions import TypedDict, Optional
from typing import Annotated, Dict, Any, Literal, Sequence, Union
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, StateGraph, START, MessagesState


from typing import Dict, List, Any
from types import MappingProxyType
import hashlib
from enum import Enum

# --- STRUCTS (Phase 2) ---
class TraderDecision(TypedDict):
    """The raw proposal from the Trader LLM (Before Gating)."""
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float # 0.0 to 1.0
    rationale: str

class FinalDecision(TypedDict):
    """The Enforced Decision (After Gating)."""
    status: "ExecutionResult"
    action: Literal["BUY", "SELL", "HOLD", "NO_OP"]
    confidence: float
    details: Optional[Dict[str, Any]]

# Researcher team state
class PortfolioPosition(TypedDict):
    ticker: str
    shares: int
    average_cost: float
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    entry_date: str

class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]  # Bullish Conversation history
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]  # Bullish Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    current_response: Annotated[str, "Latest response"]  # Last response
    judge_decision: Annotated[str, "Final judge decision"]  # Last response
    count: Annotated[int, "Length of the current conversation"]  # Conversation length
    # Enhanced Logic Fields
    last_argument_invalid: Annotated[bool, "Was the last argument rejected?"]
    rejection_reason: Annotated[str, "Reason for rejection"]
    latest_speaker: Annotated[str, "Who spoke last (Bull/Bear)"]
    confidence: Annotated[float, "Confidence in current position (0-1)"]


# Risk management team state
class RiskDebateState(TypedDict):
    risky_history: Annotated[
        str, "Risky Agent's Conversation history"
    ]  # Conversation history
    safe_history: Annotated[
        str, "Safe Agent's Conversation history"
    ]  # Conversation history
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_risky_response: Annotated[
        str, "Latest response by the risky analyst"
    ]  # Last response
    current_safe_response: Annotated[
        str, "Latest response by the safe analyst"
    ]  # Last response
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]  # Last response
    judge_decision: Annotated[str, "Judge's decision"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length
    # Enhanced Logic Fields
    invalid_reasoning_detected: Annotated[bool, "Was invalid reasoning detected?"]
    error_message: Annotated[str, "Error message for invalid reasoning"]


def reduce_overwrite(left, right):
    """
    Reducer that allows overwriting the value.
    In case of concurrent identical updates (like parallel subgraphs returning inputs),
    this resolves the conflict by taking the last value (which is identical).
    """
    return right

# 1. Define a specific reducer for the Risk Debate Dictionary
def merge_risk_states(left: dict, right: dict) -> dict:
    """Safely merges updates from parallel risk analysts."""
    if not left: return right
    if not right: return left
    return {**left, **right}


def write_once_enforce(current: Any, new: Any) -> Any:
    """
    STRICT IMMUTABILITY GUARD.
    1. Blocks overwriting if ledger already exists.
    2. Wraps the new ledger in MappingProxyType to prevent in-place mutation.
    """
    # Guard against overwriting
    if current is not None and current != {}:
        if isinstance(current, dict) and "ledger_id" in current:
             raise RuntimeError("CRITICAL: FactLedger mutation detected. The Ledger is immutable.")
        # Handle the MappingProxyType case (if checking existing state)
        if isinstance(current, MappingProxyType) and "ledger_id" in current:
             raise RuntimeError("CRITICAL: FactLedger mutation detected. The Ledger is immutable.")

    # FIX: Return a Read-Only Proxy
    # This prevents state['fact_ledger']['price_data'] = "hack"
    return MappingProxyType(new)


# --- ENUMS (Machine Readable Logs) ---
class ExecutionResult(str, Enum):
    APPROVED = "APPROVED"
    ABORT_COMPLIANCE = "ABORT_COMPLIANCE"
    ABORT_DATA_GAP = "ABORT_DATA_GAP"
    ABORT_LOW_CONFIDENCE = "ABORT_LOW_CONFIDENCE"
    ABORT_DIVERGENCE = "ABORT_DIVERGENCE"
    ABORT_STALE_DATA = "ABORT_STALE_DATA" # Temporal drift > 3%
    BLOCKED_TREND = "BLOCKED_TREND" 

# --- FACT LEDGER (The Single Source of Truth) ---
class DataFreshness(TypedDict):
    price_age_sec: float
    fundamentals_age_hours: float
    news_age_hours: float

class Technicals(TypedDict):
    current_price: float  # Frozen price at start of run
    sma_200: float
    sma_50: float
    rsi_14: Optional[float]
    revenue_growth: float # For Rule 72 checks

class FactLedger(TypedDict):
    """
    The Single Source of Truth.
    Cryptographically hashed. Immutable.
    """
    ledger_id: str              # UUID4
    created_at: str             # ISO8601 UTC
    
    # Audit: Freshness Constraints
    freshness: DataFreshness
    
    # Version Control
    source_versions: Dict[str, str]  
    
    # The Actual Data
    price_data: Union[str, Dict[str, Any]]       
    fundamental_data: Union[str, Dict[str, Any]] 
    news_data: Union[str, Dict[str, Any]]        
    insider_data: Union[str, Dict[str, Any]]
    net_insider_flow_usd: Optional[float] # Phase 2.7

    # --- Epistemic Lock (Phase 2.5) ---
    regime: str                 # Frozen Regime (e.g. BULL, VOLATILE)
    technicals: Technicals      # Frozen Indicators (SMA, RSI)
    
    # Integrity Check (Payload Hash)
    content_hash: str

class AgentState(MessagesState):
    # --- CORE INFRASTRUCTURE ---
    # This field is now protected by write_once_enforce AND MappingProxyType
    fact_ledger: Annotated[FactLedger, write_once_enforce]
    
    # EXECUTION DATA (New Phase 2)
    trader_decision: Annotated[TraderDecision, reduce_overwrite] 
    final_trade_decision: Annotated[FinalDecision, reduce_overwrite]
    
    company_of_interest: Annotated[str, reduce_overwrite] # "Company that we are interested in trading"
    trade_date: Annotated[str, reduce_overwrite] # "What date we are trading at"


    sender: Annotated[str, "Agent that sent this message"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    news_report: Annotated[
        str, "Report from the News Researcher of current world affairs"
    ]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]
    
    # regime data
    # regime data
    market_regime: Annotated[str, "Current Market Regime (e.g. VOLATILE, TRENDING_UP)"]
    broad_market_regime: Annotated[str, "Broad Market Context (e.g. SPY Regime)"]
    regime_metrics: Annotated[dict, "Metrics used to determine regime"]
    volatility_score: Annotated[float, "Current Volatility Score"]
    net_insider_flow: Annotated[float, "Net Insider Transaction Flow (Last 90 Days)"]
    portfolio: Annotated[Dict[str, PortfolioPosition], "Current active holdings"]
    cash_balance: Annotated[float, "Current cash balance"]
    risk_multiplier: Annotated[float, "Calculated Risk Multiplier based on Relative Strength"]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]

    trader_investment_plan: Annotated[str, "Plan generated by the Trader"]
    
    # Gatekeeper Inputs (V2 Phase 2 Requirement)
    bull_confidence: Annotated[float, reduce_overwrite]
    bear_confidence: Annotated[float, reduce_overwrite]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, merge_risk_states
    ]
    # final_trade_decision replaced by typed version above
    # final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]

# --- STRICT ANALYST STATES FOR SUBGRAPHS ---
# These ensure parallel analysts cannot touch global state (portfolio, risk, etc.)

class BaseAnalystState(MessagesState):
    """Base state for an isolated analyst subgraph.
    Inherits 'messages' from MessagesState.
    """
    company_of_interest: Annotated[str, reduce_overwrite]
    trade_date: Annotated[str, reduce_overwrite]
    sender: Annotated[str, "Agent name (internal to subgraph)"]

class SocialAnalystState(BaseAnalystState):
    sentiment_report: Annotated[str, "Output report"]

class NewsAnalystState(BaseAnalystState):
    news_report: Annotated[str, "Output report"]
    # Additional news-specific fields if needed, but keeping it minimal

class FundamentalsAnalystState(BaseAnalystState):
    fundamentals_report: Annotated[str, "Output report"]
