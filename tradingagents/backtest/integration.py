"""
Integration with TradingAgents framework.

This module provides integration between the backtesting framework
and TradingAgentsGraph, allowing backtesting of multi-agent strategies.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

import pandas as pd

from .strategy import BaseStrategy, Signal, Position
from .backtester import Backtester, BacktestResults
from .config import BacktestConfig
from .exceptions import IntegrationError


logger = logging.getLogger(__name__)


class TradingAgentsStrategy(BaseStrategy):
    """
    Wrapper strategy for TradingAgentsGraph.

    This class adapts TradingAgentsGraph to work with the backtesting framework.
    """

    def __init__(
        self,
        trading_graph: Any,
        lookback_days: int = 30,
    ):
        """
        Initialize TradingAgents strategy.

        Args:
            trading_graph: TradingAgentsGraph instance
            lookback_days: Number of days of historical data to provide
        """
        super().__init__(name="TradingAgents")
        self.trading_graph = trading_graph
        self.lookback_days = lookback_days
        self.last_signals: Dict[str, str] = {}  # ticker -> last action

        logger.info("TradingAgentsStrategy initialized")

    def generate_signals(
        self,
        timestamp: datetime,
        data: Dict[str, pd.DataFrame],
        positions: Dict[str, Position],
        portfolio_value: Decimal,
    ) -> List[Signal]:
        """
        Generate signals using TradingAgentsGraph.

        Args:
            timestamp: Current timestamp
            data: Historical data for all tickers
            positions: Current positions
            portfolio_value: Current portfolio value

        Returns:
            List of signals
        """
        signals = []

        for ticker, df in data.items():
            try:
                # Run TradingAgentsGraph
                final_state, processed_signal = self.trading_graph.propagate(
                    company_name=ticker,
                    trade_date=timestamp.strftime('%Y-%m-%d'),
                )

                # Parse the processed signal
                action = self._parse_signal(processed_signal)

                # Only generate signal if action changed or is new
                last_action = self.last_signals.get(ticker, 'hold')

                if action != last_action:
                    # Get confidence from final state if available
                    confidence = self._extract_confidence(final_state)

                    signal = Signal(
                        ticker=ticker,
                        timestamp=timestamp,
                        action=action,
                        confidence=confidence,
                        metadata={
                            'final_decision': final_state.get('final_trade_decision', ''),
                            'investment_plan': final_state.get('investment_plan', ''),
                        }
                    )

                    signals.append(signal)
                    self.last_signals[ticker] = action

                    logger.debug(f"{ticker}: {action} (confidence: {confidence:.2f})")

            except Exception as e:
                logger.error(f"Failed to generate signal for {ticker}: {e}")
                continue

        return signals

    def _parse_signal(self, processed_signal: str) -> str:
        """
        Parse the processed signal from TradingAgentsGraph.

        Args:
            processed_signal: Processed signal string

        Returns:
            Action ('buy', 'sell', or 'hold')
        """
        # Convert TradingAgents signal to backtest action
        signal_lower = processed_signal.lower()

        if 'buy' in signal_lower or 'long' in signal_lower:
            return 'buy'
        elif 'sell' in signal_lower or 'short' in signal_lower:
            return 'sell'
        else:
            return 'hold'

    def _extract_confidence(self, final_state: Dict[str, Any]) -> float:
        """
        Extract confidence level from final state.

        Args:
            final_state: Final state from TradingAgentsGraph

        Returns:
            Confidence level (0.0 to 1.0)
        """
        # This is a placeholder - you might want to parse the actual
        # confidence from the judge's decision or other metrics
        try:
            # Look for confidence indicators in the decision
            decision = final_state.get('final_trade_decision', '').lower()

            if 'high confidence' in decision or 'strong' in decision:
                return 0.9
            elif 'moderate' in decision or 'medium' in decision:
                return 0.7
            elif 'low' in decision or 'weak' in decision:
                return 0.5
            else:
                return 0.7  # Default moderate confidence

        except Exception:
            return 0.7

    def on_fill(self, fill: Any) -> None:
        """
        Called when an order is filled.

        Can be used to update TradingAgents memories with outcomes.

        Args:
            fill: Fill information
        """
        # TODO: Implement reflection mechanism
        # This could call trading_graph.reflect_and_remember()
        pass

    def finalize(self) -> None:
        """Called at end of backtest."""
        logger.info("TradingAgents strategy finalized")


def backtest_trading_agents(
    trading_graph: Any,
    tickers: List[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
    benchmark: str = 'SPY',
    **kwargs
) -> BacktestResults:
    """
    Backtest a TradingAgentsGraph strategy.

    Args:
        trading_graph: TradingAgentsGraph instance
        tickers: List of tickers to trade
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        initial_capital: Starting capital
        commission: Commission rate
        slippage: Slippage rate
        benchmark: Benchmark ticker
        **kwargs: Additional config parameters

    Returns:
        BacktestResults

    Example:
        >>> from tradingagents.graph.trading_graph import TradingAgentsGraph
        >>> from tradingagents.backtest.integration import backtest_trading_agents
        >>>
        >>> # Create strategy
        >>> graph = TradingAgentsGraph()
        >>>
        >>> # Run backtest
        >>> results = backtest_trading_agents(
        ...     trading_graph=graph,
        ...     tickers=['AAPL', 'MSFT'],
        ...     start_date='2023-01-01',
        ...     end_date='2023-12-31',
        ... )
        >>>
        >>> print(f"Total Return: {results.total_return:.2%}")
        >>> print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    """
    logger.info("Starting TradingAgents backtest")

    # Create configuration
    config = BacktestConfig(
        initial_capital=Decimal(str(initial_capital)),
        start_date=start_date,
        end_date=end_date,
        commission=Decimal(str(commission)),
        slippage=Decimal(str(slippage)),
        benchmark=benchmark,
        **kwargs
    )

    # Create strategy wrapper
    strategy = TradingAgentsStrategy(trading_graph)

    # Create backtester
    backtester = Backtester(config)

    # Run backtest
    results = backtester.run(
        strategy=strategy,
        tickers=tickers,
    )

    logger.info("TradingAgents backtest complete")

    return results


def compare_strategies(
    strategies: Dict[str, BaseStrategy],
    tickers: List[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    **kwargs
) -> pd.DataFrame:
    """
    Compare multiple strategies.

    Args:
        strategies: Dictionary of strategy_name -> strategy
        tickers: List of tickers to trade
        start_date: Start date
        end_date: End date
        initial_capital: Starting capital
        **kwargs: Additional config parameters

    Returns:
        DataFrame comparing strategy metrics

    Example:
        >>> from tradingagents.backtest.strategy import BuyAndHoldStrategy, SimpleMovingAverageStrategy
        >>> from tradingagents.backtest.integration import compare_strategies
        >>>
        >>> strategies = {
        ...     'Buy & Hold': BuyAndHoldStrategy(),
        ...     'SMA Crossover': SimpleMovingAverageStrategy(50, 200),
        ... }
        >>>
        >>> comparison = compare_strategies(
        ...     strategies=strategies,
        ...     tickers=['AAPL'],
        ...     start_date='2020-01-01',
        ...     end_date='2023-12-31',
        ... )
        >>>
        >>> print(comparison)
    """
    logger.info(f"Comparing {len(strategies)} strategies")

    results_dict = {}

    for name, strategy in strategies.items():
        logger.info(f"Running backtest for: {name}")

        # Create configuration
        config = BacktestConfig(
            initial_capital=Decimal(str(initial_capital)),
            start_date=start_date,
            end_date=end_date,
            **kwargs
        )

        # Create backtester
        backtester = Backtester(config)

        try:
            # Run backtest
            results = backtester.run(strategy=strategy, tickers=tickers)

            # Extract metrics
            results_dict[name] = {
                'Total Return': results.metrics.total_return,
                'Annualized Return': results.metrics.annualized_return,
                'Sharpe Ratio': results.metrics.sharpe_ratio,
                'Sortino Ratio': results.metrics.sortino_ratio,
                'Max Drawdown': results.metrics.max_drawdown,
                'Volatility': results.metrics.volatility,
                'Win Rate': results.metrics.win_rate,
                'Total Trades': results.metrics.total_trades,
            }

        except Exception as e:
            logger.error(f"Failed to backtest {name}: {e}")
            results_dict[name] = {k: None for k in [
                'Total Return', 'Annualized Return', 'Sharpe Ratio',
                'Sortino Ratio', 'Max Drawdown', 'Volatility',
                'Win Rate', 'Total Trades'
            ]}

    # Create comparison DataFrame
    comparison_df = pd.DataFrame(results_dict).T

    logger.info("Strategy comparison complete")

    return comparison_df


def parallel_backtest(
    strategy_configs: List[Dict[str, Any]],
    tickers: List[str],
    start_date: str,
    end_date: str,
    n_jobs: int = -1,
) -> List[BacktestResults]:
    """
    Run multiple backtests in parallel.

    Args:
        strategy_configs: List of dictionaries with strategy configurations
        tickers: List of tickers
        start_date: Start date
        end_date: End date
        n_jobs: Number of parallel jobs (-1 = all CPUs)

    Returns:
        List of BacktestResults

    Example:
        >>> configs = [
        ...     {'strategy': SimpleMovingAverageStrategy(50, 200)},
        ...     {'strategy': SimpleMovingAverageStrategy(20, 50)},
        ... ]
        >>>
        >>> results = parallel_backtest(
        ...     strategy_configs=configs,
        ...     tickers=['AAPL'],
        ...     start_date='2020-01-01',
        ...     end_date='2023-12-31',
        ... )
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    logger.info(f"Running {len(strategy_configs)} backtests in parallel")

    def run_single_backtest(config_dict):
        """Run a single backtest."""
        strategy = config_dict['strategy']

        backtest_config = BacktestConfig(
            initial_capital=config_dict.get('initial_capital', Decimal("100000")),
            start_date=start_date,
            end_date=end_date,
            commission=config_dict.get('commission', Decimal("0.001")),
            slippage=config_dict.get('slippage', Decimal("0.0005")),
        )

        backtester = Backtester(backtest_config)
        return backtester.run(strategy, tickers)

    # Determine number of workers
    if n_jobs == -1:
        import multiprocessing
        n_jobs = multiprocessing.cpu_count()

    results = []

    # Note: ProcessPoolExecutor may have issues with complex objects
    # For TradingAgentsGraph, you might need to use ThreadPoolExecutor instead
    # or implement proper serialization

    # For now, run sequentially to avoid pickling issues
    for config in strategy_configs:
        try:
            result = run_single_backtest(config)
            results.append(result)
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            results.append(None)

    logger.info("Parallel backtests complete")

    return results


