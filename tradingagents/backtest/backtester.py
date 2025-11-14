"""
Core backtesting engine.

This module implements the main Backtester class that orchestrates
historical data management, strategy execution, order simulation,
and performance analysis.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

import pandas as pd
import numpy as np
from tqdm import tqdm

from .config import BacktestConfig
from .data_handler import HistoricalDataHandler
from .execution import ExecutionSimulator, Order, OrderSide, Fill, create_market_order
from .strategy import BaseStrategy, Signal, Position, PositionSizer, RiskManager
from .performance import PerformanceAnalyzer, PerformanceMetrics
from .reporting import BacktestReporter
from .monte_carlo import MonteCarloSimulator, MonteCarloResults, MonteCarloConfig
from .walk_forward import WalkForwardAnalyzer, WalkForwardResults, WalkForwardConfig
from .exceptions import BacktestError, InsufficientCapitalError


logger = logging.getLogger(__name__)


@dataclass
class BacktestResults:
    """
    Container for backtest results.

    Attributes:
        config: Backtest configuration
        metrics: Performance metrics
        equity_curve: Portfolio value over time
        trades: DataFrame with trade information
        positions_history: History of positions
        orders: List of all orders
        fills: List of all fills
        benchmark: Benchmark time series
        start_date: Actual start date
        end_date: Actual end date
    """
    config: BacktestConfig
    metrics: PerformanceMetrics
    equity_curve: pd.Series
    trades: pd.DataFrame
    positions_history: pd.DataFrame
    orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    benchmark: Optional[pd.Series] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    @property
    def total_return(self) -> float:
        """Get total return."""
        return self.metrics.total_return

    @property
    def sharpe_ratio(self) -> float:
        """Get Sharpe ratio."""
        return self.metrics.sharpe_ratio

    @property
    def max_drawdown(self) -> float:
        """Get maximum drawdown."""
        return self.metrics.max_drawdown

    @property
    def win_rate(self) -> float:
        """Get win rate."""
        return self.metrics.win_rate

    def generate_report(self, output_path: str) -> None:
        """
        Generate HTML report.

        Args:
            output_path: Path to save report
        """
        reporter = BacktestReporter()
        reporter.generate_html_report(
            output_path=output_path,
            metrics=self.metrics,
            equity_curve=self.equity_curve,
            trades=self.trades,
            benchmark=self.benchmark,
            positions=self.positions_history,
            config=self.config.to_dict(),
        )

    def export_to_csv(self, output_dir: str) -> None:
        """
        Export results to CSV files.

        Args:
            output_dir: Directory to save CSV files
        """
        reporter = BacktestReporter()
        reporter.export_to_csv(
            output_dir=output_dir,
            equity_curve=self.equity_curve,
            trades=self.trades,
            metrics=self.metrics,
        )

    def compare_to_benchmark(self) -> Dict[str, float]:
        """
        Compare strategy to benchmark.

        Returns:
            Dictionary with comparison metrics
        """
        if self.benchmark is None:
            return {}

        return {
            'alpha': self.metrics.alpha or 0.0,
            'beta': self.metrics.beta or 0.0,
            'correlation': self.metrics.correlation or 0.0,
            'tracking_error': self.metrics.tracking_error or 0.0,
            'information_ratio': self.metrics.information_ratio or 0.0,
        }

    def monte_carlo(
        self,
        config: Optional[MonteCarloConfig] = None
    ) -> MonteCarloResults:
        """
        Run Monte Carlo simulation on results.

        Args:
            config: Monte Carlo configuration

        Returns:
            MonteCarloResults
        """
        if config is None:
            config = MonteCarloConfig()

        simulator = MonteCarloSimulator(config)
        return simulator.simulate(
            equity_curve=self.equity_curve,
            trades=self.trades,
        )


class Portfolio:
    """
    Manages portfolio state during backtesting.

    Tracks positions, cash, and computes portfolio value.
    """

    def __init__(self, initial_capital: Decimal):
        """
        Initialize portfolio.

        Args:
            initial_capital: Starting capital
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Dict[str, Any]] = []
        self.equity_history: List[Dict[str, Any]] = []

    def update_position(
        self,
        ticker: str,
        fill: Fill,
    ) -> None:
        """
        Update position based on fill.

        Args:
            ticker: Ticker symbol
            fill: Fill information
        """
        if ticker not in self.positions:
            # Create new position
            self.positions[ticker] = Position(
                ticker=ticker,
                quantity=Decimal("0"),
                avg_entry_price=Decimal("0"),
                current_price=fill.price,
                unrealized_pnl=Decimal("0"),
                entry_timestamp=fill.timestamp,
            )

        position = self.positions[ticker]

        # Update position quantity
        if fill.side == OrderSide.BUY:
            # Adding to long or closing short
            new_quantity = position.quantity + fill.quantity

            if position.quantity >= 0:  # Was long or flat
                # Calculate new average price
                total_cost = position.quantity * position.avg_entry_price
                total_cost += fill.quantity * fill.price
                position.avg_entry_price = total_cost / new_quantity if new_quantity > 0 else Decimal("0")
            else:  # Was short, closing
                if new_quantity >= 0:  # Fully closed or reversed
                    realized_pnl = (position.avg_entry_price - fill.price) * abs(position.quantity)
                    self._record_trade(ticker, realized_pnl, fill)
                    if new_quantity > 0:  # Reversed to long
                        position.avg_entry_price = fill.price
                else:  # Partial close
                    realized_pnl = (position.avg_entry_price - fill.price) * fill.quantity
                    self._record_trade(ticker, realized_pnl, fill)

            position.quantity = new_quantity

        else:  # SELL
            # Removing from long or opening/adding to short
            new_quantity = position.quantity - fill.quantity

            if position.quantity > 0:  # Was long
                if new_quantity <= 0:  # Fully closed or reversed
                    realized_pnl = (fill.price - position.avg_entry_price) * position.quantity
                    self._record_trade(ticker, realized_pnl, fill)
                    if new_quantity < 0:  # Reversed to short
                        position.avg_entry_price = fill.price
                else:  # Partial close
                    realized_pnl = (fill.price - position.avg_entry_price) * fill.quantity
                    self._record_trade(ticker, realized_pnl, fill)
            else:  # Was short or flat
                # Calculate new average price for short
                total_cost = abs(position.quantity) * position.avg_entry_price
                total_cost += fill.quantity * fill.price
                position.avg_entry_price = total_cost / abs(new_quantity) if new_quantity < 0 else Decimal("0")

            position.quantity = new_quantity

        # Update cash
        if fill.side == OrderSide.BUY:
            self.cash -= fill.quantity * fill.price + fill.commission
        else:
            self.cash += fill.quantity * fill.price - fill.commission

        # Clean up flat positions
        if position.quantity == 0:
            del self.positions[ticker]

    def _record_trade(self, ticker: str, pnl: Decimal, fill: Fill) -> None:
        """Record a completed trade."""
        self.trades.append({
            'ticker': ticker,
            'timestamp': fill.timestamp,
            'pnl': float(pnl),
            'pnl_pct': float(pnl / self.get_total_value()),
        })

    def update_prices(self, prices: Dict[str, Decimal], timestamp: datetime) -> None:
        """
        Update current prices for all positions.

        Args:
            prices: Dictionary of ticker -> price
            timestamp: Current timestamp
        """
        for ticker, position in self.positions.items():
            if ticker in prices:
                position.current_price = prices[ticker]

                # Update unrealized P&L
                if position.quantity > 0:  # Long
                    position.unrealized_pnl = (
                        position.quantity * (position.current_price - position.avg_entry_price)
                    )
                else:  # Short
                    position.unrealized_pnl = (
                        abs(position.quantity) * (position.avg_entry_price - position.current_price)
                    )

        # Record equity
        self.equity_history.append({
            'timestamp': timestamp,
            'total_value': float(self.get_total_value()),
            'cash': float(self.cash),
            'positions_value': float(self.get_positions_value()),
        })

    def get_positions_value(self) -> Decimal:
        """Get total value of all positions."""
        return sum(
            abs(pos.quantity) * pos.current_price
            for pos in self.positions.values()
        )

    def get_total_value(self) -> Decimal:
        """Get total portfolio value (cash + positions)."""
        positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
        )
        return self.cash + positions_value

    def get_available_capital(self) -> Decimal:
        """Get available capital for new positions."""
        # Simple: use cash (could be more sophisticated with margin)
        return self.cash


