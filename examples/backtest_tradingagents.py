"""
Example of backtesting TradingAgentsGraph.

This example shows how to backtest the multi-agent LLM trading strategy
using the backtesting framework.
"""

from decimal import Decimal

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.backtest import backtest_trading_agents, BacktestingPipeline, BacktestConfig


def example_simple_backtest():
    """Simple backtest of TradingAgentsGraph."""
    print("=" * 80)
    print("TradingAgents Backtest Example")
    print("=" * 80)

    # Create TradingAgentsGraph
    print("\nInitializing TradingAgentsGraph...")
    trading_graph = TradingAgentsGraph(
        selected_analysts=["market", "fundamentals"],
        debug=False,
    )

    # Run backtest
    print("\nRunning backtest...")
    results = backtest_trading_agents(
        trading_graph=trading_graph,
        tickers=['AAPL', 'MSFT'],
        start_date='2023-01-01',
        end_date='2023-12-31',
        initial_capital=100000.0,
        commission=0.001,
        slippage=0.0005,
        benchmark='SPY',
    )

    # Print results
    print("\n" + "=" * 80)
    print("Backtest Results")
    print("=" * 80)
    print(f"Total Return:        {results.total_return:+.2%}")
    print(f"Annualized Return:   {results.metrics.annualized_return:+.2%}")
    print(f"Sharpe Ratio:        {results.sharpe_ratio:.2f}")
    print(f"Sortino Ratio:       {results.metrics.sortino_ratio:.2f}")
    print(f"Max Drawdown:        {results.max_drawdown:.2%}")
    print(f"Volatility:          {results.metrics.volatility:.2%}")
    print(f"Win Rate:            {results.win_rate:.2%}")
    print(f"Total Trades:        {results.metrics.total_trades}")

    # Benchmark comparison
    if results.benchmark is not None:
        print("\n" + "=" * 80)
        print("Benchmark Comparison")
        print("=" * 80)
        comparison = results.compare_to_benchmark()
        print(f"Alpha:               {comparison.get('alpha', 0):+.2%}")
        print(f"Beta:                {comparison.get('beta', 0):.2f}")
        print(f"Correlation:         {comparison.get('correlation', 0):.2f}")

    # Generate report
    print("\nGenerating HTML report...")
    results.generate_report('tradingagents_backtest_report.html')
    print("Report saved to: tradingagents_backtest_report.html")

    return results


def example_comprehensive_analysis():
    """Run comprehensive analysis with Monte Carlo and reporting."""
    print("\n" + "=" * 80)
    print("Comprehensive TradingAgents Analysis")
    print("=" * 80)

    # Create configuration
    config = BacktestConfig(
        initial_capital=Decimal('100000.00'),
        start_date='2023-01-01',
        end_date='2023-12-31',
        commission=Decimal('0.001'),
        slippage=Decimal('0.0005'),
        benchmark='SPY',
        progress_bar=True,
    )

    # Create TradingAgentsGraph
    print("\nInitializing TradingAgentsGraph...")
    trading_graph = TradingAgentsGraph(
        selected_analysts=["market", "news", "fundamentals"],
        debug=False,
    )

    # Create wrapper strategy
    from tradingagents.backtest import TradingAgentsStrategy

    strategy = TradingAgentsStrategy(trading_graph)

    # Create pipeline
    pipeline = BacktestingPipeline(config)

    # Run full analysis
    print("\nRunning comprehensive analysis...")
    analysis = pipeline.run_full_analysis(
        strategy=strategy,
        tickers=['AAPL'],
        monte_carlo=True,
        generate_report=True,
        output_dir='./tradingagents_analysis',
    )

    # Print results
    print("\n" + "=" * 80)
    print("Analysis Complete")
    print("=" * 80)

    results = analysis['backtest_results']
    print(f"\nBacktest Performance:")
    print(f"  Total Return:  {results.total_return:+.2%}")
    print(f"  Sharpe Ratio:  {results.sharpe_ratio:.2f}")
    print(f"  Max Drawdown:  {results.max_drawdown:.2%}")

    if 'monte_carlo' in analysis:
        mc = analysis['monte_carlo']
        print(f"\nMonte Carlo Results:")
        print(f"  Mean Final Value:    ${mc.mean_final_value:,.2f}")
        print(f"  Probability of Profit: {mc.probability_of_profit:.2%}")
        print(f"  95% Confidence:      ${mc.confidence_intervals[0.95][0]:,.2f} - ${mc.confidence_intervals[0.95][1]:,.2f}")

    print(f"\nResults saved to: {analysis.get('report_path', 'N/A')}")

    return analysis


def example_multi_ticker_backtest():
    """Backtest TradingAgents on multiple tickers."""
    print("\n" + "=" * 80)
    print("Multi-Ticker TradingAgents Backtest")
    print("=" * 80)

    # Create TradingAgentsGraph
    trading_graph = TradingAgentsGraph(
        selected_analysts=["market", "fundamentals"],
    )

    # Backtest on multiple tech stocks
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA']

    print(f"\nBacktesting on {len(tickers)} tickers: {', '.join(tickers)}")

    results = backtest_trading_agents(
        trading_graph=trading_graph,
        tickers=tickers,
        start_date='2023-01-01',
        end_date='2023-12-31',
        initial_capital=100000.0,
    )

    print("\nResults:")
    print(f"Total Return:  {results.total_return:+.2%}")
    print(f"Sharpe Ratio:  {results.sharpe_ratio:.2f}")
    print(f"Total Trades:  {results.metrics.total_trades}")

    return results


def main():
    """Run all TradingAgents backtest examples."""
    print("\n" + "=" * 80)
    print("TradingAgents Backtesting Examples")
    print("=" * 80)
    print("\nNote: These examples require LLM API keys to be configured.")
    print("Set up your API keys in .env or environment variables before running.")

    try:
        # Run simple backtest
        example_simple_backtest()

        # Run comprehensive analysis
        # example_comprehensive_analysis()  # Commented out - takes longer

        # Run multi-ticker backtest
        # example_multi_ticker_backtest()  # Commented out - takes longer

    except Exception as e:
        print(f"\nExample failed with error: {e}")
        print("\nMake sure you have:")
        print("1. Configured your LLM API keys")
        print("2. Internet connection for data download")
        print("3. Sufficient API quota")

    print("\n" + "=" * 80)
    print("Examples Complete!")
    print("=" * 80)


if __name__ == '__main__':
    main()
