"""
Chain Strategy Models.

Defines the data models for chained multi-market investment strategies.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChainStepStatus(str, Enum):
    """Status of a chain step."""
    PENDING = "pending"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChainStep(BaseModel):
    """A single step in a chained investment strategy."""

    step_id: int = Field(description="Step number (1-based)")
    name: str = Field(description="Step name (e.g., 'Buy Oil ETF')")
    description: str = Field(description="What this step does")

    # Market & Instrument
    market: str = Field(description="Market (CRYPTO, US, AR, etc.)")
    provider: str = Field(description="Execution provider (ccxt, lumibot, byma)")
    symbol: str = Field(description="Trading symbol")
    action: str = Field(description="BUY or SELL")
    quantity: float | None = Field(default=None, description="Quantity to trade")
    notional: float | None = Field(default=None, description="Notional value (if quantity not specified)")
    order_type: str = Field(default="market", description="Order type (market, limit)")
    limit_price: float | None = Field(default=None, description="Limit price (if limit order)")

    # Conditions
    trigger_condition: str | None = Field(
        default=None,
        description="Condition to trigger this step (e.g., 'price > 100', 'signal_from_previous')"
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="Step IDs this step depends on"
    )

    # Status
    status: ChainStepStatus = Field(default=ChainStepStatus.PENDING)
    actual_price: float | None = Field(default=None, description="Actual execution price")
    actual_quantity: float | None = Field(default=None, description="Actual quantity executed")
    execution_time: datetime | None = Field(default=None, description="When this step was executed")
    error: str | None = Field(default=None, description="Error message if failed")

    # Risk
    stop_loss: float | None = Field(default=None, description="Stop loss price")
    take_profit: float | None = Field(default=None, description="Take profit price")
    max_loss: float | None = Field(default=None, description="Maximum loss for this step")


class ChainStrategy(BaseModel):
    """A complete chained investment strategy across multiple markets."""

    chain_id: str = Field(description="Unique chain identifier")
    name: str = Field(description="Chain strategy name")
    description: str = Field(description="What this chain does")
    created_at: datetime = Field(default_factory=datetime.now)

    # Steps
    steps: list[ChainStep] = Field(description="Ordered list of steps")

    # Context
    trigger_event: str = Field(description="What triggered this chain (e.g., 'geopolitical tension')")
    correlations: dict[str, float] = Field(
        default_factory=dict,
        description="Correlations between assets (e.g., {'oil_transport': -0.85})"
    )

    # Risk
    total_notional: float = Field(default=0.0, description="Total notional value")
    max_drawdown: float = Field(default=0.0, description="Maximum drawdown")
    risk_reward_ratio: float = Field(default=0.0, description="Risk/Reward ratio")

    # Veredicto
    scoring: int = Field(ge=0, le=100, description="Chain scoring 0-100")
    veredicto: str = Field(description="APPROVE / REJECT / ADJUST")
    reasoning: str = Field(description="Rationale for this chain")

    # Status
    is_active: bool = Field(default=True, description="Whether chain is active")
    current_step: int = Field(default=0, description="Current step index")


class ChainExecutionResult(BaseModel):
    """Result of executing a chain strategy."""

    chain_id: str
    status: str  # "completed", "partial", "failed"
    completed_steps: int
    total_steps: int
    results: list[dict[str, Any]]
    total_pnl: float = 0.0
    execution_time: float = 0.0  # seconds
    errors: list[str] = Field(default_factory=list)
