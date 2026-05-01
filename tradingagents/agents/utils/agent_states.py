from typing import Annotated, Any, Literal

from langgraph.graph import MessagesState
from typing_extensions import TypedDict


# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[str, "Bullish Conversation history"]  # Bullish Conversation history
    bear_history: Annotated[str, "Bearish Conversation history"]  # Bearish Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    summary: Annotated[str, "Rolling compressed summary of the debate"]
    current_response: Annotated[str, "Latest response"]  # Last response
    current_bull_summary: Annotated[str, "Latest compressed bull researcher summary"]
    current_bear_summary: Annotated[str, "Latest compressed bear researcher summary"]
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
    neutral_history: Annotated[str, "Neutral Agent's Conversation history"]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    summary: Annotated[str, "Rolling compressed summary of the risk debate"]
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


AbortReason = Literal[
    "instrument_key_invalid",
    "news_prefetch_failed",
    "news_evidence_missing",
    "news_schema_invalid",
    "fundamentals_empty_ttm",
    "social_prefetch_failed",
    "market_data_unavailable",
]


class AbortSignal(TypedDict):
    source: Annotated[str, "Node name that raised the abort"]
    reason: Annotated[AbortReason, "Machine-readable abort reason code"]
    detail: Annotated[str, "Human-readable abort diagnosis"]
    raised_at: Annotated[str, "UTC ISO-8601 timestamp when the abort was raised"]
    recoverable: Annotated[bool, "Whether a partial rerun could fix the abort"]


class AgentState(MessagesState):
    run_id: Annotated[str, "Canonical run identifier for traceability across persisted artifacts"]
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    trade_date: Annotated[str, "What date we are trading at"]
    portfolio_context: Annotated[
        str, "Whether the ticker is being evaluated as a holding or a candidate"
    ]
    instrument_key: Annotated[str, "Canonical instrument identity key"]
    asset_class: Annotated[str, "Canonical asset class"]
    instrument_type: Annotated[str, "Canonical instrument type"]
    is_etf: Annotated[bool, "Whether the instrument is an ETF"]
    is_inverse: Annotated[bool, "Whether the instrument is inverse"]
    is_leveraged: Annotated[bool, "Whether the instrument is leveraged"]

    scanner_context_packet: Annotated[str, "Consolidated context from the scanner phase"]
    scanner_graph_context_text: Annotated[
        str, "Prompt-ready ticker graph context rendered from scanner graph facts"
    ]

    sender: Annotated[str, "Agent that sent this message"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    market_report_structured: Annotated[
        dict[str, Any], "Compact canonical market contract for downstream machine consumers"
    ]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    sentiment_report_structured: Annotated[
        dict[str, Any], "Compact canonical sentiment contract for downstream machine consumers"
    ]
    news_report: Annotated[str, "Report from the News Researcher of current world affairs"]
    news_report_structured: Annotated[
        dict[str, Any], "Structured news claims before and after fact-check pruning"
    ]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]
    fundamentals_report_structured: Annotated[
        dict[str, Any], "Structured fundamentals contract for downstream machine consumers"
    ]
    research_packet_summary: Annotated[
        str, "Compressed cross-analyst briefing for downstream debate and risk nodes"
    ]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]
    investment_plan_structured: Annotated[
        dict[str, Any],
        "Compact canonical research-manager contract for downstream machine consumers",
    ]
    rm_consistency_status: Annotated[
        str, "Research-manager numeric consistency guard status"
    ]
    rm_consistency_flags: Annotated[
        list[dict[str, Any]], "Flag-only numeric claims found by the RM consistency guard"
    ]
    consistency_violations: Annotated[
        list[dict[str, Any]],
        "Numeric consistency violations for corrective research-manager re-prompt",
    ]
    _rm_consistency_attempt: Annotated[
        int, "Number of corrective RM consistency guard attempts already requested"
    ]

    trader_investment_plan: Annotated[str, "Plan generated by the Trader"]
    trader_plan_structured: Annotated[
        dict[str, Any], "Compact canonical trader contract for downstream machine consumers"
    ]

    # risk management team discussion step
    risk_debate_state: Annotated[RiskDebateState, "Current state of the debate on evaluating risk"]

    # Parallel risk debate round responses
    risk_r1_aggressive: Annotated[str, "Round 1 aggressive analyst position"]
    risk_r1_conservative: Annotated[str, "Round 1 conservative analyst position"]
    risk_r1_neutral: Annotated[str, "Round 1 neutral analyst position"]
    risk_r2_aggressive: Annotated[str, "Round 2 aggressive analyst rebuttal"]
    risk_r2_conservative: Annotated[str, "Round 2 conservative analyst rebuttal"]
    risk_r2_neutral: Annotated[str, "Round 2 neutral analyst rebuttal"]

    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]
    final_trade_decision_structured: Annotated[
        dict[str, Any],
        "Compact canonical portfolio-manager decision for downstream machine consumers",
    ]
    risk_synthesis_structured: Annotated[
        dict[str, Any], "Compact canonical risk synthesis contract for downstream machine consumers"
    ]
    analysis_status: Annotated[str, "Terminal pipeline status"]
    terminal_action: Annotated[str, "Explicit terminal action for abort and completion paths"]
    abort_signal: Annotated[AbortSignal | None, "Structured terminal abort signal"]

    # macro regime
    macro_regime_report: Annotated[
        str, "Macro regime classification (risk-on/risk-off/transition) from market analyst"
    ]
