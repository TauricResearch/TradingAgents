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

import logging
from datetime import datetime, timezone, timedelta

from .models import OrderRequest, PortfolioSnapshot

logger = logging.getLogger(__name__)

# KST timezone (UTC+9)
KST = timezone(timedelta(hours=9))


class SafetyGuard:
    """Validates orders against safety constraints before execution."""

    def __init__(self, config: dict):
        safety = config.get("broker", {}).get("safety", {})
        self.max_position_pct = safety.get("max_position_pct", 0.10)
        self.max_order_amount = safety.get("max_order_amount", 5_000_000)
        self.daily_loss_limit = safety.get("daily_loss_limit", -500_000)
        self.enforce_market_hours = safety.get("enforce_market_hours", True)
        self.is_paper = config.get("broker", {}).get("mode", "paper") == "paper"

    def check_market_hours(self) -> tuple[bool, str]:
        """Check if KRX is open (09:00-15:30 KST, weekdays).

        Paper trading bypasses this check.
        """
        if self.is_paper:
            return True, "Paper trading: market hours not enforced"

        if not self.enforce_market_hours:
            return True, "Market hours enforcement disabled"

        now = datetime.now(KST)

        # Weekday check (0=Monday, 6=Sunday)
        if now.weekday() >= 5:
            return False, f"KRX is closed on weekends (today: {now.strftime('%A')})"

        market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        if now < market_open:
            return False, f"KRX not yet open (opens at 09:00 KST, current: {now.strftime('%H:%M')})"
        if now > market_close:
            return False, f"KRX already closed (closed at 15:30 KST, current: {now.strftime('%H:%M')})"

        return True, "KRX market is open"

    def check_position_size(
        self, order_amount: float, portfolio: PortfolioSnapshot
    ) -> tuple[bool, str]:
        """Ensure single position does not exceed max_position_pct of total equity."""
        total_equity = portfolio.balance.total_equity
        if total_equity <= 0:
            return True, "No portfolio data available, skipping position size check"

        position_pct = order_amount / total_equity
        if position_pct > self.max_position_pct:
            return (
                False,
                f"Order amount ({order_amount:,.0f} KRW) exceeds "
                f"{self.max_position_pct:.0%} of total equity ({total_equity:,.0f} KRW)",
            )

        return True, "Position size OK"

    def check_order_amount(self, amount: float) -> tuple[bool, str]:
        """Ensure single order does not exceed max_order_amount."""
        if amount > self.max_order_amount:
            return (
                False,
                f"Order amount ({amount:,.0f} KRW) exceeds maximum "
                f"({self.max_order_amount:,.0f} KRW)",
            )
        return True, "Order amount OK"

    def check_daily_loss(self, current_daily_pnl: float) -> tuple[bool, str]:
        """Ensure daily losses have not exceeded limit."""
        if current_daily_pnl < self.daily_loss_limit:
            return (
                False,
                f"Daily loss ({current_daily_pnl:,.0f} KRW) exceeds limit "
                f"({self.daily_loss_limit:,.0f} KRW). Trading halted.",
            )
        return True, "Daily loss within limit"

    def validate_all(
        self,
        order: OrderRequest,
        price: float,
        portfolio: PortfolioSnapshot,
        daily_pnl: float,
    ) -> tuple[bool, str]:
        """Run all safety checks. Returns (passed, reason)."""
        order_amount = price * order.quantity

        checks = [
            self.check_market_hours(),
            self.check_order_amount(order_amount),
            self.check_position_size(order_amount, portfolio),
            self.check_daily_loss(daily_pnl),
        ]

        for passed, reason in checks:
            if not passed:
                logger.warning("Safety check failed: %s", reason)
                return False, reason

        return True, "All safety checks passed"
