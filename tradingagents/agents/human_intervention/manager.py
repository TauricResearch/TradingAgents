"""
Human Intervention System.

Provides approval workflow at critical decision points in the
investment committee pipeline. Supports both analysis and execution modes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class InterventionType(str, Enum):
    """Types of human intervention required."""

    ANALYSIS_APPROVAL = "analysis_approval"        # Approve analysis results
    TRADE_APPROVAL = "trade_approval"              # Approve trade execution
    HEDGE_APPROVAL = "hedging_approval"            # Approve hedging strategy
    CHAIN_APPROVAL = "chain_approval"              # Approve chained investment
    RISK_OVERRIDE = "risk_override"                # Override risk limits
    STRATEGY_CHANGE = "strategy_change"            # Change strategy mid-execution


class InterventionStatus(str, Enum):
    """Status of an intervention request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class InterventionRequest(BaseModel):
    """A request for human intervention."""

    request_id: str = Field(
        description="Unique identifier for this intervention request"
    )
    intervention_type: InterventionType = Field(
        description="Type of intervention required"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the request was created"
    )
    agent_name: str = Field(
        description="Name of the agent requesting intervention"
    )
    asset: str = Field(
        description="Asset or instrument being analyzed/traded"
    )
    summary: str = Field(
        description="Brief summary of what needs approval"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed information for decision-making"
    )
    scoring: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Agent's scoring 0-100"
    )
    veredicto: str | None = Field(
        default=None,
        description="Agent's recommendation (COMPRAR/MANTENER/VENDER/NO_OPERAR)"
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When this request expires"
    )
    status: InterventionStatus = Field(
        default=InterventionStatus.PENDING,
        description="Current status of the request"
    )
    human_response: str | None = Field(
        default=None,
        description="Human's response/decision"
    )
    human_timestamp: datetime | None = Field(
        default=None,
        description="When the human responded"
    )


class InterventionResponse(BaseModel):
    """Human's response to an intervention request."""

    request_id: str = Field(
        description="ID of the request being responded to"
    )
    decision: str = Field(
        description="APPROVE, REJECT, or ADJUST"
    )
    adjustments: dict[str, Any] = Field(
        default_factory=dict,
        description="Any adjustments to the proposal"
    )
    notes: str | None = Field(
        default=None,
        description="Human notes or comments"
    )


class HumanInterventionManager:
    """Manages human intervention requests and responses."""

    def __init__(self):
        self._pending_requests: dict[str, InterventionRequest] = {}
        self._completed_requests: dict[str, InterventionRequest] = {}

    def create_request(
        self,
        intervention_type: InterventionType,
        agent_name: str,
        asset: str,
        summary: str,
        details: dict[str, Any] | None = None,
        scoring: int | None = None,
        veredicto: str | None = None,
        expiry_hours: int = 24,
    ) -> InterventionRequest:
        """Create a new intervention request."""
        import uuid

        request = InterventionRequest(
            request_id=str(uuid.uuid4()),
            intervention_type=intervention_type,
            agent_name=agent_name,
            asset=asset,
            summary=summary,
            details=details or {},
            scoring=scoring,
            veredicto=veredicto,
            expires_at=datetime.now().timestamp() + (expiry_hours * 3600),
        )

        self._pending_requests[request.request_id] = request
        return request

    def get_request(self, request_id: str) -> Optional[InterventionRequest]:
        """Get a request by ID."""
        return self._pending_requests.get(request_id) or self._completed_requests.get(request_id)

    def list_pending(self) -> list[InterventionRequest]:
        """List all pending requests."""
        return list(self._pending_requests.values())

    def respond(
        self,
        request_id: str,
        response: InterventionResponse,
    ) -> InterventionRequest:
        """Respond to an intervention request."""
        request = self._pending_requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found or already completed")

        request.status = (
            InterventionStatus.APPROVED
            if response.decision.upper() == "APPROVE"
            else InterventionStatus.REJECTED
        )
        request.human_response = response.decision
        request.human_timestamp = datetime.now()
        request.details["human_adjustments"] = response.adjustments
        request.details["human_notes"] = response.notes

        # Move to completed
        self._completed_requests[request_id] = request
        del self._pending_requests[request_id]

        return request

    def cancel_request(self, request_id: str) -> InterventionRequest:
        """Cancel a pending request."""
        request = self._pending_requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        request.status = InterventionStatus.CANCELLED
        self._completed_requests[request_id] = request
        del self._pending_requests[request_id]

        return request

    def check_expired(self) -> list[InterventionRequest]:
        """Check for and expire any overdue requests."""
        now = datetime.now()
        expired = []

        for request_id, request in list(self._pending_requests.items()):
            if request.expires_at and now > request.expires_at:
                request.status = InterventionStatus.EXPIRED
                self._completed_requests[request_id] = request
                del self._pending_requests[request_id]
                expired.append(request)

        return expired


# Global instance
_intervention_manager: Optional[HumanInterventionManager] = None


def get_intervention_manager() -> HumanInterventionManager:
    """Get the global intervention manager."""
    global _intervention_manager
    if _intervention_manager is None:
        _intervention_manager = HumanInterventionManager()
    return _intervention_manager
