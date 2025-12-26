"""Risk Controls for order execution.

Issue #28: [EXEC-27] Risk controls - position limits, loss limits

This module provides pre-trade risk validation including:
- Position size limits (max shares, max notional value)
- Concentration limits (max % of portfolio in single position)
- Daily loss limits
- Drawdown limits
- Pre-trade validation framework

Example:
    >>> from tradingagents.execution import RiskManager, PositionLimits, LossLimits
    >>>
    >>> limits = PositionLimits(
    ...     max_position_size=Decimal("10000"),
    ...     max_position_value=Decimal("50000"),
    ...     max_concentration_percent=Decimal("20"),
    ... )
    >>> risk_manager = RiskManager(position_limits=limits)
    >>> result = risk_manager.check_order(order_request, portfolio)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from .broker_base import (
    OrderRequest,
    OrderSide,
    Position,
)


class RiskCheckResult(Enum):
    """Result of a risk check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class RiskRuleType(Enum):
    """Type of risk rule."""

    POSITION_SIZE = "position_size"
    POSITION_VALUE = "position_value"
    CONCENTRATION = "concentration"
    DAILY_LOSS = "daily_loss"
    DRAWDOWN = "drawdown"
    CUSTOM = "custom"


@dataclass
class RiskViolation:
    """Details of a risk limit violation.

    Attributes:
        rule_type: Type of rule violated
        rule_name: Name of the specific rule
        message: Human-readable violation message
        current_value: Current value that violated the limit
        limit_value: The limit that was exceeded
        severity: Violation severity (error, warning)
        metadata: Additional context
    """

    rule_type: RiskRuleType
    rule_name: str
    message: str
    current_value: Decimal
    limit_value: Decimal
    severity: str = "error"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskCheckResponse:
    """Response from risk validation.

    Attributes:
        passed: Whether all risk checks passed
        violations: List of rule violations
        warnings: List of warnings (non-blocking)
        checked_rules: List of rules that were checked
        timestamp: When the check was performed
    """

    passed: bool = True
    violations: List[RiskViolation] = field(default_factory=list)
    warnings: List[RiskViolation] = field(default_factory=list)
    checked_rules: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_violation(self, violation: RiskViolation) -> None:
        """Add a violation to the response."""
        if violation.severity == "warning":
            self.warnings.append(violation)
        else:
            self.violations.append(violation)
            self.passed = False

    @property
    def rejection_message(self) -> Optional[str]:
        """Get formatted rejection message if failed."""
        if self.passed:
            return None
        messages = [v.message for v in self.violations]
        return "; ".join(messages)


@dataclass
class PositionLimits:
    """Position-related risk limits.

    Attributes:
        max_position_size: Maximum shares/units in single position
        max_position_value: Maximum notional value of single position
        max_concentration_percent: Maximum % of portfolio in single position
        max_total_positions: Maximum number of open positions
        max_sector_concentration: Maximum % in single sector
        per_symbol_limits: Custom limits per symbol
    """

    max_position_size: Optional[Decimal] = None
    max_position_value: Optional[Decimal] = None
    max_concentration_percent: Optional[Decimal] = None
    max_total_positions: Optional[int] = None
    max_sector_concentration: Optional[Decimal] = None
    per_symbol_limits: Dict[str, Dict[str, Decimal]] = field(default_factory=dict)

    def get_limit_for_symbol(
        self, symbol: str, limit_type: str
    ) -> Optional[Decimal]:
        """Get specific limit for a symbol, falling back to default."""
        if symbol in self.per_symbol_limits:
            if limit_type in self.per_symbol_limits[symbol]:
                return self.per_symbol_limits[symbol][limit_type]

        return getattr(self, limit_type, None)


