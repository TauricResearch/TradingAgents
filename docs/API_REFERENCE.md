# TradingAgents Backtest API Reference

## Overview

The TradingAgents backtest module provides a comprehensive framework for backtesting trading strategies using the multi-agent LLM system.

## Core Classes

### TAFlowStrategy

Wrapper class for TradingAgentsGraph to use in backtesting.

```python
from tradingagents.backtest.ta_flow_strategy import TAFlowStrategy

strategy = TAFlowStrategy(config=None, debug=False)
```

#### Parameters
- `config` (dict, optional): Configuration dictionary for TradingAgentsGraph
- `debug` (bool): Enable debug mode for detailed logging

#### Methods

##### decide(ticker: str, date: str) -> str
Get trading decision for a given ticker and date.

**Parameters:**
- `ticker`: Stock symbol (e.g., "AAPL")
- `date`: Date in YYYY-MM-DD format

**Returns:**
- One of "Buy", "Sell", or "Hold"

**Example:**
```python
signal = strategy.decide("AAPL", "2024-01-01")
# Returns: "Buy"
```

### BacktestEngine

Main backtest simulation engine.

```python
from tradingagents.backtest.engine import BacktestEngine

engine = BacktestEngine(initial_capital=100000.0)
```

#### Parameters
- `initial_capital` (float): Starting capital for the simulation

#### Methods

##### run(ticker, start_date, end_date, strategy, fee_rate=0.001, slippage_rate=0.0005, progress_callback=None) -> BacktestResult
Run the backtest simulation.

**Parameters:**
- `ticker` (str): Stock symbol
- `start_date` (str): Start date (YYYY-MM-DD)
- `end_date` (str): End date (YYYY-MM-DD)
- `strategy` (TAFlowStrategy): Strategy object to generate signals
- `fee_rate` (float): Trading fee as percentage of trade value
- `slippage_rate` (float): Slippage as percentage of price
- `progress_callback` (callable, optional): Callback for progress updates

**Returns:**
- `BacktestResult` object with all simulation data

**Example:**
```python
result = engine.run(
    ticker="NVDA",
    start_date="2024-01-01",
    end_date="2024-03-31",
    strategy=strategy,
    fee_rate=0.001,
    slippage_rate=0.0005
)
```

### BacktestResult

Data class containing complete backtest results.

#### Attributes
- `ticker` (str): Stock symbol
- `start_date` (str): Backtest start date
- `end_date` (str): Backtest end date
- `initial_capital` (float): Starting capital
- `final_capital` (float): Ending capital
- `trades` (List[Trade]): List of all trades executed
- `equity_curve` (List[float]): Daily portfolio values
- `daily_returns` (List[float]): Daily return percentages
- `metrics` (PerformanceMetrics): Strategy performance metrics
- `buy_hold_metrics` (PerformanceMetrics): Buy & hold comparison metrics
- `dates` (List[str]): Trading dates

### PerformanceMetrics

Container for all performance metrics.

#### Attributes
- `total_return` (float): Cumulative return
- `annual_return` (float): Annualized return
- `sharpe_ratio` (float): Sharpe ratio (risk-free rate = 0)
- `max_drawdown` (float): Maximum drawdown percentage
- `max_drawdown_duration` (int): Max drawdown duration in days
- `win_rate` (float): Percentage of winning trades
- `profit_factor` (float): Total profits / Total losses
- `total_trades` (int): Total number of trades
- `volatility` (float): Annualized volatility

### BacktestRepository

Repository for storing and retrieving backtest results.

```python
from tradingagents.backtest.persistence import BacktestRepository

repository = BacktestRepository(db_path="results.sqlite")
```

#### Methods

##### save_backtest(result: BacktestResult, config: dict) -> int
Save backtest result to database.

**Returns:**
- ID of saved backtest

##### get_backtest(backtest_id: int) -> dict
Retrieve backtest by ID.

