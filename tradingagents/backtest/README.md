## TradingAgents Backtesting Framework

A comprehensive, production-ready backtesting framework for testing trading strategies with realistic execution simulation and rigorous performance analysis.

### Features

- **Event-Driven Simulation**: Process historical data bar-by-bar with proper time handling
- **Realistic Execution**: Model slippage, commissions, market impact, and partial fills
- **Look-Ahead Bias Prevention**: Strict data access controls ensure historical accuracy
- **Comprehensive Metrics**: 30+ performance metrics including Sharpe, Sortino, Calmar ratios
- **Monte Carlo Simulation**: Assess risk and confidence intervals for strategy performance
- **Walk-Forward Analysis**: Detect overfitting through in-sample/out-of-sample testing
- **Rich Reporting**: Generate HTML reports with interactive charts
- **TradingAgents Integration**: Seamlessly backtest multi-agent LLM strategies
- **Strategy Comparison**: Compare multiple strategies side-by-side
- **Parallel Processing**: Run multiple backtests concurrently

### Quick Start

```python
from tradingagents.backtest import Backtester, BacktestConfig, BuyAndHoldStrategy
from decimal import Decimal

# Configure backtest
config = BacktestConfig(
    initial_capital=Decimal('100000.00'),
    start_date='2020-01-01',
    end_date='2023-12-31',
    commission=Decimal('0.001'),
    slippage=Decimal('0.0005'),
    benchmark='SPY',
)

# Create strategy
strategy = BuyAndHoldStrategy()

# Run backtest
backtester = Backtester(config)
results = backtester.run(strategy, tickers=['AAPL', 'MSFT'])

# Analyze results
print(f"Total Return: {results.total_return:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")

# Generate report
results.generate_report('backtest_report.html')
```

### Backtesting TradingAgents

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.backtest import backtest_trading_agents

# Create strategy
graph = TradingAgentsGraph(selected_analysts=["market", "fundamentals"])

# Run backtest
results = backtest_trading_agents(
    trading_graph=graph,
    tickers=['AAPL', 'MSFT'],
    start_date='2023-01-01',
    end_date='2023-12-31',
    initial_capital=100000.0,
)

# View results
print(f"Total Return: {results.total_return:.2%}")
results.generate_report('tradingagents_backtest.html')
```

### Custom Strategy

Create your own strategy by extending `BaseStrategy`:

```python
from tradingagents.backtest import BaseStrategy, Signal
from typing import Dict, List
from datetime import datetime
from decimal import Decimal
import pandas as pd

class MyStrategy(BaseStrategy):
    def __init__(self, param1=10):
        super().__init__(name="MyStrategy")
        self.param1 = param1

    def generate_signals(
        self,
        timestamp: datetime,
        data: Dict[str, pd.DataFrame],
        positions: Dict[str, Position],
        portfolio_value: Decimal,
    ) -> List[Signal]:
        signals = []

        for ticker, df in data.items():
            # Your strategy logic here
            if some_buy_condition:
                signals.append(Signal(
                    ticker=ticker,
                    timestamp=timestamp,
                    action='buy',
                    confidence=0.8,
                ))

        return signals
