from __future__ import annotations

import pytest

from tradingagents.dashboard.extract import build_analysis_record


@pytest.fixture()
def sample_final_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2024-05-10",
        "market_report": "FINAL TRANSACTION PROPOSAL: **BUY**\nMomentum recovered and trend structure improved.",
        "sentiment_report": "FINAL TRANSACTION PROPOSAL: **HOLD**\nNo strong fresh catalyst from social/news sources.",
        "news_report": "# NVDA Weekly Macro & Trading News Report\nAI enthusiasm remains intact but valuation scrutiny is rising.",
        "fundamentals_report": "# NVDA Fundamental Report\nMargins and free cash flow remain exceptional.",
        "investment_debate_state": {
            "bull_history": "Bull case: growth and margins remain elite.",
            "bear_history": "Bear case: valuation leaves little room for disappointment.",
            "judge_decision": "**Recommendation**: Hold\n\n**Rationale**: Balanced setup.\n\n**Strategic Actions**: Maintain exposure.",
        },
        "trader_investment_decision": "**Action**: Hold\n\n**Reasoning**: Preserve exposure while avoiding aggressive adds.\n\nFINAL TRANSACTION PROPOSAL: **HOLD**",
        "risk_debate_state": {
            "aggressive_history": "Aggressive analyst: add on recovery.",
            "conservative_history": "Conservative analyst: do not chase valuation.",
            "neutral_history": "Neutral analyst: maintain current weight.",
            "judge_decision": "**Rating**: Hold\n\n**Executive Summary**: Maintain the current NVDA position near benchmark weight and do not chase strength.\n\n**Investment Thesis**: Fundamentals are strong, but valuation and AI-capex dependence argue for caution.\n\n**Time Horizon**: 3-6 months",
        },
        "investment_plan": "**Recommendation**: Hold\n\n**Rationale**: The setup is balanced.\n\n**Strategic Actions**: Maintain exposure and reassess on pullbacks.",
        "final_trade_decision": "**Rating**: Hold\n\n**Executive Summary**: Maintain the current NVDA position near benchmark weight and do not chase strength.\n\n**Investment Thesis**: Fundamentals are strong, but valuation and AI-capex dependence argue for caution.\n\n**Time Horizon**: 3-6 months",
    }


@pytest.fixture()
def sample_record(sample_final_state):
    return build_analysis_record(
        sample_final_state,
        generated_at="2026-04-29T23:00:00+00:00",
        raw_log_path="artifacts/dashboard/raw_results/NVDA/TradingAgentsStrategy_logs/full_states_log_2024-05-10.json",
    )
