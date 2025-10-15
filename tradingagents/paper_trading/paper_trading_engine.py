"""
Paper Trading Engine
Live trading simulation with real-time market data but virtual capital
"""
import ccxt
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import json
import os


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class PaperOrder:
    """Paper trading order."""
    order_id: str
    symbol: str
    side: OrderSide
    amount: float
    price: float
    timestamp: datetime
    status: OrderStatus
    filled_price: Optional[float] = None
    filled_timestamp: Optional[datetime] = None
    reason: str = ""


@dataclass
class PaperPosition:
    """Paper trading position."""
    symbol: str
    amount: float
    entry_price: float
    entry_time: datetime
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class PaperTradingEngine:
    """
    Paper trading engine for live simulation.

    Features:
    - Real-time price updates
    - Virtual order execution
    - Position tracking
    - Performance monitoring
    - Safety controls
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        initial_capital: float = 10000,
        commission_rate: float = 0.001,
        max_position_size: float = 0.20,
        max_daily_loss: float = 0.05,
        stop_loss_pct: float = 0.15,
        take_profit_pct: float = 0.30,
        update_interval: int = 60,  # seconds
        data_dir: str = "./paper_trading_data"
    ):
        """
        Initialize paper trading engine.

        Args:
            exchange_id: Exchange to connect to
            initial_capital: Starting virtual capital
            commission_rate: Trading commission
            max_position_size: Max position as % of portfolio
            max_daily_loss: Max daily loss (kill switch)
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            update_interval: Price update interval in seconds
            data_dir: Directory to save trading data
        """
        self.exchange_id = exchange_id
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.update_interval = update_interval
        self.data_dir = data_dir

        # Initialize exchange
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'enableRateLimit': True,
        })
        self.exchange.load_markets()

        # Portfolio state
        self.cash = initial_capital
        self.positions: Dict[str, PaperPosition] = {}
        self.orders: List[PaperOrder] = []
        self.portfolio_value_history: List[Dict] = []

        # Trading state
        self.is_running = False
        self.current_prices: Dict[str, float] = {}
        self.daily_start_value = initial_capital
        self.daily_pnl = 0.0

        # Strategy callback
        self.strategy_func: Optional[Callable] = None

        # Create data directory
        os.makedirs(data_dir, exist_ok=True)

        # Load previous state if exists
        self._load_state()

    def set_strategy(self, strategy_func: Callable):
        """
        Set trading strategy function.

        Args:
            strategy_func: Function(engine, symbol, current_price) -> OrderSide or None
        """
        self.strategy_func = strategy_func

    def start(self, symbols: List[str]):
        """
        Start paper trading.

        Args:
            symbols: List of trading pairs to trade
        """
        if self.is_running:
            print("Paper trading already running!")
            return

        if not self.strategy_func:
            print("Error: No strategy set! Use set_strategy() first.")
            return

        self.is_running = True
        self.symbols = symbols

        print(f"\n{'='*60}")
        print(f"PAPER TRADING STARTED")
        print(f"{'='*60}")
        print(f"Exchange: {self.exchange_id}")
        print(f"Symbols: {', '.join(symbols)}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Update Interval: {self.update_interval}s")
        print(f"{'='*60}\n")

        # Start trading loop in separate thread
        self.trading_thread = threading.Thread(target=self._trading_loop, daemon=True)
        self.trading_thread.start()

    def stop(self):
        """Stop paper trading."""
        if not self.is_running:
            return

        print("\n" + "="*60)
        print("STOPPING PAPER TRADING...")
        print("="*60)

        self.is_running = False

        # Close all positions
        self._close_all_positions()

        # Save state
        self._save_state()

        # Print final stats
        self._print_summary()

    def _trading_loop(self):
        """Main trading loop (runs in separate thread)."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Trading loop started")

        while self.is_running:
            try:
                # Update prices
                self._update_prices()

                # Check daily loss limit
                if self._check_kill_switch():
                    print("\n⚠️  KILL SWITCH ACTIVATED - Daily loss limit exceeded!")
                    self.stop()
                    break

                # Check stop loss / take profit
                self._check_stop_loss_take_profit()

                # Run strategy for each symbol
                for symbol in self.symbols:
                    if symbol in self.current_prices:
                        self._execute_strategy(symbol)

                # Update portfolio value
                self._update_portfolio_value()

                # Save state periodically
                self._save_state()

                # Sleep until next update
                time.sleep(self.update_interval)

            except Exception as e:
                print(f"Error in trading loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(self.update_interval)

    def _update_prices(self):
        """Fetch current prices for all symbols."""
        for symbol in self.symbols:
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                self.current_prices[symbol] = ticker['last']
            except Exception as e:
                print(f"Error fetching price for {symbol}: {e}")

    def _execute_strategy(self, symbol: str):
        """Execute strategy for a symbol."""
        try:
            current_price = self.current_prices[symbol]

            # Call strategy
            decision = self.strategy_func(self, symbol, current_price)

            if decision == OrderSide.BUY:
                self._place_buy_order(symbol, current_price, "Strategy buy signal")
            elif decision == OrderSide.SELL:
                self._place_sell_order(symbol, current_price, "Strategy sell signal")

        except Exception as e:
            print(f"Error executing strategy for {symbol}: {e}")

    def _place_buy_order(self, symbol: str, price: float, reason: str = ""):
        """Place virtual buy order."""
        # Check if already have position
        if symbol in self.positions:
            return

        # Calculate position size
        portfolio_value = self.get_portfolio_value()
        max_position_value = portfolio_value * self.max_position_size
        available_cash = self.cash * 0.95  # 5% buffer

        position_value = min(max_position_value, available_cash)
        amount = position_value / price

        if amount <= 0:
            return

        # Calculate costs
        cost = amount * price
        commission = cost * self.commission_rate
        total_cost = cost + commission

        if total_cost > self.cash:
            return

        # Execute order
        self.cash -= total_cost

        # Create position
        self.positions[symbol] = PaperPosition(
            symbol=symbol,
            amount=amount,
            entry_price=price,
            entry_time=datetime.now(),
            current_price=price,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0
        )

        # Record order
        order = PaperOrder(
            order_id=f"BUY-{symbol}-{int(time.time())}",
            symbol=symbol,
            side=OrderSide.BUY,
            amount=amount,
            price=price,
            timestamp=datetime.now(),
            status=OrderStatus.FILLED,
            filled_price=price,
            filled_timestamp=datetime.now(),
            reason=reason
        )
        self.orders.append(order)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🟢 BUY {amount:.6f} {symbol} @ ${price:,.2f} - {reason}")

    def _place_sell_order(self, symbol: str, price: float, reason: str = ""):
        """Place virtual sell order."""
        # Check if have position
        if symbol not in self.positions:
            return

        position = self.positions[symbol]
        amount = position.amount

        # Calculate proceeds
        proceeds = amount * price
        commission = proceeds * self.commission_rate
        net_proceeds = proceeds - commission

        # Execute order
        self.cash += net_proceeds

        # Calculate P&L
        pnl = net_proceeds - (position.entry_price * amount)
        pnl_pct = pnl / (position.entry_price * amount)

        # Remove position
        del self.positions[symbol]

        # Record order
        order = PaperOrder(
            order_id=f"SELL-{symbol}-{int(time.time())}",
            symbol=symbol,
            side=OrderSide.SELL,
            amount=amount,
            price=price,
            timestamp=datetime.now(),
            status=OrderStatus.FILLED,
            filled_price=price,
            filled_timestamp=datetime.now(),
            reason=f"{reason} (P&L: ${pnl:,.2f} / {pnl_pct:.2%})"
        )
        self.orders.append(order)

        emoji = "🟢" if pnl > 0 else "🔴"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {emoji} SELL {amount:.6f} {symbol} @ ${price:,.2f} - {reason} (P&L: ${pnl:,.2f})")

    def _check_stop_loss_take_profit(self):
        """Check all positions for stop loss / take profit."""
        positions_to_check = list(self.positions.items())

        for symbol, position in positions_to_check:
            if symbol not in self.current_prices:
                continue

            current_price = self.current_prices[symbol]

            # Update position
            position.current_price = current_price
            position.unrealized_pnl = (current_price - position.entry_price) * position.amount
            position.unrealized_pnl_pct = (current_price / position.entry_price - 1)

            # Check stop loss
            if position.unrealized_pnl_pct <= -self.stop_loss_pct:
                self._place_sell_order(
                    symbol, current_price,
                    f"Stop Loss at {position.unrealized_pnl_pct:.2%}"
                )

            # Check take profit
            elif position.unrealized_pnl_pct >= self.take_profit_pct:
                self._place_sell_order(
                    symbol, current_price,
                    f"Take Profit at {position.unrealized_pnl_pct:.2%}"
                )

    def _check_kill_switch(self) -> bool:
        """Check if daily loss limit exceeded."""
        portfolio_value = self.get_portfolio_value()
        daily_pnl = (portfolio_value - self.daily_start_value) / self.daily_start_value

        self.daily_pnl = daily_pnl

        return daily_pnl <= -self.max_daily_loss

    def _close_all_positions(self):
        """Close all open positions."""
        print("\nClosing all positions...")

        positions_to_close = list(self.positions.keys())

        for symbol in positions_to_close:
            if symbol in self.current_prices:
                self._place_sell_order(
                    symbol,
                    self.current_prices[symbol],
                    "Closing position (stop trading)"
                )

    def get_portfolio_value(self) -> float:
        """Get current portfolio value."""
        position_value = sum(
            pos.amount * self.current_prices.get(pos.symbol, pos.current_price)
            for pos in self.positions.values()
        )
        return self.cash + position_value

    def _update_portfolio_value(self):
        """Record portfolio value history."""
        portfolio_value = self.get_portfolio_value()

        self.portfolio_value_history.append({
            'timestamp': datetime.now().isoformat(),
            'portfolio_value': portfolio_value,
            'cash': self.cash,
            'positions_value': portfolio_value - self.cash,
            'num_positions': len(self.positions),
            'daily_pnl_pct': self.daily_pnl * 100
        })

        # Print periodic update
        if len(self.portfolio_value_history) % 10 == 0:  # Every 10 updates
            self._print_status()

    def _print_status(self):
        """Print current status."""
        portfolio_value = self.get_portfolio_value()
        total_return = (portfolio_value - self.initial_capital) / self.initial_capital

        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] PAPER TRADING STATUS")
        print(f"{'='*60}")
        print(f"Portfolio Value: ${portfolio_value:,.2f}")
        print(f"Cash: ${self.cash:,.2f}")
        print(f"Total Return: {total_return:.2%}")
        print(f"Daily P&L: {self.daily_pnl:.2%}")
        print(f"Open Positions: {len(self.positions)}")
        print(f"Total Orders: {len(self.orders)}")

        if self.positions:
            print(f"\nPositions:")
            for symbol, pos in self.positions.items():
                print(f"  {symbol}: {pos.amount:.6f} @ ${pos.entry_price:,.2f} (P&L: {pos.unrealized_pnl_pct:.2%})")

        print(f"{'='*60}\n")

    def _print_summary(self):
        """Print final summary."""
        portfolio_value = self.get_portfolio_value()
        total_return = (portfolio_value - self.initial_capital) / self.initial_capital

        buy_orders = [o for o in self.orders if o.side == OrderSide.BUY]
        sell_orders = [o for o in self.orders if o.side == OrderSide.SELL]

        print(f"\n{'='*60}")
        print(f"PAPER TRADING SUMMARY")
        print(f"{'='*60}")
        print(f"Final Portfolio Value: ${portfolio_value:,.2f}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Total Return: {total_return:.2%}")
        print(f"Total Orders: {len(self.orders)} ({len(buy_orders)} buy, {len(sell_orders)} sell)")
        print(f"Final Cash: ${self.cash:,.2f}")
        print(f"Open Positions: {len(self.positions)}")
        print(f"{'='*60}\n")

    def _save_state(self):
        """Save current state to disk."""
        state_file = os.path.join(self.data_dir, 'paper_trading_state.json')

        state = {
            'timestamp': datetime.now().isoformat(),
            'cash': self.cash,
            'initial_capital': self.initial_capital,
            'portfolio_value': self.get_portfolio_value(),
            'positions': {
                symbol: {
                    'amount': pos.amount,
                    'entry_price': pos.entry_price,
                    'entry_time': pos.entry_time.isoformat(),
                    'current_price': pos.current_price
                }
                for symbol, pos in self.positions.items()
            },
            'num_orders': len(self.orders),
            'portfolio_history_length': len(self.portfolio_value_history)
        }

        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

        # Save full history periodically
        if len(self.portfolio_value_history) % 100 == 0:
            history_file = os.path.join(self.data_dir, f'history_{datetime.now().strftime("%Y%m%d")}.json')
            with open(history_file, 'w') as f:
                json.dump(self.portfolio_value_history, f, indent=2)

    def _load_state(self):
        """Load previous state if exists."""
        state_file = os.path.join(self.data_dir, 'paper_trading_state.json')

        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)

                print(f"Loaded previous paper trading state from {state['timestamp']}")
                print(f"  Previous portfolio value: ${state['portfolio_value']:,.2f}")

            except Exception as e:
                print(f"Warning: Could not load previous state: {e}")