```

### Configuration

The `BacktestConfig` class provides extensive configuration options:

```python
config = BacktestConfig(
    # Core parameters
    initial_capital=Decimal('100000.00'),
    start_date='2020-01-01',
    end_date='2023-12-31',

    # Costs
    commission=Decimal('0.001'),        # 0.1%
    slippage=Decimal('0.0005'),         # 0.05%
    commission_model='percentage',       # 'percentage', 'per_share', 'fixed_per_trade'
    slippage_model='fixed',             # 'fixed', 'volume_based', 'spread_based'

    # Risk controls
    max_position_size=Decimal('0.2'),   # Max 20% per position
    max_leverage=Decimal('1.0'),        # No leverage
    allow_short=False,

    # Benchmark
    benchmark='SPY',

    # Performance metrics
    risk_free_rate=Decimal('0.02'),     # 2% annual

    # Data
    data_source='yfinance',
    cache_data=True,
    cache_dir='./data_cache',

    # System
    progress_bar=True,
    log_level='INFO',
    random_seed=42,
)
```

### Performance Metrics

The framework computes comprehensive metrics:

**Return Metrics**:
- Total Return
- Annualized Return
- Cumulative Return
- Monthly/Daily Returns

**Risk-Adjusted Metrics**:
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio
- Omega Ratio

**Risk Metrics**:
- Volatility (annualized)
- Downside Deviation
- Maximum Drawdown
- Average Drawdown
- Drawdown Duration

**Trade Statistics**:
- Total Trades
- Win Rate
- Profit Factor
- Average Win/Loss
- Best/Worst Trade

**Benchmark Comparison**:
- Alpha
- Beta
- Correlation
- Tracking Error
- Information Ratio

### Monte Carlo Simulation

Assess strategy robustness with Monte Carlo simulation:

```python
from tradingagents.backtest import MonteCarloConfig

mc_config = MonteCarloConfig(
    n_simulations=10000,
    method='resample_returns',  # or 'resample_trades', 'parametric'
    confidence_levels=[0.90, 0.95, 0.99],
)

mc_results = results.monte_carlo(mc_config)

print(f"Mean Final Value: ${mc_results.mean_final_value:,.2f}")
print(f"95% CI: ${mc_results.confidence_intervals[0.95][0]:,.2f} - "
      f"${mc_results.confidence_intervals[0.95][1]:,.2f}")
print(f"Probability of Profit: {mc_results.probability_of_profit:.2%}")
```

### Walk-Forward Analysis

Detect overfitting with walk-forward optimization:

```python
from tradingagents.backtest import WalkForwardConfig

# Define strategy factory
def strategy_factory(short_window, long_window):
    return SimpleMovingAverageStrategy(short_window, long_window)

# Define parameter grid
param_grid = {
    'short_window': [20, 50, 100],
    'long_window': [100, 200, 300],
}

# Configure walk-forward
wf_config = WalkForwardConfig(
    in_sample_months=12,
    out_sample_months=3,
    optimization_metric='sharpe',
)

# Run analysis
wf_results = backtester.walk_forward_analysis(
    strategy_factory=strategy_factory,
    param_grid=param_grid,
    tickers=['AAPL'],
    wf_config=wf_config,
)

print(f"WF Efficiency Ratio: {wf_results.efficiency_ratio:.2f}")
print(f"Overfitting Score: {wf_results.overfitting_score:.2f}")
```

### Strategy Comparison

Compare multiple strategies:

```python
from tradingagents.backtest import compare_strategies

strategies = {
    'Buy & Hold': BuyAndHoldStrategy(),
    'SMA (50/200)': SimpleMovingAverageStrategy(50, 200),
    'SMA (20/50)': SimpleMovingAverageStrategy(20, 50),
}

comparison = compare_strategies(
    strategies=strategies,
    tickers=['AAPL'],
    start_date='2020-01-01',
    end_date='2023-12-31',
)

print(comparison)
```

### Report Generation

Generate comprehensive HTML reports with interactive charts:

```python
# Generate HTML report
results.generate_report('backtest_report.html')