@dataclass
class LossLimits:
    """Loss-related risk limits.

    Attributes:
        max_daily_loss: Maximum loss allowed per day
        max_daily_loss_percent: Maximum loss as % of equity per day
        max_drawdown: Maximum drawdown from peak
        max_drawdown_percent: Maximum drawdown as % of peak
        max_single_trade_loss: Maximum loss on single trade
        max_consecutive_losses: Maximum consecutive losing trades
        cooling_off_period_minutes: Minutes to wait after hitting limit
    """

    max_daily_loss: Optional[Decimal] = None
    max_daily_loss_percent: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None
    max_drawdown_percent: Optional[Decimal] = None
    max_single_trade_loss: Optional[Decimal] = None
    max_consecutive_losses: Optional[int] = None
    cooling_off_period_minutes: int = 0


@dataclass
class PortfolioState:
    """Current portfolio state for risk calculations.

    Attributes:
        positions: Current positions keyed by symbol
        cash: Available cash
        equity: Total portfolio equity
        buying_power: Available buying power
        daily_pnl: Profit/loss for current day
        peak_equity: Peak equity for drawdown calculations
        consecutive_losses: Current consecutive losing trades
        last_loss_time: When last loss occurred
    """

    positions: Dict[str, Position] = field(default_factory=dict)
    cash: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    buying_power: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    peak_equity: Optional[Decimal] = None
    consecutive_losses: int = 0
    last_loss_time: Optional[datetime] = None

    @property
    def current_drawdown(self) -> Decimal:
        """Calculate current drawdown from peak."""
        if self.peak_equity is None or self.peak_equity <= 0:
            return Decimal("0")
        return self.peak_equity - self.equity

    @property
    def current_drawdown_percent(self) -> Decimal:
        """Calculate current drawdown as percentage."""
        if self.peak_equity is None or self.peak_equity <= 0:
            return Decimal("0")
        return (self.current_drawdown / self.peak_equity) * Decimal("100")


