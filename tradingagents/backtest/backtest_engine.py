"""Backtest Engine for historical strategy replay.

Issue #42: [BT-41] Backtest engine - historical replay, slippage

This module provides backtesting capabilities for trading strategies:
- Historical price data replay
- Realistic slippage modeling
- Commission/fee handling
- Position and portfolio tracking
- Trade execution simulation

Classes:
    SlippageModel: Base class for slippage calculation
    FixedSlippage: Fixed amount slippage
    PercentageSlippage: Percentage-based slippage
    VolumeSlippage: Volume-impact slippage
    CommissionModel: Base class for commission calculation
    FixedCommission: Fixed per-trade commission
    PercentageCommission: Percentage-based commission
    TieredCommission: Tiered commission based on trade value
    BacktestConfig: Configuration for backtest
    BacktestPosition: Position tracking during backtest
    BacktestTrade: Individual trade record
    BacktestResult: Complete backtest result
    BacktestEngine: Main backtest engine

Example:
    >>> from tradingagents.backtest import BacktestEngine, BacktestConfig
    >>> from decimal import Decimal
    >>>
    >>> config = BacktestConfig(
    ...     initial_capital=Decimal("100000"),
    ...     start_date=datetime(2023, 1, 1),
    ...     end_date=datetime(2023, 12, 31),
    ... )
    >>> engine = BacktestEngine(config)
    >>> result = engine.run(price_data, signals)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Optional, Protocol
import logging


logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


# ============================================================================
# Enums
# ============================================================================

class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type for backtest."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class FillStatus(Enum):
    """Fill status for orders."""
    UNFILLED = "unfilled"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ============================================================================
# Price Data Types
# ============================================================================

@dataclass
class OHLCV:
    """OHLCV bar data.

    Attributes:
        timestamp: Bar timestamp
        open: Open price
        high: High price
        low: Low price
        close: Close price
        volume: Volume
        symbol: Optional symbol identifier
    """
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = ZERO
    symbol: str = ""

    def __post_init__(self):
        """Convert numeric types to Decimal."""
        for field_name in ["open", "high", "low", "close", "volume"]:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                setattr(self, field_name, Decimal(str(value)))


@dataclass
class Signal:
    """Trading signal.

    Attributes:
        timestamp: Signal timestamp
        symbol: Symbol to trade
        side: Buy or sell
        quantity: Quantity to trade (0 for position sizing by engine)
        price: Target price (for limit orders)
        order_type: Order type
        confidence: Signal confidence (0-1)
        metadata: Additional signal data
    """
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: Decimal = ZERO
    price: Decimal = ZERO
    order_type: OrderType = OrderType.MARKET
    confidence: Decimal = ONE
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Slippage Models
# ============================================================================

class SlippageModel(ABC):
    """Base class for slippage calculation."""

    @abstractmethod
    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        side: OrderSide,
        volume: Decimal,
    ) -> Decimal:
        """Calculate slippage amount.

        Args:
            price: Order price
            quantity: Order quantity
            side: Order side
            volume: Bar volume

        Returns:
            Slippage amount (added to buy, subtracted from sell)
        """
        pass


class NoSlippage(SlippageModel):
    """No slippage model."""

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        side: OrderSide,
        volume: Decimal,
    ) -> Decimal:
        """No slippage."""
        return ZERO


class FixedSlippage(SlippageModel):
    """Fixed amount slippage per share.

    Attributes:
        amount: Fixed slippage amount per share
    """

    def __init__(self, amount: Decimal):
        """Initialize with fixed amount.

        Args:
            amount: Slippage per share
        """
        self.amount = Decimal(str(amount))

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        side: OrderSide,
        volume: Decimal,
    ) -> Decimal:
        """Calculate fixed slippage."""
        return self.amount


class PercentageSlippage(SlippageModel):
    """Percentage-based slippage.

    Attributes:
        percentage: Slippage as percentage of price (e.g., 0.1 = 0.1%)
    """

    def __init__(self, percentage: Decimal):
        """Initialize with percentage.

        Args:
            percentage: Slippage percentage (0.1 = 0.1%)
        """
        self.percentage = Decimal(str(percentage))

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        side: OrderSide,
        volume: Decimal,
    ) -> Decimal:
        """Calculate percentage slippage."""
        return price * self.percentage / HUNDRED


class VolumeSlippage(SlippageModel):
    """Volume-impact slippage model.

    Slippage increases with order size relative to volume.

    Attributes:
        base_percentage: Base slippage percentage
        volume_impact: Impact factor for volume (higher = more slippage)
        max_percentage: Maximum slippage percentage
    """

    def __init__(
        self,
        base_percentage: Decimal = Decimal("0.05"),
        volume_impact: Decimal = Decimal("0.1"),
        max_percentage: Decimal = Decimal("1.0"),
    ):
        """Initialize volume slippage model.

        Args:
            base_percentage: Base slippage (%)
            volume_impact: Volume impact factor
            max_percentage: Maximum slippage cap (%)
        """
        self.base_percentage = Decimal(str(base_percentage))
        self.volume_impact = Decimal(str(volume_impact))
        self.max_percentage = Decimal(str(max_percentage))

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        side: OrderSide,
        volume: Decimal,
    ) -> Decimal:
        """Calculate volume-based slippage."""
        if volume <= ZERO:
            # No volume data, use base slippage
            return price * self.base_percentage / HUNDRED

        # Calculate volume participation
        participation = quantity / volume

        # Calculate slippage percentage
        slippage_pct = self.base_percentage + (participation * self.volume_impact * HUNDRED)

        # Cap at maximum
        slippage_pct = min(slippage_pct, self.max_percentage)

        return price * slippage_pct / HUNDRED


# ============================================================================
# Commission Models
# ============================================================================

class CommissionModel(ABC):
    """Base class for commission calculation."""

    @abstractmethod
    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        trade_value: Decimal,
    ) -> Decimal:
        """Calculate commission.

        Args:
            price: Trade price
            quantity: Trade quantity
            trade_value: Total trade value

        Returns:
            Commission amount
        """
        pass


class NoCommission(CommissionModel):
    """No commission model."""

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        trade_value: Decimal,
    ) -> Decimal:
        """No commission."""
        return ZERO


class FixedCommission(CommissionModel):
    """Fixed per-trade commission.

    Attributes:
        amount: Fixed commission per trade
        minimum: Minimum commission
    """

    def __init__(
        self,
        amount: Decimal,
        minimum: Decimal = ZERO,
    ):
        """Initialize with fixed amount.

        Args:
            amount: Commission per trade
            minimum: Minimum commission
        """
        self.amount = Decimal(str(amount))
        self.minimum = Decimal(str(minimum))

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        trade_value: Decimal,
    ) -> Decimal:
        """Calculate fixed commission."""
        return max(self.amount, self.minimum)


class PerShareCommission(CommissionModel):
    """Per-share commission.

    Attributes:
        per_share: Commission per share
        minimum: Minimum commission per trade
        maximum: Maximum commission per trade
    """

    def __init__(
        self,
        per_share: Decimal,
        minimum: Decimal = ZERO,
        maximum: Decimal = Decimal("Infinity"),
    ):
        """Initialize per-share commission.

        Args:
            per_share: Commission per share
            minimum: Minimum per trade
            maximum: Maximum per trade
        """
        self.per_share = Decimal(str(per_share))
        self.minimum = Decimal(str(minimum))
        self.maximum = Decimal(str(maximum)) if maximum != Decimal("Infinity") else None

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        trade_value: Decimal,
    ) -> Decimal:
        """Calculate per-share commission."""
        commission = self.per_share * abs(quantity)
        commission = max(commission, self.minimum)
        if self.maximum is not None:
            commission = min(commission, self.maximum)
        return commission


class PercentageCommission(CommissionModel):
    """Percentage-based commission.

    Attributes:
        percentage: Commission as percentage of trade value
        minimum: Minimum commission
    """

    def __init__(
        self,
        percentage: Decimal,
        minimum: Decimal = ZERO,
    ):
        """Initialize percentage commission.

        Args:
            percentage: Commission percentage (e.g., 0.1 = 0.1%)
            minimum: Minimum commission
        """
        self.percentage = Decimal(str(percentage))
        self.minimum = Decimal(str(minimum))

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        trade_value: Decimal,
    ) -> Decimal:
        """Calculate percentage commission."""
        commission = abs(trade_value) * self.percentage / HUNDRED
        return max(commission, self.minimum)


class TieredCommission(CommissionModel):
    """Tiered commission based on trade value.

    Attributes:
        tiers: List of (threshold, percentage) tuples
        minimum: Minimum commission
    """

    def __init__(
        self,
        tiers: list[tuple[Decimal, Decimal]],
        minimum: Decimal = ZERO,
    ):
        """Initialize tiered commission.

        Args:
            tiers: List of (threshold, percentage) - sorted ascending
            minimum: Minimum commission
        """
        self.tiers = sorted(
            [(Decimal(str(t)), Decimal(str(p))) for t, p in tiers],
            key=lambda x: x[0],
        )
        self.minimum = Decimal(str(minimum))

    def calculate(
        self,
        price: Decimal,
        quantity: Decimal,
        trade_value: Decimal,
    ) -> Decimal:
        """Calculate tiered commission."""
        abs_value = abs(trade_value)

        # Find applicable tier
        percentage = self.tiers[0][1] if self.tiers else ZERO
        for threshold, pct in self.tiers:
            if abs_value >= threshold:
                percentage = pct
            else:
                break

        commission = abs_value * percentage / HUNDRED
        return max(commission, self.minimum)


# ============================================================================
# Backtest Data Classes
# ============================================================================

@dataclass
class BacktestConfig:
    """Configuration for backtest.

    Attributes:
        initial_capital: Starting capital
        start_date: Backtest start date
        end_date: Backtest end date
        slippage_model: Slippage model to use
        commission_model: Commission model to use
        position_sizing: Position sizing mode
        max_position_pct: Maximum position as % of portfolio
        min_trade_value: Minimum trade value
        allow_shorting: Whether to allow short positions
        margin_rate: Margin rate for leveraged trades
        risk_free_rate: Risk-free rate for Sharpe calculation
        benchmark_symbol: Benchmark symbol for comparison
        rebalance_frequency: Rebalance frequency in days (0 = no rebalance)
    """
    initial_capital: Decimal = Decimal("100000")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    slippage_model: SlippageModel = field(default_factory=NoSlippage)
    commission_model: CommissionModel = field(default_factory=NoCommission)
    position_sizing: str = "equal"  # equal, risk_parity, kelly
    max_position_pct: Decimal = Decimal("20")  # 20% max per position
    min_trade_value: Decimal = Decimal("100")
    allow_shorting: bool = False
    margin_rate: Decimal = Decimal("50")  # 50% margin
    risk_free_rate: Decimal = Decimal("0.05")  # 5% annual
    benchmark_symbol: str = "SPY"
    rebalance_frequency: int = 0  # 0 = no automatic rebalance


@dataclass
class BacktestPosition:
    """Position during backtest.

    Attributes:
        symbol: Position symbol
        quantity: Current quantity (negative for short)
        average_cost: Average cost basis
        current_price: Current market price
        unrealized_pnl: Unrealized P&L
        realized_pnl: Realized P&L from closed trades
        opened_at: Position open timestamp
        last_updated: Last update timestamp
    """
    symbol: str
    quantity: Decimal = ZERO
    average_cost: Decimal = ZERO
    current_price: Decimal = ZERO
    unrealized_pnl: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    opened_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    @property
    def market_value(self) -> Decimal:
        """Get current market value."""
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> Decimal:
        """Get total cost basis."""
        return self.quantity * self.average_cost

    @property
    def is_long(self) -> bool:
        """Check if long position."""
        return self.quantity > ZERO

    @property
    def is_short(self) -> bool:
        """Check if short position."""
        return self.quantity < ZERO

    def update_price(self, price: Decimal, timestamp: datetime) -> None:
        """Update current price and unrealized P&L.

        Args:
            price: New price
            timestamp: Update timestamp
        """
        self.current_price = price
        self.unrealized_pnl = (price - self.average_cost) * self.quantity
        self.last_updated = timestamp


@dataclass
class BacktestTrade:
    """Individual trade record.

    Attributes:
        trade_id: Unique trade ID
        timestamp: Trade timestamp
        symbol: Symbol traded
        side: Buy or sell
        quantity: Quantity traded
        price: Execution price (after slippage)
        base_price: Price before slippage
        slippage: Slippage amount
        commission: Commission paid
        trade_value: Total trade value
        signal_confidence: Original signal confidence
        position_after: Position quantity after trade
        cash_after: Cash balance after trade
        pnl: Realized P&L (for closing trades)
    """
    trade_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = ZERO
    price: Decimal = ZERO
    base_price: Decimal = ZERO
    slippage: Decimal = ZERO
    commission: Decimal = ZERO
    trade_value: Decimal = ZERO
    signal_confidence: Decimal = ONE
    position_after: Decimal = ZERO
    cash_after: Decimal = ZERO
    pnl: Decimal = ZERO


@dataclass
class BacktestSnapshot:
    """Portfolio snapshot at a point in time.

    Attributes:
        timestamp: Snapshot timestamp
        cash: Cash balance
        positions_value: Total value of positions
        total_value: Total portfolio value
        positions: Current positions
        drawdown: Current drawdown from peak
        peak_value: Peak portfolio value
    """
    timestamp: datetime
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    positions: dict[str, BacktestPosition] = field(default_factory=dict)
    drawdown: Decimal = ZERO
    peak_value: Decimal = ZERO


@dataclass
class BacktestResult:
    """Complete backtest result.

    Attributes:
        config: Backtest configuration
        start_date: Actual start date
        end_date: Actual end date
        initial_capital: Starting capital
        final_value: Ending portfolio value
        total_return: Total return percentage
        annualized_return: Annualized return
        sharpe_ratio: Sharpe ratio
        sortino_ratio: Sortino ratio
        max_drawdown: Maximum drawdown
        win_rate: Win rate
        profit_factor: Profit factor
        total_trades: Number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        avg_trade_pnl: Average P&L per trade
        avg_win: Average winning trade
        avg_loss: Average losing trade
        max_win: Largest winning trade
        max_loss: Largest losing trade
        total_commission: Total commission paid
        total_slippage: Total slippage cost
        trades: List of all trades
        snapshots: Portfolio snapshots over time
        daily_returns: Daily return series
        benchmark_return: Benchmark return (if available)
        alpha: Alpha vs benchmark
        beta: Beta vs benchmark
        errors: Any errors during backtest
    """
    config: BacktestConfig = field(default_factory=BacktestConfig)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_capital: Decimal = ZERO
    final_value: Decimal = ZERO
    total_return: Decimal = ZERO
    annualized_return: Decimal = ZERO
    sharpe_ratio: Decimal = ZERO
    sortino_ratio: Decimal = ZERO
    max_drawdown: Decimal = ZERO
    win_rate: Decimal = ZERO
    profit_factor: Decimal = ZERO
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_trade_pnl: Decimal = ZERO
    avg_win: Decimal = ZERO
    avg_loss: Decimal = ZERO
    max_win: Decimal = ZERO
    max_loss: Decimal = ZERO
    total_commission: Decimal = ZERO
    total_slippage: Decimal = ZERO
    trades: list[BacktestTrade] = field(default_factory=list)
    snapshots: list[BacktestSnapshot] = field(default_factory=list)
    daily_returns: list[Decimal] = field(default_factory=list)
    benchmark_return: Decimal = ZERO
    alpha: Decimal = ZERO
    beta: Decimal = ZERO
    errors: list[str] = field(default_factory=list)


# ============================================================================
# Backtest Engine
# ============================================================================

class BacktestEngine:
    """Main backtest engine for historical strategy replay.

    Attributes:
        config: Backtest configuration
        cash: Current cash balance
        positions: Current positions
        trades: Trade history
        snapshots: Portfolio snapshots
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        """Initialize backtest engine.

        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        self.reset()

    def reset(self) -> None:
        """Reset engine state."""
        self.cash = self.config.initial_capital
        self.positions: dict[str, BacktestPosition] = {}
        self.trades: list[BacktestTrade] = []
        self.snapshots: list[BacktestSnapshot] = []
        self._trade_counter = 0
        self._peak_value = self.config.initial_capital
        self._current_timestamp: Optional[datetime] = None
        self._price_data: dict[str, list[OHLCV]] = {}
        self._current_prices: dict[str, Decimal] = {}

    def run(
        self,
        price_data: dict[str, list[OHLCV]],
        signals: list[Signal],
        strategy_callback: Optional[Callable[[datetime, dict[str, OHLCV]], list[Signal]]] = None,
    ) -> BacktestResult:
        """Run backtest.

        Args:
            price_data: Dict of symbol -> list of OHLCV bars
            signals: List of trading signals (pre-generated)
            strategy_callback: Optional callback for dynamic signal generation

        Returns:
            BacktestResult with all metrics
        """
        self.reset()
        self._price_data = price_data

        # Determine date range
        all_timestamps = set()
        for bars in price_data.values():
            for bar in bars:
                all_timestamps.add(bar.timestamp)

        if not all_timestamps:
            return self._create_result([])

        sorted_timestamps = sorted(all_timestamps)
        start_date = self.config.start_date or sorted_timestamps[0]
        end_date = self.config.end_date or sorted_timestamps[-1]

        # Filter timestamps to date range
        timestamps = [t for t in sorted_timestamps if start_date <= t <= end_date]

        if not timestamps:
            return self._create_result([])

        # Index signals by timestamp
        signal_index: dict[datetime, list[Signal]] = {}
        for signal in signals:
            if start_date <= signal.timestamp <= end_date:
                if signal.timestamp not in signal_index:
                    signal_index[signal.timestamp] = []
                signal_index[signal.timestamp].append(signal)

        # Main replay loop
        errors = []
        for timestamp in timestamps:
            self._current_timestamp = timestamp

            # Get current prices
            current_bars = self._get_bars_at(timestamp)
            self._update_prices(current_bars)

            # Process signals for this timestamp
            timestamp_signals = signal_index.get(timestamp, [])

            # Also get signals from callback if provided
            if strategy_callback:
                try:
                    callback_signals = strategy_callback(timestamp, current_bars)
                    timestamp_signals.extend(callback_signals)
                except Exception as e:
                    errors.append(f"Strategy callback error at {timestamp}: {e}")

            # Execute signals
            for signal in timestamp_signals:
                try:
                    self._execute_signal(signal, current_bars)
                except Exception as e:
                    errors.append(f"Signal execution error at {timestamp}: {e}")

            # Take snapshot
            self._take_snapshot(timestamp)

        result = self._create_result(errors)
        return result

    def _get_bars_at(self, timestamp: datetime) -> dict[str, OHLCV]:
        """Get OHLCV bars at timestamp.

        Args:
            timestamp: Target timestamp

        Returns:
            Dict of symbol -> OHLCV
        """
        bars = {}
        for symbol, bar_list in self._price_data.items():
            for bar in bar_list:
                if bar.timestamp == timestamp:
                    bars[symbol] = bar
                    break
        return bars

    def _update_prices(self, bars: dict[str, OHLCV]) -> None:
        """Update current prices and position values.

        Args:
            bars: Current price bars
        """
        for symbol, bar in bars.items():
            self._current_prices[symbol] = bar.close

            if symbol in self.positions:
                self.positions[symbol].update_price(bar.close, bar.timestamp)

    def _execute_signal(self, signal: Signal, bars: dict[str, OHLCV]) -> Optional[BacktestTrade]:
        """Execute a trading signal.

        Args:
            signal: Signal to execute
            bars: Current price bars

        Returns:
            BacktestTrade if executed, None if rejected
        """
        symbol = signal.symbol

        # Check if we have price data
        if symbol not in bars:
            logger.warning(f"No price data for {symbol} at {signal.timestamp}")
            return None

        bar = bars[symbol]

        # Determine quantity
        quantity = self._calculate_quantity(signal, bar)
        if quantity == ZERO:
            return None

        # Get execution price with slippage
        base_price = bar.close
        if signal.order_type == OrderType.LIMIT:
            base_price = signal.price

        slippage = self.config.slippage_model.calculate(
            base_price, quantity, signal.side, bar.volume
        )

        if signal.side == OrderSide.BUY:
            exec_price = base_price + slippage
        else:
            exec_price = base_price - slippage

        # Calculate trade value and commission
        trade_value = exec_price * quantity
        commission = self.config.commission_model.calculate(
            exec_price, quantity, trade_value
        )

        # Check if we can afford the trade
        if signal.side == OrderSide.BUY:
            total_cost = trade_value + commission
            if total_cost > self.cash:
                # Reduce quantity to what we can afford
                available = self.cash - commission
                if available <= ZERO:
                    return None
                quantity = (available / exec_price).quantize(Decimal("1"))
                if quantity <= ZERO:
                    return None
                trade_value = exec_price * quantity
                commission = self.config.commission_model.calculate(
                    exec_price, quantity, trade_value
                )
                total_cost = trade_value + commission

            self.cash -= total_cost
        else:
            # Sell - check position
            current_position = self.positions.get(symbol)
            if current_position is None or current_position.quantity <= ZERO:
                if not self.config.allow_shorting:
                    return None
            elif quantity > current_position.quantity:
                # Can only sell what we have
                quantity = current_position.quantity
                trade_value = exec_price * quantity
                commission = self.config.commission_model.calculate(
                    exec_price, quantity, trade_value
                )

            self.cash += trade_value - commission

        # Update position
        pnl = self._update_position(signal, quantity, exec_price)

        # Create trade record
        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=f"BT-{self._trade_counter:06d}",
            timestamp=signal.timestamp,
            symbol=symbol,
            side=signal.side,
            quantity=quantity,
            price=exec_price,
            base_price=base_price,
            slippage=slippage * quantity,
            commission=commission,
            trade_value=trade_value,
            signal_confidence=signal.confidence,
            position_after=self.positions.get(symbol, BacktestPosition(symbol)).quantity,
            cash_after=self.cash,
            pnl=pnl,
        )

        self.trades.append(trade)
        return trade

    def _calculate_quantity(self, signal: Signal, bar: OHLCV) -> Decimal:
        """Calculate trade quantity based on position sizing.

        Args:
            signal: Trading signal
            bar: Current price bar

        Returns:
            Quantity to trade
        """
        if signal.quantity > ZERO:
            return signal.quantity

        # Position sizing based on config
        portfolio_value = self._get_portfolio_value()
        max_position_value = portfolio_value * self.config.max_position_pct / HUNDRED

        if self.config.position_sizing == "equal":
            # Equal weight for each position
            num_positions = max(len(self.positions), 5)  # Assume at least 5 positions
            target_value = portfolio_value / Decimal(num_positions)
            target_value = min(target_value, max_position_value)
        else:
            target_value = max_position_value

        # Check minimum trade value
        if target_value < self.config.min_trade_value:
            return ZERO

        quantity = (target_value / bar.close).quantize(Decimal("1"))
        return max(quantity, ZERO)

    def _update_position(
        self,
        signal: Signal,
        quantity: Decimal,
        price: Decimal,
    ) -> Decimal:
        """Update position after trade.

        Args:
            signal: Trading signal
            quantity: Trade quantity
            price: Execution price

        Returns:
            Realized P&L
        """
        symbol = signal.symbol
        pnl = ZERO

        if symbol not in self.positions:
            self.positions[symbol] = BacktestPosition(
                symbol=symbol,
                opened_at=signal.timestamp,
            )

        position = self.positions[symbol]

        if signal.side == OrderSide.BUY:
            # Buying
            if position.quantity >= ZERO:
                # Adding to long or opening new long
                total_cost = position.quantity * position.average_cost + quantity * price
                new_quantity = position.quantity + quantity
                position.average_cost = total_cost / new_quantity if new_quantity > ZERO else ZERO
                position.quantity = new_quantity
            else:
                # Covering short
                pnl = (position.average_cost - price) * min(quantity, abs(position.quantity))
                position.realized_pnl += pnl
                position.quantity += quantity
        else:
            # Selling
            if position.quantity > ZERO:
                # Closing long
                pnl = (price - position.average_cost) * min(quantity, position.quantity)
                position.realized_pnl += pnl
                position.quantity -= quantity
            else:
                # Adding to short or opening new short
                total_cost = abs(position.quantity) * position.average_cost + quantity * price
                new_quantity = position.quantity - quantity
                position.average_cost = total_cost / abs(new_quantity) if new_quantity != ZERO else price
                position.quantity = new_quantity

        position.last_updated = signal.timestamp

        # Clean up closed positions
        if position.quantity == ZERO:
            del self.positions[symbol]

        return pnl

    def _get_portfolio_value(self) -> Decimal:
        """Get total portfolio value.

        Returns:
            Total value (cash + positions)
        """
        positions_value = sum(p.market_value for p in self.positions.values())
        return self.cash + positions_value

    def _take_snapshot(self, timestamp: datetime) -> None:
        """Take portfolio snapshot.

        Args:
            timestamp: Snapshot timestamp
        """
        positions_value = sum(p.market_value for p in self.positions.values())
        total_value = self.cash + positions_value

        # Update peak and drawdown
        if total_value > self._peak_value:
            self._peak_value = total_value

        drawdown = (self._peak_value - total_value) / self._peak_value * HUNDRED if self._peak_value > ZERO else ZERO

        snapshot = BacktestSnapshot(
            timestamp=timestamp,
            cash=self.cash,
            positions_value=positions_value,
            total_value=total_value,
            positions={k: BacktestPosition(
                symbol=v.symbol,
                quantity=v.quantity,
                average_cost=v.average_cost,
                current_price=v.current_price,
                unrealized_pnl=v.unrealized_pnl,
                realized_pnl=v.realized_pnl,
            ) for k, v in self.positions.items()},
            drawdown=drawdown,
            peak_value=self._peak_value,
        )

        self.snapshots.append(snapshot)

    def _create_result(self, errors: list[str]) -> BacktestResult:
        """Create backtest result with calculated metrics.

        Args:
            errors: List of errors during backtest

        Returns:
            Complete BacktestResult
        """
        if not self.snapshots:
            return BacktestResult(
                config=self.config,
                initial_capital=self.config.initial_capital,
                final_value=self.config.initial_capital,
                errors=errors,
            )

        # Basic metrics
        start_date = self.snapshots[0].timestamp
        end_date = self.snapshots[-1].timestamp
        final_value = self.snapshots[-1].total_value
        total_return = (final_value - self.config.initial_capital) / self.config.initial_capital * HUNDRED

        # Calculate trading days and annualized return
        trading_days = len(self.snapshots)
        years = Decimal(str((end_date - start_date).days)) / Decimal("365")
        if years > ZERO:
            annualized_return = ((final_value / self.config.initial_capital) ** (ONE / years) - ONE) * HUNDRED
        else:
            annualized_return = ZERO

        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(self.snapshots)):
            prev_value = self.snapshots[i - 1].total_value
            curr_value = self.snapshots[i].total_value
            if prev_value > ZERO:
                daily_returns.append((curr_value - prev_value) / prev_value)
            else:
                daily_returns.append(ZERO)

        # Sharpe ratio
        if daily_returns:
            avg_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)
            std_dev = variance ** Decimal("0.5")
            daily_rf = self.config.risk_free_rate / Decimal("252")
            if std_dev > ZERO:
                sharpe_ratio = (avg_return - daily_rf) / std_dev * Decimal("252").sqrt()
            else:
                sharpe_ratio = ZERO
        else:
            sharpe_ratio = ZERO

        # Sortino ratio (downside deviation)
        negative_returns = [r for r in daily_returns if r < ZERO]
        if negative_returns:
            downside_variance = sum(r ** 2 for r in negative_returns) / len(negative_returns)
            downside_dev = downside_variance ** Decimal("0.5")
            daily_rf = self.config.risk_free_rate / Decimal("252")
            if downside_dev > ZERO:
                avg_return = sum(daily_returns) / len(daily_returns) if daily_returns else ZERO
                sortino_ratio = (avg_return - daily_rf) / downside_dev * Decimal("252").sqrt()
            else:
                sortino_ratio = ZERO
        else:
            sortino_ratio = ZERO

        # Maximum drawdown
        max_drawdown = max((s.drawdown for s in self.snapshots), default=ZERO)

        # Trade statistics
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t.pnl > ZERO)
        losing_trades = sum(1 for t in self.trades if t.pnl < ZERO)
        win_rate = Decimal(str(winning_trades)) / Decimal(str(total_trades)) * HUNDRED if total_trades > 0 else ZERO

        wins = [t.pnl for t in self.trades if t.pnl > ZERO]
        losses = [t.pnl for t in self.trades if t.pnl < ZERO]

        avg_win = sum(wins) / len(wins) if wins else ZERO
        avg_loss = sum(losses) / len(losses) if losses else ZERO
        max_win = max(wins) if wins else ZERO
        max_loss = min(losses) if losses else ZERO  # Most negative

        total_wins = sum(wins)
        total_losses = abs(sum(losses))
        profit_factor = total_wins / total_losses if total_losses > ZERO else ZERO

        avg_trade_pnl = sum(t.pnl for t in self.trades) / total_trades if total_trades > 0 else ZERO

        # Total costs
        total_commission = sum(t.commission for t in self.trades)
        total_slippage = sum(t.slippage for t in self.trades)

        return BacktestResult(
            config=self.config,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.config.initial_capital,
            final_value=final_value,
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_pnl=avg_trade_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_win=max_win,
            max_loss=max_loss,
            total_commission=total_commission,
            total_slippage=total_slippage,
            trades=self.trades,
            snapshots=self.snapshots,
            daily_returns=daily_returns,
            errors=errors,
        )

    def get_position(self, symbol: str) -> Optional[BacktestPosition]:
        """Get current position for symbol.

        Args:
            symbol: Symbol to look up

        Returns:
            Position if exists
        """
        return self.positions.get(symbol)

    def get_cash(self) -> Decimal:
        """Get current cash balance.

        Returns:
            Cash balance
        """
        return self.cash

    def get_portfolio_value(self) -> Decimal:
        """Get current portfolio value.

        Returns:
            Total portfolio value
        """
        return self._get_portfolio_value()


# ============================================================================
# Factory Functions
# ============================================================================

def create_backtest_engine(
    initial_capital: Decimal = Decimal("100000"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    slippage: Optional[SlippageModel] = None,
    commission: Optional[CommissionModel] = None,
    **kwargs,
) -> BacktestEngine:
    """Create a configured backtest engine.

    Args:
        initial_capital: Starting capital
        start_date: Backtest start date
        end_date: Backtest end date
        slippage: Slippage model
        commission: Commission model
        **kwargs: Additional config options

    Returns:
        Configured BacktestEngine
    """
    config = BacktestConfig(
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
        slippage_model=slippage or NoSlippage(),
        commission_model=commission or NoCommission(),
        **{k: v for k, v in kwargs.items() if hasattr(BacktestConfig, k)},
    )

    return BacktestEngine(config)
