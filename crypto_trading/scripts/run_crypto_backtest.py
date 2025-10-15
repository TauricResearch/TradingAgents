"""
Full Crypto Backtesting Example
Runs actual backtests with real historical data
"""
import os
import sys
from datetime import datetime, timedelta

# Add project root to path (go up 3 levels: scripts -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from crypto_trading.src.backtesting.crypto_backtest_engine import CryptoBacktestEngine, OrderType
from crypto_trading.src.backtesting.crypto_data_loader import CryptoDataLoader, CRYPTO_MARKET_CYCLES
from crypto_trading.src.backtesting.crypto_strategy_evaluator import CryptoStrategyEvaluator


def print_section(title):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


# ============================================================================
# STRATEGY DEFINITIONS
# ============================================================================

def buy_and_hold_strategy(timestamp, row, engine):
    """Buy once and hold."""
    if len(engine.positions) == 0:
        return OrderType.BUY, "Initial buy - Buy and Hold strategy"
    return OrderType.HOLD, "Holding position"


class SimpleMovingAverageCrossover:
    """Simple MA crossover strategy."""

    def __init__(self, short_window=20, long_window=50):
        self.short_window = short_window
        self.long_window = long_window
        self.prices = []

    def __call__(self, timestamp, row, engine):
        self.prices.append(row['close'])

        if len(self.prices) < self.long_window:
            return OrderType.HOLD, "Building price history"

        # Calculate simple moving averages
        short_ma = sum(self.prices[-self.short_window:]) / self.short_window
        long_ma = sum(self.prices[-self.long_window:]) / self.long_window

        # Golden cross - buy signal
        if short_ma > long_ma and len(engine.positions) == 0:
            return OrderType.BUY, f"Golden cross: SMA{self.short_window} (${short_ma:.0f}) > SMA{self.long_window} (${long_ma:.0f})"

        # Death cross - sell signal
        elif short_ma < long_ma and len(engine.positions) > 0:
            return OrderType.SELL, f"Death cross: SMA{self.short_window} (${short_ma:.0f}) < SMA{self.long_window} (${long_ma:.0f})"

        return OrderType.HOLD, f"No signal: SMA{self.short_window}=${short_ma:.0f}, SMA{self.long_window}=${long_ma:.0f}"


class MomentumStrategy:
    """Buy on momentum, sell on reversal."""

    def __init__(self, lookback=10, momentum_threshold=0.05):
        self.lookback = lookback
        self.momentum_threshold = momentum_threshold
        self.prices = []

    def __call__(self, timestamp, row, engine):
        self.prices.append(row['close'])

        if len(self.prices) < self.lookback:
            return OrderType.HOLD, "Building price history"

        # Calculate momentum (% change over lookback period)
        momentum = (self.prices[-1] - self.prices[-self.lookback]) / self.prices[-self.lookback]

        # Strong upward momentum - buy
        if momentum > self.momentum_threshold and len(engine.positions) == 0:
            return OrderType.BUY, f"Strong momentum: +{momentum:.2%} over {self.lookback} days"

        # Momentum reversal - sell
        elif momentum < -self.momentum_threshold and len(engine.positions) > 0:
            return OrderType.SELL, f"Momentum reversal: {momentum:.2%} over {self.lookback} days"

        return OrderType.HOLD, f"Momentum neutral: {momentum:.2%}"


# ============================================================================
# BACKTEST EXECUTION
# ============================================================================