class BacktestingPipeline:
    """
    Pipeline for running comprehensive backtesting workflows.

    Combines backtesting, walk-forward analysis, Monte Carlo simulation,
    and reporting into a single workflow.
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize pipeline.

        Args:
            config: Backtest configuration
        """
        self.config = config
        self.backtester = Backtester(config)

    def run_full_analysis(
        self,
        strategy: BaseStrategy,
        tickers: List[str],
        monte_carlo: bool = True,
        generate_report: bool = True,
        output_dir: str = './backtest_results',
    ) -> Dict[str, Any]:
        """
        Run full backtesting analysis.

        Args:
            strategy: Trading strategy
            tickers: List of tickers
            monte_carlo: Whether to run Monte Carlo simulation
            generate_report: Whether to generate HTML report
            output_dir: Output directory for results

        Returns:
            Dictionary with all analysis results
        """
        from pathlib import Path

        logger.info("Running full backtesting analysis")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Run backtest
        results = self.backtester.run(strategy, tickers)

        analysis = {
            'backtest_results': results,
            'metrics': results.metrics,
        }

        # Monte Carlo simulation
        if monte_carlo:
            logger.info("Running Monte Carlo simulation")
            from .monte_carlo import MonteCarloConfig
            mc_config = MonteCarloConfig(n_simulations=10000)
            mc_results = results.monte_carlo(mc_config)
            analysis['monte_carlo'] = mc_results

        # Generate report
        if generate_report:
            logger.info("Generating HTML report")
            report_path = output_path / 'backtest_report.html'
            results.generate_report(str(report_path))
            analysis['report_path'] = str(report_path)

        # Export to CSV
        results.export_to_csv(str(output_path))

        logger.info(f"Analysis complete. Results saved to {output_dir}")

        return analysis
