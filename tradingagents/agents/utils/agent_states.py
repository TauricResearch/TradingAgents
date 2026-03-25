from typing import Annotated, Any, Sequence
from datetime import date, timedelta, datetime
from typing_extensions import TypedDict, Optional
from langchain_openai import ChatOpenAI
from tradingagents.agents import *
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, StateGraph, START, MessagesState


# Researcher team state
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


# Risk management team state
class RiskDebateState(TypedDict):
    aggressive_history: Annotated[
        str, "Aggressive Agent's Conversation history"
    ]  # Conversation history
    conservative_history: Annotated[
        str, "Conservative Agent's Conversation history"
    ]  # Conversation history
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[
        str, "Latest response by the aggressive analyst"
    ]  # Last response
    current_conservative_response: Annotated[
        str, "Latest response by the conservative analyst"
    ]  # Last response
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]  # Last response
    judge_decision: Annotated[str, "Judge's decision"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


class FairValueRange(TypedDict):
    low: Optional[float]
    high: Optional[float]


class ValuationData(TypedDict):
    fair_value_range: FairValueRange
    expected_return_pct: Optional[float]
    primary_method: str
    thesis: str


class SegmentData(TypedDict):
    ticker: str
    analysis_date: str
    business_unit_decomposition: list[dict[str, Any]]
    segment_economics: dict[str, Any]
    value_driver_map: list[dict[str, Any]]


class ScenarioCaseData(TypedDict):
    probability: Optional[float]
    price_target: Optional[float]
    thesis: str


class ScenarioCatalystData(TypedDict):
    ticker: str
    analysis_date: str
    scenario_map: list[dict[str, Any]]
    dated_catalyst_map: list[dict[str, Any]]
    invalidation_triggers: list[dict[str, Any]]


class PositionSizingData(TypedDict):
    conviction: str
    target_weight_pct: Optional[float]
    initial_weight_pct: Optional[float]
    max_loss_pct: Optional[float]


class ChiefAnalystData(TypedDict):
    action: str
    summary: str
    thesis: str
    confidence: str


def make_default_valuation_data() -> ValuationData:
    return {
        "fair_value_range": {"low": None, "high": None},
        "expected_return_pct": None,
        "primary_method": "",
        "thesis": "",
    }


def make_default_segment_data() -> SegmentData:
    return {
        "ticker": "",
        "analysis_date": "",
        "business_unit_decomposition": [],
        "segment_economics": {},
        "value_driver_map": [],
    }


def make_default_scenario_case_data() -> ScenarioCaseData:
    return {
        "probability": None,
        "price_target": None,
        "thesis": "",
    }


def make_default_scenario_catalyst_data() -> ScenarioCatalystData:
    return {
        "ticker": "",
        "analysis_date": "",
        "scenario_map": [],
        "dated_catalyst_map": [],
        "invalidation_triggers": [],
    }


def make_default_position_sizing_data() -> PositionSizingData:
    return {
        "conviction": "",
        "target_weight_pct": None,
        "initial_weight_pct": None,
        "max_loss_pct": None,
    }


def make_default_chief_analyst_data() -> ChiefAnalystData:
    return {
        "action": "",
        "summary": "",
        "thesis": "",
        "confidence": "",
    }


def make_default_structured_stock_underwriting_state() -> dict[str, Any]:
    return {
        "valuation_data": make_default_valuation_data(),
        "segment_data": make_default_segment_data(),
        "scenario_catalyst_data": make_default_scenario_catalyst_data(),
        "position_sizing_data": make_default_position_sizing_data(),
        "chief_analyst_data": make_default_chief_analyst_data(),
    }


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    trade_date: Annotated[str, "What date we are trading at"]

    sender: Annotated[str, "Agent that sent this message"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    news_report: Annotated[
        str, "Report from the News Researcher of current world affairs"
    ]
    macro_report: Annotated[str, "Report from the Macro Analyst"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]
    factor_rules_report: Annotated[
        str, "Summary from the optional factor rule analyst"
    ]
    segment_report: Annotated[str, "Report from the Segment Analyst"]
    scenario_catalyst_report: Annotated[
        str,
        "Report from the Scenario and Catalyst Analyst",
    ]
    valuation_data: Annotated[
        ValuationData, "Structured valuation underwriting output"
    ]
    segment_data: Annotated[
        SegmentData, "Structured segment underwriting output"
    ]
    scenario_catalyst_data: Annotated[
        ScenarioCatalystData, "Structured scenario and catalyst underwriting output"
    ]
    position_sizing_data: Annotated[
        PositionSizingData, "Structured position sizing underwriting output"
    ]
    chief_analyst_data: Annotated[
        ChiefAnalystData, "Structured chief analyst summary output"
    ]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]

    trader_investment_plan: Annotated[str, "Plan generated by the Trader"]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]
