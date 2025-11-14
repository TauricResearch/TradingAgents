"""
Complete example of using the TradingAgents backtesting framework.

This example demonstrates:
1. Basic backtesting with built-in strategies
2. Custom strategy implementation
3. Performance analysis
4. Monte Carlo simulation
5. Report generation
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict, List

import pandas as pd

# Import backtesting framework
from tradingagents.backtest import (
    Backtester,
    BacktestConfig,
    BaseStrategy,
    Signal,
    Position,
    BuyAndHoldStrategy,
    SimpleMovingAverageStrategy,
    compare_strategies,
)


def example_1_basic_backtest():
    """Example 1: Run a basic backtest with buy-and-hold strategy."""
    print("=" * 80)
    print("Example 1: Basic Backtest")
    print("=" * 80)

    # Create configuration
    config = BacktestConfig(
        initial_capital=Decimal('100000.00'),
        start_date='2020-01-01',
        end_date='2023-12-31',
        commission=Decimal('0.001'),  # 0.1%
        slippage=Decimal('0.0005'),   # 0.05%
        benchmark='SPY',
    )

    # Create strategy
    strategy = BuyAndHoldStrategy()

    # Create backtester
    backtester = Backtester(config)

    # Run backtest
    print("\nRunning backtest...")
    results = backtester.run(
        strategy=strategy,
        tickers=['AAPL', 'MSFT'],
    )

    # Print results
    print("\nBacktest Results:")
    print(f"Total Return: {results.total_return:+.2%}")
    print(f"Annualized Return: {results.metrics.annualized_return:+.2%}")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {results.max_drawdown:.2%}")
    print(f"Win Rate: {results.win_rate:.2%}")
    print(f"Total Trades: {results.metrics.total_trades}")

    # Generate HTML report
    print("\nGenerating HTML report...")
    results.generate_report('backtest_report_example1.html')
    print("Report saved to: backtest_report_example1.html")

    # Export to CSV
    print("\nExporting to CSV...")
    results.export_to_csv('backtest_results_example1')
    print("Results exported to: backtest_results_example1/")

    return results


def example_2_sma_strategy():
    """Example 2: Backtest with SMA crossover strategy."""
    print("\n" + "=" * 80)
    print("Example 2: SMA Crossover Strategy")
    print("=" * 80)

    config = BacktestConfig(
        initial_capital=Decimal('100000.00'),
        start_date='2020-01-01',
        end_date='2023-12-31',
        commission=Decimal('0.001'),
        slippage=Decimal('0.0005'),
        benchmark='SPY',
    )

    # Create SMA strategy
    strategy = SimpleMovingAverageStrategy(
        short_window=50,
        long_window=200,
    )

    backtester = Backtester(config)

    print("\nRunning backtest with SMA crossover...")
    results = backtester.run(
        strategy=strategy,
        tickers=['AAPL'],
    )

    print("\nResults:")
    print(f"Total Return: {results.total_return:+.2%}")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {results.max_drawdown:.2%}")

    return results


class MomentumStrategy(BaseStrategy):
    """
    Example custom momentum strategy.

    Buys stocks with positive momentum (returns over lookback period).
    """

    def __init__(self, lookback_days: int = 20):
        """Initialize momentum strategy."""
        super().__init__(name="Momentum")
        self.lookback_days = lookback_days

    def generate_signals(
        self,
        timestamp: datetime,
        data: Dict[str, pd.DataFrame],
        positions: Dict[str, Position],
        portfolio_value: Decimal,
    ) -> List[Signal]:
        """Generate momentum-based signals."""
        signals = []

        for ticker, df in data.items():
            if len(df) < self.lookback_days:
                continue

            # Calculate momentum (returns over lookback period)
            recent_prices = df['close'].tail(self.lookback_days)
            momentum = (recent_prices.iloc[-1] / recent_prices.iloc[0]) - 1

            current_position = positions.get(ticker)

            # Buy if positive momentum and not holding
            if momentum > 0.05 and (not current_position or current_position.is_flat):
                signals.append(Signal(
                    ticker=ticker,
                    timestamp=timestamp,
                    action='buy',
                    confidence=min(float(momentum) * 5, 1.0),
                ))

            # Sell if negative momentum and holding
            elif momentum < -0.02 and current_position and not current_position.is_flat:
                signals.append(Signal(
                    ticker=ticker,
                    timestamp=timestamp,
                    action='sell',
                    confidence=0.8,
                ))

        return signals


def example_3_custom_strategy():
    """Example 3: Custom momentum strategy."""
    print("\n" + "=" * 80)
    print("Example 3: Custom Momentum Strategy")
    print("=" * 80)

    config = BacktestConfig(
        initial_capital=Decimal('100000.00'),
        start_date='2020-01-01',
        end_date='2023-12-31',
        commission=Decimal('0.001'),
        slippage=Decimal('0.0005'),
    )

    strategy = MomentumStrategy(lookback_days=20)

    backtester = Backtester(config)

    print("\nRunning backtest with momentum strategy...")
    results = backtester.run(
        strategy=strategy,
        tickers=['AAPL', 'MSFT', 'GOOGL'],
    )

    print("\nResults:")
    print(f"Total Return: {results.total_return:+.2%}")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {results.max_drawdown:.2%}")

    return results


def example_4_compare_strategies():
    """Example 4: Compare multiple strategies."""
    print("\n" + "=" * 80)
    print("Example 4: Strategy Comparison")
    print("=" * 80)

    strategies = {
        'Buy & Hold': BuyAndHoldStrategy(),
        'SMA (50/200)': SimpleMovingAverageStrategy(50, 200),
        'SMA (20/50)': SimpleMovingAverageStrategy(20, 50),
        'Momentum': MomentumStrategy(20),
    }

    print("\nComparing strategies...")
    comparison = compare_strategies(
        strategies=strategies,
        tickers=['AAPL'],
        start_date='2020-01-01',
        end_date='2023-12-31',
        initial_capital=100000.0,
    )

    print("\nComparison Results:")
    print(comparison)

    return comparison


def example_5_monte_carlo():
    """Example 5: Monte Carlo simulation."""
    print("\n" + "=" * 80)
    print("Example 5: Monte Carlo Simulation")
    print("=" * 80)

    # First run a backtest
    config = BacktestConfig(
        initial_capital=Decimal('100000.00'),
        start_date='2020-01-01',
        end_date='2023-12-31',
        commission=Decimal('0.001'),
    )

    strategy = SimpleMovingAverageStrategy()
    backtester = Backtester(config)

    print("\nRunning initial backtest...")
    results = backtester.run(strategy=strategy, tickers=['AAPL'])

    # Run Monte Carlo simulation
    print("\nRunning Monte Carlo simulation...")
    from tradingagents.backtest import MonteCarloConfig

    mc_config = MonteCarloConfig(
        n_simulations=10000,
        method='resample_returns',
    )

    mc_results = results.monte_carlo(mc_config)

    print("\nMonte Carlo Results:")
    print(f"Mean Final Value: ${mc_results.mean_final_value:,.2f}")
    print(f"Median Final Value: ${mc_results.median_final_value:,.2f}")
    print(f"Probability of Profit: {mc_results.probability_of_profit:.2%}")
    print("\nConfidence Intervals:")
    for level, (lower, upper) in mc_results.confidence_intervals.items():
        print(f"  {level:.0%}: ${lower:,.2f} - ${upper:,.2f}")

    return mc_results


def example_6_walk_forward():
    """Example 6: Walk-forward analysis."""
    print("\n" + "=" * 80)
    print("Example 6: Walk-Forward Analysis")
    print("=" * 80)

    from tradingagents.backtest import WalkForwardConfig

    config = BacktestConfig(
        initial_capital=Decimal('100000.00'),
        start_date='2020-01-01',
        end_date='2023-12-31',
        commission=Decimal('0.001'),
    )

    # Define strategy factory
    def strategy_factory(short_window, long_window):
        """Create SMA strategy with given parameters."""
        return SimpleMovingAverageStrategy(short_window, long_window)

    # Define parameter grid
    param_grid = {
        'short_window': [20, 50],
        'long_window': [100, 200],
    }

    # Create walk-forward config
    wf_config = WalkForwardConfig(
        in_sample_months=12,
        out_sample_months=3,
        optimization_metric='sharpe',
    )

    backtester = Backtester(config)

    print("\nRunning walk-forward analysis...")
    print("(This may take a while...)")

    wf_results = backtester.walk_forward_analysis(
        strategy_factory=strategy_factory,
        param_grid=param_grid,
        tickers=['AAPL'],
        wf_config=wf_config,
    )

    print("\nWalk-Forward Results:")
    print(f"Number of Windows: {len(wf_results.windows)}")
    print(f"WF Efficiency Ratio: {wf_results.efficiency_ratio:.2f}")
    print(f"Overfitting Score: {wf_results.overfitting_score:.2f}")

    print("\nWindow Summary:")
    print(wf_results.summary())

    return wf_results


def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("TradingAgents Backtesting Framework Examples")
    print("=" * 80)

    # Run examples
    try:
        example_1_basic_backtest()
    except Exception as e:
        print(f"Example 1 failed: {e}")

    try:
        example_2_sma_strategy()
    except Exception as e:
        print(f"Example 2 failed: {e}")

    try:
        example_3_custom_strategy()
    except Exception as e:
        print(f"Example 3 failed: {e}")

    try:
        example_4_compare_strategies()
    except Exception as e:
        print(f"Example 4 failed: {e}")

    try:
        example_5_monte_carlo()
    except Exception as e:
        print(f"Example 5 failed: {e}")

    # Walk-forward is slow, so commented out by default
    # try:
    #     example_6_walk_forward()
    # except Exception as e:
    #     print(f"Example 6 failed: {e}")

    print("\n" + "=" * 80)
    print("Examples Complete!")
    print("=" * 80)


if __name__ == '__main__':
    main()