def run_single_backtest():
    """Example 1: Run a single backtest."""
    print_section("EXAMPLE 1: Single Backtest - Buy and Hold")

    try:
        # Setup
        print("Setting up backtest...")
        engine = CryptoBacktestEngine(
            initial_capital=10000,
            commission_rate=0.001,
            slippage_rate=0.002
        )
        loader = CryptoDataLoader(exchange_id='binance')
        evaluator = CryptoStrategyEvaluator(engine, loader)

        # Define period
        symbol = 'BTC/USDT'
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 6, 1)

        print(f"Symbol: {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Initial Capital: ${engine.initial_capital:,.2f}\n")

        # Run backtest
        print("Fetching data and running backtest...\n")
        metrics = evaluator.run_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            strategy_func=buy_and_hold_strategy,
            timeframe='1d'
        )

        # Display results
        print("\n📊 BACKTEST RESULTS:")
        print(f"  Final Capital:     ${metrics['final_capital']:,.2f}")
        print(f"  Total Return:      {metrics['total_return_pct']:.2f}%")
        print(f"  Max Drawdown:      {metrics['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe Ratio:      {metrics['sharpe_ratio']:.2f}")
        print(f"  Total Trades:      {metrics['total_trades']}")
        print(f"  Win Rate:          {metrics['win_rate_pct']:.1f}%")

        return True

    except Exception as e:
        print(f"\n❌ Error running backtest: {e}")
        print("\nNote: This requires:")
        print("  1. CCXT installed: pip install ccxt")
        print("  2. Internet connection to fetch data")
        import traceback
        traceback.print_exc()
        return False


def compare_strategies_example():
    """Example 2: Compare multiple strategies."""
    print_section("EXAMPLE 2: Strategy Comparison")

    try:
        # Setup
        print("Setting up strategy comparison...")
        engine = CryptoBacktestEngine(initial_capital=10000)
        loader = CryptoDataLoader(exchange_id='binance')
        evaluator = CryptoStrategyEvaluator(engine, loader)

        # Define strategies
        strategies = {
            'Buy & Hold': buy_and_hold_strategy,
            'MA Cross (20/50)': SimpleMovingAverageCrossover(20, 50),
            'Momentum (10d)': MomentumStrategy(10, 0.05),
        }

        # Run comparison
        symbol = 'BTC/USDT'
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 6, 1)

        print(f"Symbol: {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Strategies: {len(strategies)}\n")

        print("Running comparisons...\n")
        comparison_df = evaluator.compare_strategies(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            strategies=strategies,
            timeframe='1d'
        )

        # Find best strategy
        print("\n🏆 BEST STRATEGIES:")
        best_return = comparison_df.loc[comparison_df['total_return_pct'].idxmax()]
        best_sharpe = comparison_df.loc[comparison_df['sharpe_ratio'].idxmax()]

        print(f"  Best Return:  {best_return['strategy_name']} ({best_return['total_return_pct']:.2f}%)")
        print(f"  Best Sharpe:  {best_sharpe['strategy_name']} ({best_sharpe['sharpe_ratio']:.2f})")

        return True

    except Exception as e:
        print(f"\n❌ Error in comparison: {e}")
        import traceback
        traceback.print_exc()
        return False


def walk_forward_test_example():
    """Example 3: Walk-forward testing."""
    print_section("EXAMPLE 3: Walk-Forward Testing")

    try:
        # Setup
        print("Setting up walk-forward test...")
        engine = CryptoBacktestEngine(initial_capital=10000)
        loader = CryptoDataLoader(exchange_id='binance')
        evaluator = CryptoStrategyEvaluator(engine, loader)

        # Define parameters
        symbol = 'BTC/USDT'
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 6, 1)

        print(f"Symbol: {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Train Period: 60 days")
        print(f"Test Period: 30 days\n")

        # Run walk-forward test
        print("Running walk-forward test...\n")
        results = evaluator.run_walk_forward_test(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            strategy_func=SimpleMovingAverageCrossover(20, 50),
            train_period_days=60,
            test_period_days=30,
            timeframe='1d'
        )

        # Analyze results
        if results:
            import numpy as np
            returns = [r['total_return_pct'] for r in results]
            sharpes = [r['sharpe_ratio'] for r in results]

            print("\n📊 WALK-FORWARD SUMMARY:")
            print(f"  Periods Tested:    {len(results)}")
            print(f"  Avg Return:        {np.mean(returns):.2f}%")
            print(f"  Std Dev:           {np.std(returns):.2f}%")
            print(f"  Avg Sharpe:        {np.mean(sharpes):.2f}")
            print(f"  Win Rate:          {sum(1 for r in returns if r > 0) / len(returns) * 100:.1f}%")

        return True

    except Exception as e:
        print(f"\n❌ Error in walk-forward test: {e}")
        import traceback
        traceback.print_exc()
        return False


