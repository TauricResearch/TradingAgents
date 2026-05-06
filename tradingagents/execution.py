"""Broker-neutral execution models and dry-run executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, Sequence


ExecutionAction = Literal["buy", "sell"]
ExecutionStatus = Literal["planned"]


@dataclass(frozen=True)
class ExecutionOrder:
    ticker: str
    action: ExecutionAction
    quantity: float

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero.")
        if not self.ticker.strip():
            raise ValueError("ticker is required.")


@dataclass(frozen=True)
class ExecutionResult:
    order: ExecutionOrder
    status: ExecutionStatus
    message: str | None = None


class ExecutorProtocol(Protocol):
    def execute(self, orders: Sequence[ExecutionOrder]) -> list[ExecutionResult]:
        """Execute or plan orders and return broker-neutral results."""


@dataclass
class DryRunExecutor:
    submitted_orders: list[ExecutionOrder] = field(default_factory=list)

    def execute(self, orders: Sequence[ExecutionOrder]) -> list[ExecutionResult]:
        return [
            ExecutionResult(order=order, status="planned", message="dry run")
            for order in orders
        ]


def execute_orders(
    orders: Sequence[ExecutionOrder],
    *,
    dry_run: bool,
    executor: ExecutorProtocol | None = None,
) -> list[ExecutionResult]:
    if dry_run:
        return DryRunExecutor().execute(orders)
    if executor is None:
        raise ValueError("executor is required when dry_run is False.")
    return executor.execute(orders)
