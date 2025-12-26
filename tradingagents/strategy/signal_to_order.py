"""Signal to Order Converter.

This module converts trading signals into executable orders by:
- Translating BUY/SELL signals to OrderRequest objects
- Applying position sizing based on risk parameters
- Setting stop loss and take profit levels
- Validating orders before submission

Issue #36: [STRAT-35] Signal to order converter

Design Principles:
    - Clean separation between signal generation and execution
    - Risk-aware position sizing
    - Configurable stop loss and take profit
    - Comprehensive order validation
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import uuid

from tradingagents.execution.broker_base import (
    OrderRequest,
    OrderSide,
    OrderType,
    TimeInForce,
)


# ============================================================================
# Enums
# ============================================================================

class SignalType(str, Enum):
    """Type of trading signal."""
    BUY = "buy"              # Long entry
    SELL = "sell"            # Long exit or short entry
    HOLD = "hold"            # No action
    CLOSE = "close"          # Close existing position
    SCALE_IN = "scale_in"    # Add to position
    SCALE_OUT = "scale_out"  # Reduce position


class SignalStrength(str, Enum):
    """Strength of the signal."""
    STRONG = "strong"        # High confidence, full size
    MODERATE = "moderate"    # Medium confidence, partial size
    WEAK = "weak"            # Low confidence, minimal size


class PositionSizingMethod(str, Enum):
    """Method for calculating position size."""
    FIXED_QUANTITY = "fixed_quantity"       # Fixed number of shares
    FIXED_VALUE = "fixed_value"             # Fixed dollar amount
    PERCENT_PORTFOLIO = "percent_portfolio"  # Percentage of portfolio
    RISK_BASED = "risk_based"               # Based on max risk per trade
    VOLATILITY_BASED = "volatility_based"   # Based on asset volatility


class StopLossType(str, Enum):
    """Type of stop loss."""
    FIXED_PERCENT = "fixed_percent"         # Fixed percentage below entry
    FIXED_AMOUNT = "fixed_amount"           # Fixed dollar amount below entry
    ATR_BASED = "atr_based"                 # Multiple of ATR
    VOLATILITY_BASED = "volatility_based"   # Based on historical volatility
    SUPPORT_LEVEL = "support_level"         # At support level
    TRAILING = "trailing"                   # Trailing stop


class TakeProfitType(str, Enum):
    """Type of take profit."""
    FIXED_PERCENT = "fixed_percent"         # Fixed percentage above entry
    FIXED_AMOUNT = "fixed_amount"           # Fixed dollar amount above entry
    RISK_REWARD = "risk_reward"             # Multiple of risk (R:R ratio)
    RESISTANCE_LEVEL = "resistance_level"   # At resistance level
    TRAILING = "trailing"                   # Trailing take profit


class OrderValidationError(str, Enum):
    """Order validation error types."""
    INVALID_SYMBOL = "invalid_symbol"
    INVALID_QUANTITY = "invalid_quantity"
    INVALID_PRICE = "invalid_price"
    INSUFFICIENT_CAPITAL = "insufficient_capital"
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"
    INVALID_STOP_LOSS = "invalid_stop_loss"
    INVALID_TAKE_PROFIT = "invalid_take_profit"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TradingSignal:
    """A trading signal from strategy or analyst.

    Attributes:
        signal_id: Unique identifier for the signal
        timestamp: When the signal was generated
        symbol: Trading symbol
        signal_type: Type of signal (buy, sell, hold, etc.)
        strength: Signal strength (strong, moderate, weak)
        entry_price: Suggested entry price
        target_price: Suggested target price
        stop_price: Suggested stop price
        confidence: Confidence level (0-1)
        reason: Human-readable reason for signal
        metadata: Additional signal data
    """
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    symbol: str = ""
    signal_type: SignalType = SignalType.HOLD
    strength: SignalStrength = SignalStrength.MODERATE
    entry_price: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    confidence: Decimal = Decimal("0.5")
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionSizingConfig:
    """Configuration for position sizing.

    Attributes:
        method: Position sizing method
        fixed_quantity: Fixed quantity for FIXED_QUANTITY method
        fixed_value: Fixed value for FIXED_VALUE method
        percent_portfolio: Percentage for PERCENT_PORTFOLIO method
        max_risk_per_trade: Max risk per trade (as decimal, e.g., 0.01 = 1%)
        max_position_percent: Max position size as % of portfolio
        round_to_lot_size: Whether to round to lot sizes
        lot_size: Lot size for rounding (default 1)
        min_quantity: Minimum order quantity
        max_quantity: Maximum order quantity
    """
    method: PositionSizingMethod = PositionSizingMethod.PERCENT_PORTFOLIO
    fixed_quantity: Decimal = Decimal("100")
    fixed_value: Decimal = Decimal("10000")
    percent_portfolio: Decimal = Decimal("0.05")  # 5%
    max_risk_per_trade: Decimal = Decimal("0.01")  # 1%
    max_position_percent: Decimal = Decimal("0.20")  # 20%
    round_to_lot_size: bool = True
    lot_size: Decimal = Decimal("1")
    min_quantity: Decimal = Decimal("1")
    max_quantity: Optional[Decimal] = None


@dataclass
class StopLossConfig:
    """Configuration for stop loss.

    Attributes:
        type: Stop loss type
        percent: Percentage for FIXED_PERCENT type
        amount: Dollar amount for FIXED_AMOUNT type
        atr_multiplier: ATR multiplier for ATR_BASED type
        trail_percent: Trail percentage for TRAILING type
        trail_amount: Trail amount for TRAILING type
        enabled: Whether stop loss is enabled
    """
    type: StopLossType = StopLossType.FIXED_PERCENT
    percent: Decimal = Decimal("0.02")  # 2%
    amount: Optional[Decimal] = None
    atr_multiplier: Decimal = Decimal("2.0")
    trail_percent: Optional[Decimal] = None
    trail_amount: Optional[Decimal] = None
    enabled: bool = True


@dataclass
class TakeProfitConfig:
    """Configuration for take profit.

    Attributes:
        type: Take profit type
        percent: Percentage for FIXED_PERCENT type
        amount: Dollar amount for FIXED_AMOUNT type
        risk_reward_ratio: Risk:reward ratio for RISK_REWARD type
        enabled: Whether take profit is enabled
    """
    type: TakeProfitType = TakeProfitType.RISK_REWARD
    percent: Decimal = Decimal("0.06")  # 6%
    amount: Optional[Decimal] = None
    risk_reward_ratio: Decimal = Decimal("3.0")  # 3:1 R:R
    enabled: bool = True


@dataclass
class ConversionConfig:
    """Configuration for signal to order conversion.

    Attributes:
        position_sizing: Position sizing configuration
        stop_loss: Stop loss configuration
        take_profit: Take profit configuration
        default_order_type: Default order type
        default_time_in_force: Default time in force
        use_limit_orders: Use limit orders instead of market
        limit_order_offset: Offset from signal price for limits
        scale_by_strength: Scale position size by signal strength
        strength_multipliers: Multipliers for each signal strength
        scale_by_confidence: Scale position size by confidence
        min_confidence: Minimum confidence to generate order
    """
    position_sizing: PositionSizingConfig = field(
        default_factory=PositionSizingConfig
    )
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = field(default_factory=TakeProfitConfig)
    default_order_type: OrderType = OrderType.MARKET
    default_time_in_force: TimeInForce = TimeInForce.DAY
    use_limit_orders: bool = False
    limit_order_offset: Decimal = Decimal("0.001")  # 0.1%
    scale_by_strength: bool = True
    strength_multipliers: Dict[SignalStrength, Decimal] = field(
        default_factory=lambda: {
            SignalStrength.STRONG: Decimal("1.0"),
            SignalStrength.MODERATE: Decimal("0.75"),
            SignalStrength.WEAK: Decimal("0.5"),
        }
    )
    scale_by_confidence: bool = False
    min_confidence: Decimal = Decimal("0.0")


@dataclass
class OrderValidationResult:
    """Result of order validation.

    Attributes:
        is_valid: Whether the order is valid
        errors: List of validation errors
        warnings: List of validation warnings
        adjusted_quantity: Quantity after adjustments (if any)
        adjusted_stop_price: Stop price after adjustments
        adjusted_take_profit: Take profit after adjustments
    """
    is_valid: bool = True
    errors: List[Tuple[OrderValidationError, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    adjusted_quantity: Optional[Decimal] = None
    adjusted_stop_price: Optional[Decimal] = None
    adjusted_take_profit: Optional[Decimal] = None


@dataclass
class ConversionResult:
    """Result of signal to order conversion.

    Attributes:
        success: Whether conversion succeeded
        order_request: The generated OrderRequest (if successful)
        stop_loss_order: Stop loss order (if configured)
        take_profit_order: Take profit order (if configured)
        validation: Validation result
        signal: Original signal
        calculated_quantity: Position size calculated
        calculated_stop_price: Stop loss price calculated
        calculated_take_profit: Take profit price calculated
        error_message: Error message (if failed)
    """
    success: bool = True
    order_request: Optional[OrderRequest] = None
    stop_loss_order: Optional[OrderRequest] = None
    take_profit_order: Optional[OrderRequest] = None
    validation: OrderValidationResult = field(
        default_factory=OrderValidationResult
    )
    signal: Optional[TradingSignal] = None
    calculated_quantity: Decimal = Decimal("0")
    calculated_stop_price: Optional[Decimal] = None
    calculated_take_profit: Optional[Decimal] = None
    error_message: str = ""


# ============================================================================
# SignalToOrderConverter Class
# ============================================================================

class SignalToOrderConverter:
    """Converts trading signals to executable orders.

    This class handles the conversion of trading signals into OrderRequest
    objects, applying position sizing, stop loss, and take profit logic.

    Attributes:
        config: Conversion configuration
        portfolio_value: Current portfolio value (for sizing)
        current_prices: Dict of symbol to current price
        volatility_data: Dict of symbol to volatility (for ATR-based stops)
    """

    def __init__(
        self,
        config: Optional[ConversionConfig] = None,
        portfolio_value: Decimal = Decimal("100000"),
        current_prices: Optional[Dict[str, Decimal]] = None,
        volatility_data: Optional[Dict[str, Decimal]] = None,
    ):
        """Initialize the converter.

        Args:
            config: Conversion configuration (uses defaults if None)
            portfolio_value: Current portfolio value
            current_prices: Dict of symbol to current market price
            volatility_data: Dict of symbol to ATR or volatility
        """
        self.config = config or ConversionConfig()
        self.portfolio_value = portfolio_value
        self.current_prices = current_prices or {}
        self.volatility_data = volatility_data or {}

    def convert(self, signal: TradingSignal) -> ConversionResult:
        """Convert a trading signal to an order.

        Args:
            signal: The trading signal to convert

        Returns:
            ConversionResult with order(s) and validation info
        """
        result = ConversionResult(signal=signal)

        # Skip non-actionable signals
        if signal.signal_type == SignalType.HOLD:
            result.success = False
            result.error_message = "HOLD signals do not generate orders"
            return result

        # Check minimum confidence
        if signal.confidence < self.config.min_confidence:
            result.success = False
            result.error_message = (
                f"Signal confidence {signal.confidence} below minimum "
                f"{self.config.min_confidence}"
            )
            return result

        # Get entry price
        entry_price = self._get_entry_price(signal)
        if entry_price is None:
            result.success = False
            result.error_message = (
                f"Cannot determine entry price for {signal.symbol}"
            )
            return result

        # Calculate position size
        quantity = self._calculate_position_size(
            signal=signal,
            entry_price=entry_price,
        )
        result.calculated_quantity = quantity

        # Calculate stop loss
        stop_price = None
        if self.config.stop_loss.enabled:
            stop_price = self._calculate_stop_loss(
                signal=signal,
                entry_price=entry_price,
            )
            result.calculated_stop_price = stop_price

        # Calculate take profit
        take_profit_price = None
        if self.config.take_profit.enabled:
            take_profit_price = self._calculate_take_profit(
                signal=signal,
                entry_price=entry_price,
                stop_price=stop_price,
            )
            result.calculated_take_profit = take_profit_price

        # Validate the order
        validation = self._validate_order(
            signal=signal,
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        result.validation = validation

        if not validation.is_valid:
            result.success = False
            result.error_message = "; ".join(
                f"{e.value}: {msg}" for e, msg in validation.errors
            )
            return result

        # Use adjusted values if available
        final_quantity = validation.adjusted_quantity or quantity
        final_stop = validation.adjusted_stop_price or stop_price
        final_tp = validation.adjusted_take_profit or take_profit_price

        # Determine order side
        order_side = self._signal_to_side(signal.signal_type)

        # Determine order type and price
        order_type, limit_price = self._determine_order_type(
            signal=signal,
            entry_price=entry_price,
        )

        # Create main order
        try:
            main_order = OrderRequest(
                symbol=signal.symbol,
                side=order_side,
                quantity=final_quantity,
                order_type=order_type,
                limit_price=limit_price,
                time_in_force=self.config.default_time_in_force,
                stop_loss_price=final_stop if self.config.stop_loss.enabled else None,
                take_profit_price=final_tp if self.config.take_profit.enabled else None,
                metadata={
                    "signal_id": signal.signal_id,
                    "signal_strength": signal.strength.value,
                    "signal_confidence": str(signal.confidence),
                    "signal_reason": signal.reason,
                },
            )
            result.order_request = main_order
        except ValueError as e:
            result.success = False
            result.error_message = f"Failed to create order: {str(e)}"
            return result

        # Create separate stop loss order if needed
        if final_stop and order_side == OrderSide.BUY:
            try:
                result.stop_loss_order = OrderRequest(
                    symbol=signal.symbol,
                    side=OrderSide.SELL,
                    quantity=final_quantity,
                    order_type=OrderType.STOP,
                    stop_price=final_stop,
                    time_in_force=TimeInForce.GTC,
                    metadata={"parent_signal_id": signal.signal_id},
                )
            except ValueError:
                # Non-fatal - main order is still valid
                result.validation.warnings.append(
                    "Could not create separate stop loss order"
                )

        # Create separate take profit order if needed
        if final_tp and order_side == OrderSide.BUY:
            try:
                result.take_profit_order = OrderRequest(
                    symbol=signal.symbol,
                    side=OrderSide.SELL,
                    quantity=final_quantity,
                    order_type=OrderType.LIMIT,
                    limit_price=final_tp,
                    time_in_force=TimeInForce.GTC,
                    metadata={"parent_signal_id": signal.signal_id},
                )
            except ValueError:
                result.validation.warnings.append(
                    "Could not create separate take profit order"
                )

        result.success = True
        return result

    def convert_batch(
        self,
        signals: List[TradingSignal],
    ) -> List[ConversionResult]:
        """Convert multiple signals to orders.

        Args:
            signals: List of trading signals

        Returns:
            List of ConversionResult for each signal
        """
        return [self.convert(signal) for signal in signals]

    def _get_entry_price(self, signal: TradingSignal) -> Optional[Decimal]:
        """Get entry price for signal.

        Args:
            signal: The trading signal

        Returns:
            Entry price or None if unavailable
        """
        # Use signal's entry price if available
        if signal.entry_price is not None:
            return signal.entry_price

        # Fall back to current market price
        if signal.symbol in self.current_prices:
            return self.current_prices[signal.symbol]

        return None

    def _calculate_position_size(
        self,
        signal: TradingSignal,
        entry_price: Decimal,
    ) -> Decimal:
        """Calculate position size based on configuration.

        Args:
            signal: The trading signal
            entry_price: Entry price for the trade

        Returns:
            Position size in shares/contracts
        """
        config = self.config.position_sizing

        # Start with base size from method
        if config.method == PositionSizingMethod.FIXED_QUANTITY:
            base_quantity = config.fixed_quantity

        elif config.method == PositionSizingMethod.FIXED_VALUE:
            if entry_price > 0:
                base_quantity = config.fixed_value / entry_price
            else:
                base_quantity = Decimal("0")

        elif config.method == PositionSizingMethod.PERCENT_PORTFOLIO:
            position_value = self.portfolio_value * config.percent_portfolio
            if entry_price > 0:
                base_quantity = position_value / entry_price
            else:
                base_quantity = Decimal("0")

        elif config.method == PositionSizingMethod.RISK_BASED:
            base_quantity = self._calculate_risk_based_size(
                signal=signal,
                entry_price=entry_price,
            )

        elif config.method == PositionSizingMethod.VOLATILITY_BASED:
            base_quantity = self._calculate_volatility_based_size(
                signal=signal,
                entry_price=entry_price,
            )
        else:
            base_quantity = config.fixed_quantity

        # Apply strength multiplier
        if self.config.scale_by_strength:
            multiplier = self.config.strength_multipliers.get(
                signal.strength, Decimal("1.0")
            )
            base_quantity *= multiplier

        # Apply confidence scaling
        if self.config.scale_by_confidence:
            base_quantity *= signal.confidence

        # Enforce max position size
        max_value = self.portfolio_value * config.max_position_percent
        if entry_price > 0:
            max_quantity = max_value / entry_price
            base_quantity = min(base_quantity, max_quantity)

        # Round to lot size
        if config.round_to_lot_size and config.lot_size > 0:
            base_quantity = (
                base_quantity / config.lot_size
            ).to_integral_value(rounding=ROUND_DOWN) * config.lot_size

        # Enforce min/max quantity
        base_quantity = max(base_quantity, config.min_quantity)
        if config.max_quantity is not None:
            base_quantity = min(base_quantity, config.max_quantity)

        return base_quantity

    def _calculate_risk_based_size(
        self,
        signal: TradingSignal,
        entry_price: Decimal,
    ) -> Decimal:
        """Calculate position size based on risk per trade.

        Args:
            signal: The trading signal
            entry_price: Entry price

        Returns:
            Position size in shares
        """
        config = self.config.position_sizing

        # Calculate dollar risk allowed
        risk_dollars = self.portfolio_value * config.max_risk_per_trade

        # Calculate risk per share (distance to stop)
        if signal.stop_price:
            risk_per_share = abs(entry_price - signal.stop_price)
        else:
            # Use default stop loss percentage
            risk_per_share = entry_price * self.config.stop_loss.percent

        if risk_per_share > 0:
            return risk_dollars / risk_per_share
        else:
            return Decimal("0")

    def _calculate_volatility_based_size(
        self,
        signal: TradingSignal,
        entry_price: Decimal,
    ) -> Decimal:
        """Calculate position size based on volatility.

        Args:
            signal: The trading signal
            entry_price: Entry price

        Returns:
            Position size in shares
        """
        config = self.config.position_sizing

        # Get ATR/volatility for symbol
        volatility = self.volatility_data.get(signal.symbol, entry_price * Decimal("0.02"))

        # Target volatility contribution (e.g., 1% of portfolio)
        target_vol = self.portfolio_value * config.max_risk_per_trade

        if volatility > 0:
            return target_vol / volatility
        else:
            # Fall back to percent of portfolio
            position_value = self.portfolio_value * config.percent_portfolio
            if entry_price > 0:
                return position_value / entry_price
            return Decimal("0")

    def _calculate_stop_loss(
        self,
        signal: TradingSignal,
        entry_price: Decimal,
    ) -> Optional[Decimal]:
        """Calculate stop loss price.

        Args:
            signal: The trading signal
            entry_price: Entry price

        Returns:
            Stop loss price or None
        """
        config = self.config.stop_loss

        # Use signal's stop price if provided
        if signal.stop_price:
            return signal.stop_price

        # Calculate based on type
        if config.type == StopLossType.FIXED_PERCENT:
            if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                return entry_price * (Decimal("1") - config.percent)
            else:
                return entry_price * (Decimal("1") + config.percent)

        elif config.type == StopLossType.FIXED_AMOUNT:
            if config.amount:
                if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                    return entry_price - config.amount
                else:
                    return entry_price + config.amount

        elif config.type == StopLossType.ATR_BASED:
            atr = self.volatility_data.get(
                signal.symbol,
                entry_price * Decimal("0.02")
            )
            atr_distance = atr * config.atr_multiplier
            if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                return entry_price - atr_distance
            else:
                return entry_price + atr_distance

        elif config.type == StopLossType.TRAILING:
            if config.trail_percent:
                return entry_price * (Decimal("1") - config.trail_percent)
            elif config.trail_amount:
                return entry_price - config.trail_amount

        return None

    def _calculate_take_profit(
        self,
        signal: TradingSignal,
        entry_price: Decimal,
        stop_price: Optional[Decimal],
    ) -> Optional[Decimal]:
        """Calculate take profit price.

        Args:
            signal: The trading signal
            entry_price: Entry price
            stop_price: Stop loss price (for R:R calculation)

        Returns:
            Take profit price or None
        """
        config = self.config.take_profit

        # Use signal's target price if provided
        if signal.target_price:
            return signal.target_price

        # Calculate based on type
        if config.type == TakeProfitType.FIXED_PERCENT:
            if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                return entry_price * (Decimal("1") + config.percent)
            else:
                return entry_price * (Decimal("1") - config.percent)

        elif config.type == TakeProfitType.FIXED_AMOUNT:
            if config.amount:
                if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                    return entry_price + config.amount
                else:
                    return entry_price - config.amount

        elif config.type == TakeProfitType.RISK_REWARD:
            if stop_price:
                risk = abs(entry_price - stop_price)
                reward = risk * config.risk_reward_ratio
                if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                    return entry_price + reward
                else:
                    return entry_price - reward

        return None

    def _validate_order(
        self,
        signal: TradingSignal,
        quantity: Decimal,
        entry_price: Decimal,
        stop_price: Optional[Decimal],
        take_profit_price: Optional[Decimal],
    ) -> OrderValidationResult:
        """Validate the generated order.

        Args:
            signal: Original signal
            quantity: Calculated quantity
            entry_price: Entry price
            stop_price: Stop loss price
            take_profit_price: Take profit price

        Returns:
            OrderValidationResult
        """
        result = OrderValidationResult()

        # Validate symbol
        if not signal.symbol:
            result.is_valid = False
            result.errors.append((
                OrderValidationError.INVALID_SYMBOL,
                "Symbol is required"
            ))

        # Validate quantity
        if quantity <= 0:
            result.is_valid = False
            result.errors.append((
                OrderValidationError.INVALID_QUANTITY,
                f"Quantity must be positive, got {quantity}"
            ))

        # Validate entry price
        if entry_price <= 0:
            result.is_valid = False
            result.errors.append((
                OrderValidationError.INVALID_PRICE,
                f"Entry price must be positive, got {entry_price}"
            ))

        # Validate position value vs portfolio
        position_value = quantity * entry_price
        max_position = self.portfolio_value * self.config.position_sizing.max_position_percent

        if position_value > max_position:
            result.warnings.append(
                f"Position value {position_value} exceeds max {max_position}, "
                f"adjusting quantity"
            )
            result.adjusted_quantity = (max_position / entry_price).to_integral_value(
                rounding=ROUND_DOWN
            )

        # Validate stop loss
        if stop_price is not None:
            if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                if stop_price >= entry_price:
                    result.is_valid = False
                    result.errors.append((
                        OrderValidationError.INVALID_STOP_LOSS,
                        f"Stop loss {stop_price} must be below entry {entry_price} for BUY"
                    ))
            else:
                if stop_price <= entry_price:
                    result.is_valid = False
                    result.errors.append((
                        OrderValidationError.INVALID_STOP_LOSS,
                        f"Stop loss {stop_price} must be above entry {entry_price} for SELL"
                    ))

        # Validate take profit
        if take_profit_price is not None:
            if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                if take_profit_price <= entry_price:
                    result.is_valid = False
                    result.errors.append((
                        OrderValidationError.INVALID_TAKE_PROFIT,
                        f"Take profit {take_profit_price} must be above entry {entry_price} for BUY"
                    ))
            else:
                if take_profit_price >= entry_price:
                    result.is_valid = False
                    result.errors.append((
                        OrderValidationError.INVALID_TAKE_PROFIT,
                        f"Take profit {take_profit_price} must be below entry {entry_price} for SELL"
                    ))

        # Check risk limit
        if stop_price is not None and result.is_valid:
            risk_per_share = abs(entry_price - stop_price)
            final_qty = result.adjusted_quantity or quantity
            total_risk = risk_per_share * final_qty
            max_risk = self.portfolio_value * self.config.position_sizing.max_risk_per_trade

            if total_risk > max_risk * Decimal("2"):  # Allow some buffer
                result.warnings.append(
                    f"Total risk {total_risk} high relative to max {max_risk}"
                )

        return result

    def _signal_to_side(self, signal_type: SignalType) -> OrderSide:
        """Convert signal type to order side.

        Args:
            signal_type: The signal type

        Returns:
            OrderSide (BUY or SELL)
        """
        if signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
            return OrderSide.BUY
        else:
            return OrderSide.SELL

    def _determine_order_type(
        self,
        signal: TradingSignal,
        entry_price: Decimal,
    ) -> Tuple[OrderType, Optional[Decimal]]:
        """Determine order type and limit price.

        Args:
            signal: The trading signal
            entry_price: Entry price

        Returns:
            Tuple of (OrderType, limit_price or None)
        """
        if self.config.use_limit_orders:
            # Calculate limit price with offset
            offset = entry_price * self.config.limit_order_offset
            if signal.signal_type in [SignalType.BUY, SignalType.SCALE_IN]:
                limit_price = entry_price + offset
            else:
                limit_price = entry_price - offset
            return OrderType.LIMIT, limit_price
        else:
            return self.config.default_order_type, None

    def update_portfolio_value(self, value: Decimal):
        """Update the portfolio value.

        Args:
            value: New portfolio value
        """
        self.portfolio_value = value

    def update_price(self, symbol: str, price: Decimal):
        """Update the current price for a symbol.

        Args:
            symbol: Trading symbol
            price: Current market price
        """
        self.current_prices[symbol] = price

    def update_volatility(self, symbol: str, volatility: Decimal):
        """Update the volatility/ATR for a symbol.

        Args:
            symbol: Trading symbol
            volatility: ATR or volatility value
        """
        self.volatility_data[symbol] = volatility
