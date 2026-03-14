# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
import logging
from typing import Optional, List

from .base_broker import BaseBroker
from .models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
    OrderStatus,
    PortfolioSnapshot,
)
from .safety import SafetyGuard

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Orchestrates trade execution with safety checks.

    Sits between the decision pipeline and the broker, enforcing all
    safety rules before any order is placed.
    """

    def __init__(self, broker: BaseBroker, config: dict):
        self.broker = broker
        self.config = config
        self.safety = SafetyGuard(config)

        broker_config = config.get("broker", {})
        self.default_order_type = broker_config.get("default_order_type", "market").upper()
        self.default_quantity = broker_config.get("default_quantity")
        self.default_position_pct = broker_config.get("default_position_pct", 0.05)

        self._daily_pnl: float = 0.0
        self._order_history: List[OrderResult] = []

    def execute_decision(
        self,
        ticker: str,
        decision: str,
        quantity: Optional[int] = None,
    ) -> OrderResult:
        """Convert a BUY/SELL/HOLD decision into an executed order.

        Args:
            ticker: Stock ticker (e.g. "005930")
            decision: "BUY", "SELL", or "HOLD"
            quantity: Number of shares. If None, calculated from portfolio percentage.

        Returns:
            OrderResult with execution details.
        """
        decision = decision.strip().upper()

        # HOLD = no-op
        if decision == "HOLD":
            return OrderResult(
                success=True,
                status=OrderStatus.FILLED,
                message="HOLD decision — no order placed",
            )

        if decision not in ("BUY", "SELL"):
            return OrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                message=f"Invalid decision: {decision}. Expected BUY, SELL, or HOLD.",
            )

        side = OrderSide.BUY if decision == "BUY" else OrderSide.SELL

        # Get current price
        try:
            price = self.broker.get_current_price(ticker)
            if price <= 0:
                return OrderResult(
                    success=False,
                    status=OrderStatus.REJECTED,
                    message=f"Invalid price for {ticker}: {price}",
                )
        except Exception as e:
            return OrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                message=f"Failed to get price for {ticker}: {e}",
            )

        # Calculate quantity if not specified
        if quantity is None:
            quantity = self._calculate_quantity(ticker, side, price)
            if quantity <= 0:
                return OrderResult(
                    success=False,
                    status=OrderStatus.REJECTED,
                    message=f"Calculated quantity is 0 for {ticker} at {price:,.0f} KRW",
                )

        # Get portfolio for safety checks
        try:
            portfolio = self.broker.get_portfolio()
        except Exception:
            portfolio = PortfolioSnapshot(account_no="", balance=None, positions=[])

        # Run safety checks
        order = OrderRequest(
            ticker=ticker,
            side=side,
            quantity=quantity,
            order_type=OrderType[self.default_order_type],
        )

        passed, reason = self.safety.validate_all(
            order, price, portfolio, self._daily_pnl
        )
        if not passed:
            return OrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                message=f"Safety check failed: {reason}",
            )

        # Execute order
        logger.info(
            "Executing %s order: %s %d shares of %s at ~%,.0f KRW",
            "PAPER" if self.broker.is_paper_trading else "REAL",
            side.value,
            quantity,
            ticker,
            price,
        )

        result = self.broker.place_order(order)
        self._order_history.append(result)

        if result.success:
            logger.info("Order executed: %s", result.message)
        else:
            logger.error("Order failed: %s", result.message)

        return result

    def _calculate_quantity(
        self, ticker: str, side: OrderSide, price: float
    ) -> int:
        """Calculate order quantity based on configuration.

        Uses default_quantity if set, otherwise calculates from
        default_position_pct of portfolio.
        """
        if self.default_quantity:
            return self.default_quantity

        try:
            portfolio = self.broker.get_portfolio()
        except Exception as e:
            logger.warning("Cannot get portfolio for quantity calc: %s", e)
            return 0

        if side == OrderSide.SELL:
            # For sells, find how many shares we hold
            for pos in portfolio.positions:
                if pos.ticker == ticker:
                    return pos.quantity
            return 0

        # For buys, use percentage of total equity
        total_equity = portfolio.balance.total_equity
        if total_equity <= 0:
            return 0

        target_amount = total_equity * self.default_position_pct
        quantity = math.floor(target_amount / price)
        return max(quantity, 0)

    def get_portfolio_context(self) -> str:
        """Generate portfolio summary text for agent prompt context."""
        try:
            snapshot = self.broker.get_portfolio()
        except Exception as e:
            return f"Portfolio unavailable: {e}"

        bal = snapshot.balance
        lines = [
            f"Account: {snapshot.account_no} "
            f"({'Paper' if self.broker.is_paper_trading else 'Real'})",
            f"Total Equity: {bal.total_equity:,.0f} KRW",
            f"Cash Balance: {bal.cash_balance:,.0f} KRW",
            f"Buying Power: {bal.buying_power:,.0f} KRW",
            f"Unrealized P&L: {bal.total_unrealized_pnl:+,.0f} KRW",
        ]

        if snapshot.positions:
            lines.append("\nPositions:")
            for p in snapshot.positions:
                pnl_sign = "+" if p.unrealized_pnl >= 0 else ""
                lines.append(
                    f"  {p.name} ({p.ticker}): {p.quantity} shares "
                    f"@ avg {p.avg_cost:,.0f} KRW, "
                    f"current {p.current_price:,.0f} KRW, "
                    f"P&L {pnl_sign}{p.unrealized_pnl:,.0f} KRW ({pnl_sign}{p.unrealized_pnl_pct:.1f}%)"
                )
        else:
            lines.append("\nNo current positions.")

        return "\n".join(lines)

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get raw portfolio snapshot from broker."""
        return self.broker.get_portfolio()
