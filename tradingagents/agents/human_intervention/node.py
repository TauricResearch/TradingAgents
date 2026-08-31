"""
Human Intervention Node for LangGraph.

Provides a node that pauses execution and waits for human approval
at critical decision points.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from .manager import (
    InterventionRequest,
    InterventionType,
    get_intervention_manager,
)


def create_human_intervention_node(
    intervention_type: InterventionType,
    agent_name: str = "System",
):
    """Create a human intervention node for the graph."""

    def human_intervention_node(state: dict[str, Any]) -> dict[str, Any]:
        """Pause execution and request human approval."""
        manager = get_intervention_manager()

        # Extract relevant info from state
        asset = state.get("company_of_interest", "Unknown")
        scoring = state.get("scoring")
        veredicto = state.get("veredicto")

        # Create summary based on intervention type
        if intervention_type == InterventionType.TRADE_APPROVAL:
            summary = f"Trade approval required for {asset}"
            details = {
                "final_trade_decision": state.get("final_trade_decision", ""),
                "trader_plan": state.get("trader_investment_plan", ""),
                "investment_plan": state.get("investment_plan", ""),
            }
        elif intervention_type == InterventionType.HEDGE_APPROVAL:
            summary = f"Hedging strategy approval required for {asset}"
            details = {
                "hedging_report": state.get("hedging_report", ""),
                "derivatives_report": state.get("derivatives_report", ""),
            }
        elif intervention_type == InterventionType.ANALYSIS_APPROVAL:
            summary = f"Analysis approval required for {asset}"
            details = {
                "market_report": state.get("market_report", ""),
                "fundamentals_report": state.get("fundamentals_report", ""),
                "sentiment_report": state.get("sentiment_report", ""),
                "news_report": state.get("news_report", ""),
            }
        else:
            summary = f"Approval required for {asset}"
            details = {}

        # Create intervention request
        request = manager.create_request(
            intervention_type=intervention_type,
            agent_name=agent_name,
            asset=asset,
            summary=summary,
            details=details,
            scoring=scoring,
            veredicto=veredicto,
        )

        # Create approval message for the user
        approval_message = _format_approval_request(request)

        # Add to messages
        messages = state.get("messages", [])
        messages.append(AIMessage(content=approval_message))

        return {
            "messages": messages,
            "intervention_request": request,
            "pending_approval": True,
        }

    return human_intervention_node


def _format_approval_request(request: InterventionRequest) -> str:
    """Format an intervention request for human display."""
    lines = [
        "## 🚨 HUMAN APPROVAL REQUIRED",
        "",
        f"**Request ID**: {request.request_id}",
        f"**Type**: {request.intervention_type.value}",
        f"**Asset**: {request.asset}",
        f"**Agent**: {request.agent_name}",
        f"**Timestamp**: {request.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "### Summary",
        request.summary,
    ]

    if request.scoring is not None:
        lines.append(f"\n**Scoring**: {request.scoring}/100")

    if request.veredicto:
        lines.append(f"**Veredicto**: {request.veredicto}")

    if request.details:
        lines.append("\n### Details")
        for key, value in request.details.items():
            if isinstance(value, str) and len(value) > 500:
                lines.append(f"\n**{key}**:\n{value[:500]}...")
            else:
                lines.append(f"\n**{key}**: {value}")

    lines.extend([
        "",
        "---",
        "",
        "**To respond, use:**",
        f"- `approve {request.request_id}` — Approve the proposal",
        f"- `reject {request.request_id} <reason>` — Reject with reason",
        f"- `adjust {request.request_id} <changes>` — Request adjustments",
        "",
        f"**Expires at**: {request.expires_at.strftime('%Y-%m-%d %H:%M:%S') if request.expires_at else 'Never'}",
    ])

    return "\n".join(lines)


def create_approval_response_handler():
    """Create a handler for processing approval responses."""

    def handle_approval_response(
        state: dict[str, Any],
        command: str,
    ) -> dict[str, Any]:
        """Process an approval response command."""
        manager = get_intervention_manager()

        parts = command.strip().split(maxsplit=2)
        if len(parts) < 2:
            return {"error": "Invalid command format"}

        action = parts[0].lower()
        request_id = parts[1]
        reason = parts[2] if len(parts) > 2 else None

        request = manager.get_request(request_id)
        if not request:
            return {"error": f"Request {request_id} not found"}

        if action == "approve":
            response = InterventionResponse(
                request_id=request_id,
                decision="APPROVE",
                notes=reason,
            )
        elif action == "reject":
            response = InterventionResponse(
                request_id=request_id,
                decision="REJECT",
                notes=reason,
            )
        elif action == "adjust":
            response = InterventionResponse(
                request_id=request_id,
                decision="ADJUST",
                adjustments={"requested_changes": reason},
                notes=reason,
            )
        else:
            return {"error": f"Unknown action: {action}"}

        updated_request = manager.respond(request_id, response)

        # Update state
        messages = state.get("messages", [])
        messages.append(
            HumanMessage(
                content=f"Human response: {action.upper()} for {request.asset}"
            )
        )

        return {
            "messages": messages,
            "intervention_response": updated_request,
            "pending_approval": False,
            "approval_decision": action.upper(),
        }

    return handle_approval_response