# Export to CSV
results.export_to_csv('./backtest_results')
```

Reports include:
- Equity curve
- Drawdown chart
- Monthly returns heatmap
- Returns distribution
- Trade analysis
- Rolling metrics
- Detailed statistics

### Best Practices

#### 1. Prevent Look-Ahead Bias
The framework automatically prevents look-ahead bias, but ensure your strategy:
- Only uses data available at the current bar
- Doesn't peek into future data
- Uses point-in-time data access

#### 2. Model Realistic Execution
Configure appropriate:
- Commission rates (typical: 0.1% for retail, 0.01% for institutional)
- Slippage (typical: 0.05% for liquid stocks, higher for illiquid)
- Trading hours enforcement
- Market impact for large orders

#### 3. Test Robustness
- Run Monte Carlo simulations
- Perform walk-forward analysis
- Test on multiple time periods
- Test on different universes of stocks

#### 4. Avoid Overfitting
- Use walk-forward optimization
- Keep strategies simple
- Don't over-optimize on in-sample data
- Check WF efficiency ratio (>0.5 is good)

#### 5. Account for Survivor Bias
When testing on current index constituents:
```python
data_handler.check_survivor_bias(tickers)
```

This warns about potential survivor bias.

### Data Sources

Supported data sources:
- **yfinance**: Yahoo Finance (free, default)
- **CSV**: Local CSV files
- **alpha_vantage**: Alpha Vantage API
- **Custom**: Implement your own data loader

Configure data source:
```python
config = BacktestConfig(
    data_source='yfinance',  # or 'csv', 'alpha_vantage'
    cache_data=True,         # Cache for faster reruns
    cache_dir='./cache',
)
```

### Position Sizing

Built-in position sizing methods:

```python
from tradingagents.backtest import PositionSizer

# Equal weight
sizer = PositionSizer(method='equal_weight', params={'num_positions': 10})

# Fixed amount
sizer = PositionSizer(method='fixed_amount', params={'amount': Decimal('10000')})

# Confidence weighted
sizer = PositionSizer(method='confidence_weighted')
```

### Risk Management

Built-in risk controls:

```python
from tradingagents.backtest import RiskManager

risk_manager = RiskManager(
    max_position_size=Decimal('0.2'),  # Max 20% per position
    max_leverage=Decimal('2.0'),        # Max 2x leverage
    stop_loss_pct=Decimal('0.05'),      # 5% stop loss
)
```

### Examples

See the `examples/` directory for complete examples:
- `backtest_example.py`: Comprehensive examples with built-in strategies
- `backtest_tradingagents.py`: TradingAgents-specific examples

Run examples:
```bash
python examples/backtest_example.py
python examples/backtest_tradingagents.py
```

### Testing

Run the test suite:
```bash
pytest tests/backtest/ -v
```

### Performance Tips

1. **Enable Caching**: Cache historical data for faster reruns
2. **Reduce Progress Bar Overhead**: Set `progress_bar=False` for batch jobs
3. **Parallel Backtests**: Use `parallel_backtest()` for multiple strategies
4. **Limit Data**: Use focused date ranges and ticker lists

### Troubleshooting

#### "DataNotFoundError: No data returned"
- Check internet connection
- Verify ticker symbols are correct
- Ensure date range is valid (not too far in past)
- Try different data source

#### "InsufficientCapitalError"
- Increase `initial_capital`
- Reduce position sizes
- Check commission and slippage settings

#### "LookAheadBiasError"
- Ensure strategy only uses historical data
- Check `data_handler.set_current_time()` calls
- Verify data access patterns

### Limitations

1. **Data Quality**: Relies on data source quality
2. **Execution Modeling**: Simplified execution model (no order book)
3. **Corporate Actions**: Limited handling of splits/dividends
4. **Short Selling**: Basic short selling support
5. **Options/Futures**: Not supported (equities only)

### Future Enhancements

Planned features:
- Options backtesting
- Futures support
- More sophisticated execution models
- Real-time paper trading
- Strategy optimization algorithms
- Machine learning integration

### Contributing

To contribute to the backtesting framework:
1. Follow existing code style
2. Add comprehensive tests
3. Update documentation
4. Ensure no look-ahead bias

### License

See main repository LICENSE file.

### Support

For issues or questions:
1. Check documentation
2. Review examples
3. Open GitHub issue
4. Check test cases for usage patterns

---

**Note**: Past performance does not guarantee future results. Backtesting has inherent limitations and should be combined with forward testing and risk management.