class Backtester:
    """
    Main backtesting engine.

    Orchestrates historical data, strategy execution, order simulation,
    and performance analysis.
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize backtester.

        Args:
            config: Backtest configuration
        """
        self.config = config

        # Initialize components
        self.data_handler = HistoricalDataHandler(config)
        self.execution_simulator = ExecutionSimulator(config)
        self.performance_analyzer = PerformanceAnalyzer(config.risk_free_rate)

        # Position sizer and risk manager
        self.position_sizer = PositionSizer(
            method='equal_weight',
            params={'num_positions': 10}
        )
        self.risk_manager = RiskManager(
            max_position_size=config.max_position_size,
            max_leverage=config.max_leverage,
        )

        # State
        self.portfolio: Optional[Portfolio] = None
        self.orders: List[Order] = []

        logger.info("Backtester initialized")

    def run(
        self,
        strategy: BaseStrategy,
        tickers: List[str],
        data_source: Optional[str] = None,
    ) -> BacktestResults:
        """
        Run backtest.

        Args:
            strategy: Trading strategy
            tickers: List of tickers to trade
            data_source: Data source (overrides config)

        Returns:
            BacktestResults

        Raises:
            BacktestError: If backtest fails
        """
        logger.info(f"Starting backtest: {self.config.start_date} to {self.config.end_date}")
        logger.info(f"Tickers: {tickers}")
        logger.info(f"Initial capital: ${self.config.initial_capital}")

        try:
            # Load data
            self.data_handler.load_data(
                tickers=tickers,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
            )

            # Load benchmark if specified
            benchmark = None
            if self.config.benchmark:
                self.data_handler.load_data(
                    tickers=[self.config.benchmark],
                    start_date=self.config.start_date,
                    end_date=self.config.end_date,
                )
                benchmark = self.data_handler.data[self.config.benchmark]['close']

            # Get trading days
            trading_days = self.data_handler.get_trading_days()

            # Initialize portfolio
            self.portfolio = Portfolio(self.config.initial_capital)

            # Initialize strategy
            strategy.initialize(tickers, trading_days[0])

            # Run backtest
            self._run_backtest(strategy, tickers, trading_days)

            # Analyze results
            results = self._create_results(benchmark)

            logger.info("Backtest complete")
            logger.info(f"Total Return: {results.total_return:.2%}")
            logger.info(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
            logger.info(f"Max Drawdown: {results.max_drawdown:.2%}")

            return results

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            raise BacktestError(f"Backtest failed: {e}")

    def _run_backtest(
        self,
        strategy: BaseStrategy,
        tickers: List[str],
        trading_days: pd.DatetimeIndex,
    ) -> None:
        """Run the backtest simulation."""
        for current_date in tqdm(trading_days, desc="Backtesting", disable=not self.config.progress_bar):
            # Set current time for look-ahead bias prevention
            self.data_handler.set_current_time(current_date)

            # Get current data for all tickers
            current_data = {}
            current_prices = {}

            for ticker in tickers:
                try:
                    data = self.data_handler.get_data_at(ticker, current_date)
                    if not data.empty:
                        current_data[ticker] = data
                        current_prices[ticker] = self.data_handler.get_price_at(
                            ticker, current_date, 'close'
                        )
                except Exception as e:
                    logger.warning(f"Failed to get data for {ticker} at {current_date}: {e}")
                    continue

            if not current_data:
                continue

            # Update portfolio prices
            self.portfolio.update_prices(current_prices, current_date)

            # Call strategy on_bar
            strategy.on_bar(current_date, current_data)

            # Generate signals
            signals = strategy.generate_signals(
                timestamp=current_date,
                data=current_data,
                positions=self.portfolio.positions,
                portfolio_value=self.portfolio.get_total_value(),
            )

            # Process signals
            for signal in signals:
                self._process_signal(signal, current_data, current_date)

        # Finalize strategy
        strategy.finalize()

    def _process_signal(
        self,
        signal: Signal,
        current_data: Dict[str, pd.DataFrame],
        current_date: datetime,
    ) -> None:
        """Process a trading signal."""
        ticker = signal.ticker

        # Check if we have data for this ticker
        if ticker not in current_data:
            return

        # Get current price and volume
        current_bar = current_data[ticker].iloc[-1]
        current_price = Decimal(str(current_bar['close']))
        current_volume = Decimal(str(current_bar['volume'])) if 'volume' in current_bar else Decimal("0")

        # Check risk management
        approved, reason = self.risk_manager.check_signal(
            signal,
            self.portfolio.positions,
            self.portfolio.get_total_value(),
        )

        if not approved:
            logger.debug(f"Signal rejected by risk manager: {reason}")
            return

        # Determine order side and quantity
        if signal.action == 'buy':
            # Calculate position size
            quantity = self.position_sizer.calculate_position_size(
                signal,
                self.portfolio.get_total_value(),
                current_price,
                self.config.max_position_size,
            )

            if quantity <= 0:
                return

            # Create buy order
            order = create_market_order(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                timestamp=current_date,
            )

        elif signal.action == 'sell':
            # Sell existing position
            if ticker not in self.portfolio.positions:
                return

            position = self.portfolio.positions[ticker]
            quantity = abs(position.quantity)

            if quantity <= 0:
                return

            # Create sell order
            order = create_market_order(
                ticker=ticker,
                side=OrderSide.SELL,
                quantity=quantity,
                timestamp=current_date,
            )

        else:  # 'hold'
            return

        # Execute order
        try:
            filled_order = self.execution_simulator.execute_order(
                order,
                current_price,
                current_volume,
                self.portfolio.get_available_capital(),
            )

            self.orders.append(filled_order)

            # Update portfolio if filled
            if filled_order.is_filled or filled_order.is_partially_filled:
                fill = self.execution_simulator.fills[-1]
                self.portfolio.update_position(ticker, fill)

        except InsufficientCapitalError as e:
            logger.debug(f"Insufficient capital for order: {e}")
        except Exception as e:
            logger.warning(f"Order execution failed: {e}")

    def _create_results(self, benchmark: Optional[pd.Series]) -> BacktestResults:
        """Create backtest results."""
        # Get equity curve
        equity_df = pd.DataFrame(self.portfolio.equity_history)
        equity_df.set_index('timestamp', inplace=True)
        equity_curve = equity_df['total_value']

        # Get trades
        trades_df = pd.DataFrame(self.portfolio.trades)

        # Calculate metrics
        metrics = self.performance_analyzer.analyze(
            equity_curve=equity_curve,
            trades=trades_df,
            benchmark=benchmark,
        )

        # Get positions history
        positions_history = pd.DataFrame([
            {
                'timestamp': row['timestamp'],
                **{ticker: self.portfolio.positions.get(ticker, Position(
                    ticker=ticker,
                    quantity=Decimal("0"),
                    avg_entry_price=Decimal("0"),
                    current_price=Decimal("0"),
                    unrealized_pnl=Decimal("0"),
                    entry_timestamp=row['timestamp']
                )).to_dict() for ticker in self.portfolio.positions.keys()}
            }
            for row in self.portfolio.equity_history
        ])

        results = BacktestResults(
            config=self.config,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades_df,
            positions_history=positions_history,
            orders=self.orders,
            fills=self.execution_simulator.fills,
            benchmark=benchmark,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
        )

        return results

    def walk_forward_analysis(
        self,
        strategy_factory: Any,
        param_grid: Dict[str, List[Any]],
        tickers: List[str],
        wf_config: Optional[WalkForwardConfig] = None,
    ) -> WalkForwardResults:
        """
        Perform walk-forward analysis.

        Args:
            strategy_factory: Function that creates strategy with given params
            param_grid: Parameter grid to optimize
            tickers: List of tickers
            wf_config: Walk-forward configuration

        Returns:
            WalkForwardResults
        """
        if wf_config is None:
            wf_config = WalkForwardConfig(
                in_sample_months=12,
                out_sample_months=3,
            )

        analyzer = WalkForwardAnalyzer(wf_config)

        def backtest_func(params, tickers, start, end, capital):
            """Wrapper function for walk-forward analysis."""
            strategy = strategy_factory(**params)
            config = BacktestConfig(
                initial_capital=capital,
                start_date=start,
                end_date=end,
                commission=self.config.commission,
                slippage=self.config.slippage,
            )
            backtester = Backtester(config)
            results = backtester.run(strategy, tickers)
            return results.metrics, results.equity_curve, results.trades

        return analyzer.analyze(
            backtest_func=backtest_func,
            param_grid=param_grid,
            tickers=tickers,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
        )
