from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.critical_abort import extract_abort_report
from tradingagents.constants import CRITICAL_ABORT_NODE


def create_critical_abort_terminal() -> Callable[[AgentState], dict[str, Any]]:
    def critical_abort_terminal_node(state: AgentState, /) -> dict[str, Any]:
        context = str(state.get("portfolio_context") or "candidate").strip().lower()
        is_holding = context == "holding"
        terminal_action = "SELL" if is_holding else "AVOID"
        source_field, abort_report = extract_abort_report(
            state, "market_report", "news_report", "fundamentals_report"
        )
        source_label = source_field.replace("_", " ") if source_field else "analyst report"
        instrument_context = build_instrument_context(state["company_of_interest"])

        decision_text = (
            "Rating: Sell\n\n"
            f"Terminal Action: {terminal_action}\n\n"
            f"Executive Summary: Critical abort triggered from the {source_label}. "
            + (
                "Exit the existing position immediately and do not wait for trader or risk debate output."
                if is_holding
                else "Reject the candidate and do not open a position."
            )
            + "\n\n"
            "Investment Thesis: The normal debate, trader, and portfolio-manager path was intentionally skipped. "
            "This ticker hit a hard-stop condition that must be preserved as a first-class terminal outcome.\n\n"
            f"Instrument Context: {instrument_context}\n\n"
            f"Aborting Report:\n{abort_report or 'No abort report captured.'}"
        )

        risk_debate_state = state.get("risk_debate_state", {})
        new_risk_debate_state = {
            "judge_decision": decision_text,
            "history": risk_debate_state.get("history", ""),
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": CRITICAL_ABORT_NODE,
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get(
                "current_conservative_response", ""
            ),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state.get("count", 0),
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": decision_text,
            "analysis_status": "aborted",
            "terminal_action": terminal_action,
            "critical_abort_reason": abort_report,
            "sender": CRITICAL_ABORT_NODE,
        }

    return critical_abort_terminal_node