def market_cycle_test_example():
    """Example 4: Test on historical market cycles."""
    print_section("EXAMPLE 4: Market Cycle Testing")

    try:
        # Setup
        print("Testing strategy across market cycles...")
        engine = CryptoBacktestEngine(initial_capital=10000)
        loader = CryptoDataLoader(exchange_id='binance')
        evaluator = CryptoStrategyEvaluator(engine, loader)

        # Use recent cycles only (to ensure data availability)
        recent_cycles = [
            {
                'name': '2022 Bear Market',
                'type': 'bear',
                'start': '2022-01-01',
                'end': '2022-11-21'
            },
            {
                'name': '2023 Recovery',
                'type': 'bull',
                'start': '2023-01-01',
                'end': '2023-12-31'
            },
            {
                'name': '2024 YTD',
                'type': 'bull',
                'start': '2024-01-01',
                'end': '2024-06-01'
            }
        ]

        print(f"Testing {len(recent_cycles)} market cycles\n")

        # Run tests
        results = evaluator.test_on_market_cycles(
            symbol='BTC/USDT',
            strategy_func=SimpleMovingAverageCrossover(20, 50),
            cycles=recent_cycles,
            timeframe='1d'
        )

        # Analyze by cycle type
        print("\n📊 PERFORMANCE BY MARKET CYCLE:")
        bull_returns = []
        bear_returns = []

        for cycle_name, metrics in results.items():
            cycle_type = metrics['cycle_type']
            return_pct = metrics['total_return_pct']

            print(f"  {cycle_name:20s} ({cycle_type:4s}): {return_pct:>7.2f}%")

            if cycle_type == 'bull':
                bull_returns.append(return_pct)
            else:
                bear_returns.append(return_pct)

        if bull_returns and bear_returns:
            import numpy as np
            print(f"\n  Bull Market Avg:  {np.mean(bull_returns):.2f}%")
            print(f"  Bear Market Avg:  {np.mean(bear_returns):.2f}%")

        return True

    except Exception as e:
        print(f"\n❌ Error in cycle testing: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run all backtest examples."""
    print("\n" + "=" * 80)
    print("  CRYPTO BACKTESTING - FULL EXECUTION EXAMPLES")
    print("=" * 80)
    print("\nThis script runs actual backtests with real historical data.")
    print("\nRequirements:")
    print("  ✓ CCXT installed (pip install ccxt)")
    print("  ✓ Internet connection")
    print("  ✓ ~5-10 minutes for data fetching and execution\n")

    import time

    results = {}
    start_time = time.time()

    # Run examples
    print("\n🚀 Starting backtest execution...\n")

    results['single'] = run_single_backtest()
    time.sleep(1)

    results['comparison'] = compare_strategies_example()
    time.sleep(1)

    results['walk_forward'] = walk_forward_test_example()
    time.sleep(1)

    results['cycles'] = market_cycle_test_example()

    # Summary
    elapsed = time.time() - start_time

    print_section("EXECUTION SUMMARY")

    total = len(results)
    passed = sum(1 for r in results.values() if r is True)

    for name, result in results.items():
        status = "✅ SUCCESS" if result else "❌ FAILED"
        print(f"{status:15s} - {name}")

    print(f"\nResults: {passed}/{total} examples completed")
    print(f"Execution time: {elapsed:.1f} seconds")

    if passed == total:
        print("\n🎉 All backtest examples completed successfully!")
    else:
        print(f"\n⚠️  {total - passed} example(s) failed.")
        print("\nTroubleshooting:")
        print("  1. Install CCXT: pip install ccxt")
        print("  2. Check internet connection")
        print("  3. Review error messages above")

    print("\n📚 Next Steps:")
    print("  1. Review backtest results above")
    print("  2. Try different strategies in examples/crypto_backtest_examples.py")
    print("  3. Integrate with Phase 2 crypto agents")
    print("  4. Calibrate risk parameters based on results")
    print("  5. Proceed to Phase 4: Paper Trading\n")


if __name__ == "__main__":
    main()