##### list_backtests(ticker=None, start_date=None, end_date=None, limit=100) -> List[BacktestSummary]
List backtests with optional filters.

### ReportManager

Manage HTML report generation and storage.

```python
from tradingagents.backtest.output import ReportManager

manager = ReportManager(reports_dir="reports/")
```

#### Methods

##### save_report(result: BacktestResult, ticker: str, start_date: str, end_date: str) -> Path
Generate and save HTML report.

**Returns:**
- Path to saved report

## Complete Example

```python
from tradingagents.backtest.ta_flow_strategy import TAFlowStrategy
from tradingagents.backtest.engine import BacktestEngine
from tradingagents.backtest.persistence import BacktestRepository
from tradingagents.backtest.output import ReportManager, TerminalReporter
from tradingagents.default_config import DEFAULT_CONFIG

# Configure strategy
config = DEFAULT_CONFIG.copy()
config["online_tools"] = False  # Force offline mode
config["max_debate_rounds"] = 1  # Reduce for faster testing

# Initialize components
strategy = TAFlowStrategy(config=config, debug=True)
engine = BacktestEngine(initial_capital=100000)

# Run backtest
result = engine.run(
    ticker="AAPL",
    start_date="2024-01-01",
    end_date="2024-03-31",
    strategy=strategy,
    fee_rate=0.001,
    slippage_rate=0.0005
)

# Display results
reporter = TerminalReporter()
reporter.display_summary(result.metrics, result.buy_hold_metrics)

# Save to database
repository = BacktestRepository()
backtest_id = repository.save_backtest(result, config)
print(f"Saved with ID: {backtest_id}")

# Generate HTML report
manager = ReportManager()
report_path = manager.save_report(result, "AAPL", "2024-01-01", "2024-03-31")
print(f"Report saved to: {report_path}")
```

## Configuration Options

### Strategy Configuration

```python
config = {
    "online_tools": False,  # Always False for backtesting
    "deep_think_llm": "gpt-4",  # LLM for complex decisions
    "quick_think_llm": "gpt-4o-mini",  # LLM for quick decisions
    "max_debate_rounds": 3,  # Number of debate rounds
    "llm_provider": "openai",  # LLM provider
    "backend_url": None,  # Custom backend URL
}
```

### Position Management Rules

The backtest engine follows these position management rules:

1. **No Position → Buy Signal**: Open long position
2. **No Position → Sell Signal**: Open short position
3. **Long Position → Sell Signal**: Close long, open short
4. **Short Position → Buy Signal**: Close short, open long
5. **Any Position → Hold Signal**: Maintain current position

### Fee and Slippage Calculation

- **Buy Price**: `market_price × (1 + slippage_rate)`
- **Sell Price**: `market_price × (1 - slippage_rate)`
- **Trading Fee**: `trade_value × fee_rate`

## Error Handling

The system includes comprehensive error handling:

- **Strategy Errors**: Return "Hold" signal on error
- **Data Errors**: Raise ValueError with descriptive message
- **Persistence Errors**: Log error and re-raise

## Performance Considerations

- **LLM Calls**: Each trading day requires one LLM call
- **Caching**: Use offline mode to leverage cached data
- **Batch Processing**: Process multiple tickers sequentially
- **Memory**: Results are stored in memory during simulation

## Extending the Framework

### Custom Strategy

```python
class CustomStrategy:
    def decide(self, ticker: str, date: str) -> str:
        # Your logic here
        return "Buy"  # or "Sell" or "Hold"

# Use with BacktestEngine
engine = BacktestEngine()
result = engine.run(ticker="AAPL", strategy=CustomStrategy(), ...)
```

### Custom Metrics

```python
from tradingagents.backtest.metrics import MetricsCalculator

class CustomMetricsCalculator(MetricsCalculator):
    def calculate(self, equity_curve, trades, initial_capital, start_date, end_date):
        metrics = super().calculate(...)
        # Add custom calculations
        metrics.custom_metric = self._calculate_custom_metric(...)
        return metrics
```