class RiskManager:
    """Manages pre-trade risk validation.

    The RiskManager validates orders against configured risk limits
    before allowing them to be submitted to brokers.

    Example:
        >>> risk_manager = RiskManager(
        ...     position_limits=PositionLimits(max_position_size=1000),
        ...     loss_limits=LossLimits(max_daily_loss=Decimal("500")),
        ... )
        >>> result = risk_manager.validate_order(order_request, portfolio_state)
        >>> if not result.passed:
        ...     print(f"Order rejected: {result.rejection_message}")
    """

    def __init__(
        self,
        position_limits: Optional[PositionLimits] = None,
        loss_limits: Optional[LossLimits] = None,
        custom_rules: Optional[List[Callable]] = None,
        enabled: bool = True,
    ) -> None:
        """Initialize risk manager.

        Args:
            position_limits: Position-related limits
            loss_limits: Loss-related limits
            custom_rules: Custom validation functions
            enabled: Whether risk checks are enabled
        """
        self._position_limits = position_limits or PositionLimits()
        self._loss_limits = loss_limits or LossLimits()
        self._custom_rules = custom_rules or []
        self._enabled = enabled
        self._daily_pnl_by_date: Dict[date, Decimal] = {}
        self._peak_equity: Optional[Decimal] = None
        self._in_cooling_off = False
        self._cooling_off_until: Optional[datetime] = None

    @property
    def enabled(self) -> bool:
        """Check if risk manager is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable risk manager."""
        self._enabled = value

    @property
    def position_limits(self) -> PositionLimits:
        """Get position limits."""
        return self._position_limits

    @position_limits.setter
    def position_limits(self, limits: PositionLimits) -> None:
        """Set position limits."""
        self._position_limits = limits

    @property
    def loss_limits(self) -> LossLimits:
        """Get loss limits."""
        return self._loss_limits

    @loss_limits.setter
    def loss_limits(self, limits: LossLimits) -> None:
        """Set loss limits."""
        self._loss_limits = limits

    def add_custom_rule(
        self,
        rule: Callable[[OrderRequest, PortfolioState], Optional[RiskViolation]],
    ) -> None:
        """Add a custom validation rule.

        Args:
            rule: Function that takes order and portfolio, returns violation or None
        """
        self._custom_rules.append(rule)

    def validate_order(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        estimated_fill_price: Optional[Decimal] = None,
    ) -> RiskCheckResponse:
        """Validate an order against all risk limits.

        Args:
            order: Order request to validate
            portfolio: Current portfolio state
            estimated_fill_price: Expected fill price for value calculations

        Returns:
            RiskCheckResponse with validation results
        """
        response = RiskCheckResponse()

        if not self._enabled:
            response.checked_rules.append("(risk checks disabled)")
            return response

        # Check cooling off period
        if self._in_cooling_off and self._cooling_off_until:
            if datetime.now(timezone.utc) < self._cooling_off_until:
                response.add_violation(
                    RiskViolation(
                        rule_type=RiskRuleType.DAILY_LOSS,
                        rule_name="cooling_off_period",
                        message=f"In cooling off period until {self._cooling_off_until}",
                        current_value=Decimal("0"),
                        limit_value=Decimal("0"),
                    )
                )
                return response
            else:
                self._in_cooling_off = False
                self._cooling_off_until = None

        # Run all checks
        self._check_position_size(order, portfolio, response)
        self._check_position_value(order, portfolio, response, estimated_fill_price)
        self._check_concentration(order, portfolio, response, estimated_fill_price)
        self._check_total_positions(order, portfolio, response)
        self._check_daily_loss(portfolio, response)
        self._check_drawdown(portfolio, response)
        self._check_single_trade_loss(order, portfolio, response, estimated_fill_price)
        self._check_consecutive_losses(portfolio, response)
        self._run_custom_rules(order, portfolio, response)

        return response

    def _check_position_size(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
    ) -> None:
        """Check position size limits."""
        response.checked_rules.append("position_size")

        limit = self._position_limits.get_limit_for_symbol(
            order.symbol, "max_position_size"
        )
        if limit is None:
            return

        current_position = portfolio.positions.get(order.symbol)
        current_qty = current_position.quantity if current_position else Decimal("0")

        if order.side == OrderSide.BUY:
            new_qty = current_qty + order.quantity
        else:
            new_qty = current_qty - order.quantity

        if abs(new_qty) > limit:
            response.add_violation(
                RiskViolation(
                    rule_type=RiskRuleType.POSITION_SIZE,
                    rule_name="max_position_size",
                    message=(
                        f"Position size {abs(new_qty)} exceeds limit {limit} "
                        f"for {order.symbol}"
                    ),
                    current_value=abs(new_qty),
                    limit_value=limit,
                )
            )

    def _check_position_value(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
        estimated_price: Optional[Decimal],
    ) -> None:
        """Check position value limits."""
        response.checked_rules.append("position_value")

        limit = self._position_limits.get_limit_for_symbol(
            order.symbol, "max_position_value"
        )
        if limit is None:
            return

        if estimated_price is None:
            # Can't check without price
            return

        current_position = portfolio.positions.get(order.symbol)
        current_qty = current_position.quantity if current_position else Decimal("0")

        if order.side == OrderSide.BUY:
            new_qty = current_qty + order.quantity
        else:
            new_qty = current_qty - order.quantity

        new_value = abs(new_qty * estimated_price)

        if new_value > limit:
            response.add_violation(
                RiskViolation(
                    rule_type=RiskRuleType.POSITION_VALUE,
                    rule_name="max_position_value",
                    message=(
                        f"Position value ${new_value} exceeds limit ${limit} "
                        f"for {order.symbol}"
                    ),
                    current_value=new_value,
                    limit_value=limit,
                )
            )

    def _check_concentration(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
        estimated_price: Optional[Decimal],
    ) -> None:
        """Check concentration limits."""
        response.checked_rules.append("concentration")

        limit = self._position_limits.max_concentration_percent
        if limit is None:
            return

        if estimated_price is None or portfolio.equity <= 0:
            return

        current_position = portfolio.positions.get(order.symbol)
        current_qty = current_position.quantity if current_position else Decimal("0")

        if order.side == OrderSide.BUY:
            new_qty = current_qty + order.quantity
        else:
            new_qty = current_qty - order.quantity

        new_value = abs(new_qty * estimated_price)
        concentration = (new_value / portfolio.equity) * Decimal("100")

        if concentration > limit:
            response.add_violation(
                RiskViolation(
                    rule_type=RiskRuleType.CONCENTRATION,
                    rule_name="max_concentration",
                    message=(
                        f"Concentration {concentration:.1f}% exceeds limit {limit}% "
                        f"for {order.symbol}"
                    ),
                    current_value=concentration,
                    limit_value=limit,
                )
            )

    def _check_total_positions(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
    ) -> None:
        """Check total positions limit."""
        response.checked_rules.append("total_positions")

        limit = self._position_limits.max_total_positions
        if limit is None:
            return

        # Only check for new positions (buys in symbols we don't have)
        if order.side != OrderSide.BUY:
            return

        if order.symbol in portfolio.positions:
            return  # Adding to existing position

        if len(portfolio.positions) >= limit:
            response.add_violation(
                RiskViolation(
                    rule_type=RiskRuleType.POSITION_SIZE,
                    rule_name="max_total_positions",
                    message=(
                        f"Total positions {len(portfolio.positions)} at limit {limit}"
                    ),
                    current_value=Decimal(str(len(portfolio.positions))),
                    limit_value=Decimal(str(limit)),
                )
            )

    def _check_daily_loss(
        self,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
    ) -> None:
        """Check daily loss limits."""
        response.checked_rules.append("daily_loss")

        # Check absolute daily loss
        if self._loss_limits.max_daily_loss is not None:
            if portfolio.daily_pnl < -self._loss_limits.max_daily_loss:
                self._trigger_cooling_off()
                response.add_violation(
                    RiskViolation(
                        rule_type=RiskRuleType.DAILY_LOSS,
                        rule_name="max_daily_loss",
                        message=(
                            f"Daily loss ${abs(portfolio.daily_pnl)} exceeds limit "
                            f"${self._loss_limits.max_daily_loss}"
                        ),
                        current_value=abs(portfolio.daily_pnl),
                        limit_value=self._loss_limits.max_daily_loss,
                    )
                )

        # Check percentage daily loss
        if self._loss_limits.max_daily_loss_percent is not None:
            if portfolio.equity > 0:
                daily_loss_pct = (
                    abs(portfolio.daily_pnl) / portfolio.equity
                ) * Decimal("100")
                if (
                    portfolio.daily_pnl < 0
                    and daily_loss_pct > self._loss_limits.max_daily_loss_percent
                ):
                    self._trigger_cooling_off()
                    response.add_violation(
                        RiskViolation(
                            rule_type=RiskRuleType.DAILY_LOSS,
                            rule_name="max_daily_loss_percent",
                            message=(
                                f"Daily loss {daily_loss_pct:.1f}% exceeds limit "
                                f"{self._loss_limits.max_daily_loss_percent}%"
                            ),
                            current_value=daily_loss_pct,
                            limit_value=self._loss_limits.max_daily_loss_percent,
                        )
                    )

    def _check_drawdown(
        self,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
    ) -> None:
        """Check drawdown limits."""
        response.checked_rules.append("drawdown")

        # Check absolute drawdown
        if self._loss_limits.max_drawdown is not None:
            if portfolio.current_drawdown > self._loss_limits.max_drawdown:
                response.add_violation(
                    RiskViolation(
                        rule_type=RiskRuleType.DRAWDOWN,
                        rule_name="max_drawdown",
                        message=(
                            f"Drawdown ${portfolio.current_drawdown} exceeds limit "
                            f"${self._loss_limits.max_drawdown}"
                        ),
                        current_value=portfolio.current_drawdown,
                        limit_value=self._loss_limits.max_drawdown,
                    )
                )

        # Check percentage drawdown
        if self._loss_limits.max_drawdown_percent is not None:
            if portfolio.current_drawdown_percent > self._loss_limits.max_drawdown_percent:
                response.add_violation(
                    RiskViolation(
                        rule_type=RiskRuleType.DRAWDOWN,
                        rule_name="max_drawdown_percent",
                        message=(
                            f"Drawdown {portfolio.current_drawdown_percent:.1f}% "
                            f"exceeds limit {self._loss_limits.max_drawdown_percent}%"
                        ),
                        current_value=portfolio.current_drawdown_percent,
                        limit_value=self._loss_limits.max_drawdown_percent,
                    )
                )

    def _check_single_trade_loss(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
        estimated_price: Optional[Decimal],
    ) -> None:
        """Check single trade loss limit."""
        response.checked_rules.append("single_trade_loss")

        limit = self._loss_limits.max_single_trade_loss
        if limit is None:
            return

        if estimated_price is None:
            return

        # Calculate max potential loss for the order
        order_value = order.quantity * estimated_price

        # For sells, potential loss is limited
        # For buys, assume worst case is total loss of order value
        if order.side == OrderSide.BUY:
            potential_loss = order_value
            if potential_loss > limit:
                response.add_violation(
                    RiskViolation(
                        rule_type=RiskRuleType.DAILY_LOSS,
                        rule_name="max_single_trade_loss",
                        message=(
                            f"Potential loss ${potential_loss} exceeds limit "
                            f"${limit}"
                        ),
                        current_value=potential_loss,
                        limit_value=limit,
                        severity="warning",  # Warning, not blocking
                    )
                )

    def _check_consecutive_losses(
        self,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
    ) -> None:
        """Check consecutive losses limit."""
        response.checked_rules.append("consecutive_losses")

        limit = self._loss_limits.max_consecutive_losses
        if limit is None:
            return

        if portfolio.consecutive_losses >= limit:
            self._trigger_cooling_off()
            response.add_violation(
                RiskViolation(
                    rule_type=RiskRuleType.DAILY_LOSS,
                    rule_name="max_consecutive_losses",
                    message=(
                        f"Consecutive losses {portfolio.consecutive_losses} "
                        f"reached limit {limit}"
                    ),
                    current_value=Decimal(str(portfolio.consecutive_losses)),
                    limit_value=Decimal(str(limit)),
                )
            )

    def _run_custom_rules(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        response: RiskCheckResponse,
    ) -> None:
        """Run custom validation rules."""
        for i, rule in enumerate(self._custom_rules):
            response.checked_rules.append(f"custom_rule_{i}")
            try:
                violation = rule(order, portfolio)
                if violation:
                    response.add_violation(violation)
            except Exception:
                # Don't let custom rule errors break validation
                pass

    def _trigger_cooling_off(self) -> None:
        """Trigger cooling off period."""
        if self._loss_limits.cooling_off_period_minutes > 0:
            self._in_cooling_off = True
            from datetime import timedelta

            self._cooling_off_until = datetime.now(timezone.utc) + timedelta(
                minutes=self._loss_limits.cooling_off_period_minutes
            )

    def update_daily_pnl(self, pnl: Decimal, trade_date: date) -> None:
        """Update daily P&L tracking.

        Args:
            pnl: P&L for the trade
            trade_date: Date of the trade
        """
        if trade_date not in self._daily_pnl_by_date:
            self._daily_pnl_by_date[trade_date] = Decimal("0")
        self._daily_pnl_by_date[trade_date] += pnl

    def get_daily_pnl(self, trade_date: date) -> Decimal:
        """Get daily P&L for a date.

        Args:
            trade_date: Date to get P&L for

        Returns:
            P&L for the date
        """
        return self._daily_pnl_by_date.get(trade_date, Decimal("0"))

    def update_peak_equity(self, equity: Decimal) -> None:
        """Update peak equity tracking.

        Args:
            equity: Current equity
        """
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

    def reset_daily_limits(self) -> None:
        """Reset daily tracking (call at start of each trading day)."""
        self._in_cooling_off = False
        self._cooling_off_until = None

    def reset_all(self) -> None:
        """Reset all tracking state."""
        self._daily_pnl_by_date.clear()
        self._peak_equity = None
        self._in_cooling_off = False
        self._cooling_off_until = None


# Export
__all__ = [
    "RiskManager",
    "RiskCheckResult",
    "RiskRuleType",
    "RiskViolation",
    "RiskCheckResponse",
    "PositionLimits",
    "LossLimits",
    "PortfolioState",
]
