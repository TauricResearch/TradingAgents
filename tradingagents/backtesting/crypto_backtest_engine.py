"""
Crypto Backtesting Engine
Main backtesting framework for crypto trading strategies with agent validation
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class OrderType(Enum):
    """Order types for trades."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass
class Trade:
    """Represents a single trade execution."""
    timestamp: datetime
    symbol: str
    order_type: OrderType
    price: float
    quantity: float
    commission: float
    slippage: float
    total_cost: float
    portfolio_value_before: float
    portfolio_value_after: float
    reason: str = ""  # Agent's reasoning


@dataclass
class Position:
    """Represents a current position."""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class CryptoBacktestEngine:
    """
    Crypto-specific backtesting engine.

    Handles 24/7 trading, higher volatility, and crypto-specific metrics.
    """

    def __init__(
        self,
        initial_capital: float = 10000,
        commission_rate: float = 0.001,  # 0.1% (higher than stocks)
        slippage_rate: float = 0.002,    # 0.2% (higher than stocks)
        max_position_size: float = 0.20,  # 20% per position
        stop_loss_pct: float = 0.15,     # 15% stop loss
        take_profit_pct: float = 0.30,   # 30% take profit
        risk_per_trade: float = 0.02,    # 2% risk per trade
    ):
        """
        Initialize the crypto backtesting engine.

        Args:
            initial_capital: Starting capital in USD
            commission_rate: Trading commission (0.1% = 0.001)
            slippage_rate: Slippage rate (0.2% = 0.002)
            max_position_size: Maximum position as % of portfolio
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            risk_per_trade: Risk per trade as % of portfolio
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.max_position_size = max_position_size
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.risk_per_trade = risk_per_trade

        # Portfolio state
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.portfolio_value_history: List[Tuple[datetime, float]] = []
        self.trades: List[Trade] = []

        # Performance tracking
        self.max_portfolio_value = initial_capital
        self.max_drawdown = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate current portfolio value.

        Args:
            current_prices: Dictionary of symbol -> current price

        Returns:
            Total portfolio value (cash + positions)
        """
        position_value = sum(
            pos.quantity * current_prices.get(pos.symbol, pos.current_price)
            for pos in self.positions.values()
        )
        return self.cash + position_value

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        portfolio_value: float
    ) -> float:
        """
        Calculate position size based on risk management rules.

        Args:
            symbol: Trading symbol
            entry_price: Entry price
            portfolio_value: Current portfolio value

        Returns:
            Position size in base currency
        """
        # Maximum position based on portfolio %
        max_position_value = portfolio_value * self.max_position_size

        # Risk-based position sizing
        risk_amount = portfolio_value * self.risk_per_trade
        stop_distance = self.stop_loss_pct
        risk_based_quantity = risk_amount / (entry_price * stop_distance)
        risk_based_value = risk_based_quantity * entry_price

        # Use smaller of the two
        position_value = min(max_position_value, risk_based_value)

        # Don't exceed available cash
        available_cash = self.cash * 0.95  # Keep 5% buffer
        position_value = min(position_value, available_cash)

        return position_value / entry_price

    def execute_trade(
        self,
        timestamp: datetime,
        symbol: str,
        order_type: OrderType,
        price: float,
        reason: str = ""
    ) -> Optional[Trade]:
        """
        Execute a trade with commission and slippage.

        Args:
            timestamp: Trade timestamp
            symbol: Trading symbol
            order_type: BUY, SELL, or HOLD
            price: Execution price
            reason: Agent's reasoning for trade

        Returns:
            Trade object if executed, None if rejected
        """
        if order_type == OrderType.HOLD:
            return None

        portfolio_value_before = self.get_portfolio_value({symbol: price})

        if order_type == OrderType.BUY:
            # Check if we already have a position
            if symbol in self.positions:
                return None  # Skip if already in position

            # Calculate position size
            quantity = self.calculate_position_size(symbol, price, portfolio_value_before)

            if quantity <= 0:
                return None  # Insufficient capital

            # Calculate costs
            slippage = price * self.slippage_rate
            execution_price = price * (1 + self.slippage_rate)
            cost = quantity * execution_price
            commission = cost * self.commission_rate
            total_cost = cost + commission

            # Check if we have enough cash
            if total_cost > self.cash:
                return None  # Insufficient funds

            # Execute buy
            self.cash -= total_cost
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=execution_price,
                entry_time=timestamp,
                current_price=price,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0
            )

            portfolio_value_after = self.get_portfolio_value({symbol: price})

            trade = Trade(
                timestamp=timestamp,
                symbol=symbol,
                order_type=order_type,
                price=execution_price,
                quantity=quantity,
                commission=commission,
                slippage=slippage * quantity,
                total_cost=total_cost,
                portfolio_value_before=portfolio_value_before,
                portfolio_value_after=portfolio_value_after,
                reason=reason
            )

            self.trades.append(trade)
            self.total_trades += 1

            return trade

        elif order_type == OrderType.SELL:
            # Check if we have a position to sell
            if symbol not in self.positions:
                return None  # No position to sell

            position = self.positions[symbol]
            quantity = position.quantity

            # Calculate proceeds
            slippage = price * self.slippage_rate
            execution_price = price * (1 - self.slippage_rate)
            proceeds = quantity * execution_price
            commission = proceeds * self.commission_rate
            net_proceeds = proceeds - commission

            # Execute sell
            self.cash += net_proceeds

            # Calculate P&L
            pnl = net_proceeds - (position.entry_price * quantity)
            if pnl > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            # Remove position
            del self.positions[symbol]

            portfolio_value_after = self.get_portfolio_value({symbol: price})

            trade = Trade(
                timestamp=timestamp,
                symbol=symbol,
                order_type=order_type,
                price=execution_price,
                quantity=quantity,
                commission=commission,
                slippage=slippage * quantity,
                total_cost=net_proceeds,
                portfolio_value_before=portfolio_value_before,
                portfolio_value_after=portfolio_value_after,
                reason=reason
            )

            self.trades.append(trade)
            self.total_trades += 1

            return trade

    def check_stop_loss_take_profit(
        self,
        timestamp: datetime,
        current_prices: Dict[str, float]
    ) -> List[Trade]:
        """
        Check all positions for stop loss or take profit triggers.

        Args:
            timestamp: Current timestamp
            current_prices: Current prices for all symbols

        Returns:
            List of trades executed due to SL/TP
        """
        executed_trades = []

        # Create a list of positions to check (to avoid dict size change during iteration)
        positions_to_check = list(self.positions.items())

        for symbol, position in positions_to_check:
            current_price = current_prices.get(symbol)
            if current_price is None:
                continue

            # Update position
            position.current_price = current_price
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
            position.unrealized_pnl_pct = (current_price / position.entry_price - 1)

            # Check stop loss
            if position.unrealized_pnl_pct <= -self.stop_loss_pct:
                trade = self.execute_trade(
                    timestamp, symbol, OrderType.SELL, current_price,
                    reason=f"Stop Loss triggered at {position.unrealized_pnl_pct:.2%}"
                )
                if trade:
                    executed_trades.append(trade)

            # Check take profit
            elif position.unrealized_pnl_pct >= self.take_profit_pct:
                trade = self.execute_trade(
                    timestamp, symbol, OrderType.SELL, current_price,
                    reason=f"Take Profit triggered at {position.unrealized_pnl_pct:.2%}"
                )
                if trade:
                    executed_trades.append(trade)

        return executed_trades

    def update_portfolio_value(self, timestamp: datetime, current_prices: Dict[str, float]):
        """Update portfolio value history and drawdown."""
        portfolio_value = self.get_portfolio_value(current_prices)
        self.portfolio_value_history.append((timestamp, portfolio_value))

        # Update max portfolio value and drawdown
        if portfolio_value > self.max_portfolio_value:
            self.max_portfolio_value = portfolio_value

        current_drawdown = (self.max_portfolio_value - portfolio_value) / self.max_portfolio_value
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

    def get_performance_metrics(self) -> Dict:
        """
        Calculate comprehensive performance metrics.

        Returns:
            Dictionary of performance metrics
        """
        if len(self.portfolio_value_history) < 2:
            return {}

        # Extract values
        timestamps = [t for t, v in self.portfolio_value_history]
        values = np.array([v for t, v in self.portfolio_value_history])

        # Total return
        total_return = (values[-1] - values[0]) / values[0]

        # Calculate returns
        returns = np.diff(values) / values[:-1]

        # Sharpe ratio (assuming 252 trading days, but crypto is 365)
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(365)
        else:
            sharpe_ratio = 0.0

        # Win rate
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0

        # Average trade P&L
        if len(self.trades) > 0:
            trade_pnls = []
            for trade in self.trades:
                if trade.order_type == OrderType.SELL:
                    pnl_pct = (trade.portfolio_value_after - trade.portfolio_value_before) / trade.portfolio_value_before
                    trade_pnls.append(pnl_pct)

            avg_win = np.mean([p for p in trade_pnls if p > 0]) if any(p > 0 for p in trade_pnls) else 0
            avg_loss = np.mean([p for p in trade_pnls if p < 0]) if any(p < 0 for p in trade_pnls) else 0
        else:
            avg_win = 0
            avg_loss = 0

        return {
            'initial_capital': self.initial_capital,
            'final_capital': values[-1],
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown * 100,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'win_rate_pct': win_rate * 100,
            'avg_win': avg_win * 100 if avg_win else 0,
            'avg_loss': avg_loss * 100 if avg_loss else 0,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0,
            'total_commission_paid': sum(t.commission for t in self.trades),
            'total_slippage_cost': sum(t.slippage for t in self.trades),
        }

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame for analysis."""
        if not self.trades:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                'timestamp': t.timestamp,
                'symbol': t.symbol,
                'order_type': t.order_type.value,
                'price': t.price,
                'quantity': t.quantity,
                'commission': t.commission,
                'slippage': t.slippage,
                'total_cost': t.total_cost,
                'portfolio_value_before': t.portfolio_value_before,
                'portfolio_value_after': t.portfolio_value_after,
                'pnl': t.portfolio_value_after - t.portfolio_value_before,
                'reason': t.reason
            }
            for t in self.trades
        ])

    def get_portfolio_history_df(self) -> pd.DataFrame:
        """Get portfolio value history as DataFrame."""
        if not self.portfolio_value_history:
            return pd.DataFrame()

        return pd.DataFrame(
            self.portfolio_value_history,
            columns=['timestamp', 'portfolio_value']
        )
