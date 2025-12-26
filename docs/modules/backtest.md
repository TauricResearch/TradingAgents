# Backtest Module

The backtest module provides comprehensive historical strategy replay with realistic slippage and commission modeling, results analysis, and report generation.

## Overview

```
tradingagents/backtest/
    __init__.py          # Public API exports
    backtest_engine.py   # Core backtest engine
    results_analyzer.py  # Metrics and trade analysis
    report_generator.py  # PDF/HTML/JSON/Markdown reports
```

## Quick Start

```python
from tradingagents.backtest import (
    BacktestEngine,
    BacktestConfig,
    ResultsAnalyzer,
    ReportGenerator,
    OHLCV,
    Signal,
    OrderSide,
    PercentageSlippage,
    PercentageCommission,
)
from decimal import Decimal
from datetime import datetime

# Configure backtest
config = BacktestConfig(
    initial_capital=Decimal("100000"),
    slippage_model=PercentageSlippage(Decimal("0.1")),  # 0.1% slippage
    commission_model=PercentageCommission(Decimal("0.1")),  # 0.1% commission
)

# Create engine
engine = BacktestEngine(config)

# Prepare price data
price_data = {
    "AAPL": [
        OHLCV(datetime(2023, 1, 3), 130, 132, 129, 131, 1000000),
        OHLCV(datetime(2023, 1, 4), 131, 135, 130, 134, 1200000),
        OHLCV(datetime(2023, 1, 5), 134, 136, 133, 135, 1100000),
    ],
}

# Define signals
signals = [
    Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
    Signal(datetime(2023, 1, 5), "AAPL", OrderSide.SELL, Decimal("100")),
]

# Run backtest
result = engine.run(price_data, signals)

# Analyze results
analyzer = ResultsAnalyzer()
analysis = analyzer.analyze(result)

# Generate report
generator = ReportGenerator()
report = generator.generate(result, analysis)
```

## Backtest Engine

### BacktestConfig

Configuration for backtest execution:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `initial_capital` | `Decimal` | Required | Starting capital |
| `slippage_model` | `SlippageModel` | `NoSlippage()` | Slippage model |
| `commission_model` | `CommissionModel` | `NoCommission()` | Commission model |
| `allow_fractional` | `bool` | `True` | Allow fractional shares |
| `margin_enabled` | `bool` | `False` | Enable margin trading |

### Slippage Models

Built-in slippage models:

```python
from tradingagents.backtest import (
    NoSlippage,           # No slippage
    FixedSlippage,        # Fixed amount per share
    PercentageSlippage,   # Percentage of price
    VolumeSlippage,       # Volume-impact model
)

# Fixed: $0.01 per share
slippage = FixedSlippage(Decimal("0.01"))

# Percentage: 0.1% of price
slippage = PercentageSlippage(Decimal("0.1"))

# Volume impact: 0.1% per 1% of daily volume
slippage = VolumeSlippage(
    base_impact=Decimal("0.1"),
    volume_factor=Decimal("0.01"),
)
```

### Commission Models

Built-in commission models:

```python
from tradingagents.backtest import (
    NoCommission,           # No commission
    FixedCommission,        # Fixed per trade
    PerShareCommission,     # Per share
    PercentageCommission,   # Percentage of value
    TieredCommission,       # Tiered by trade value
)

# Fixed: $5 per trade
commission = FixedCommission(Decimal("5"))

# Per share: $0.005 per share, min $1, max $10
commission = PerShareCommission(
    per_share=Decimal("0.005"),
    minimum=Decimal("1"),
    maximum=Decimal("10"),
)

# Percentage: 0.1% of trade value
commission = PercentageCommission(Decimal("0.1"))

# Tiered: Different rates by trade size
commission = TieredCommission(tiers=[
    (Decimal("10000"), Decimal("0.2")),   # 0.2% for trades < $10k
    (Decimal("100000"), Decimal("0.1")),  # 0.1% for trades < $100k
    (None, Decimal("0.05")),               # 0.05% for larger trades
])
```

### BacktestResult

The result contains:

- `initial_capital`: Starting capital
- `final_value`: Ending portfolio value
- `total_return`: Total return percentage
- `total_trades`: Number of trades executed
- `winning_trades`: Number of profitable trades
- `losing_trades`: Number of losing trades
- `win_rate`: Win rate percentage
- `profit_factor`: Gross profit / gross loss
- `max_drawdown`: Maximum drawdown percentage
- `sharpe_ratio`: Sharpe ratio
- `sortino_ratio`: Sortino ratio
- `trades`: List of BacktestTrade records
- `snapshots`: List of BacktestSnapshot records

## Results Analyzer

### AnalysisResult

Comprehensive analysis output:

```python
analyzer = ResultsAnalyzer()
analysis = analyzer.analyze(result)

# Risk metrics
print(f"Sharpe: {analysis.risk_metrics.sharpe_ratio}")
print(f"Sortino: {analysis.risk_metrics.sortino_ratio}")
print(f"Calmar: {analysis.risk_metrics.calmar_ratio}")
print(f"VaR (95%): {analysis.risk_metrics.var_95}")
print(f"CVaR (95%): {analysis.risk_metrics.cvar_95}")

# Trade statistics
print(f"Win rate: {analysis.trade_statistics.win_rate}%")
print(f"Profit factor: {analysis.trade_statistics.profit_factor}")
print(f"Max win streak: {analysis.trade_statistics.max_win_streak}")
print(f"Average trade: {analysis.trade_statistics.avg_trade}")

# Drawdown analysis
print(f"Max drawdown: {analysis.drawdown_analysis.max_drawdown}%")
print(f"Recovery time: {analysis.drawdown_analysis.max_drawdown_duration} days")

# Monthly performance
for breakdown in analysis.monthly_performance:
    print(f"{breakdown.period}: {breakdown.return_pct}%")
```

### RiskMetrics

| Metric | Description |
|--------|-------------|
| `sharpe_ratio` | Risk-adjusted return (vs risk-free rate) |
| `sortino_ratio` | Downside risk-adjusted return |
| `calmar_ratio` | Return / max drawdown |
| `var_95` | 5% worst-case daily loss |
| `cvar_95` | Average of 5% worst days |
| `ulcer_index` | Depth and duration of drawdowns |
| `max_drawdown` | Maximum peak-to-trough decline |
| `max_drawdown_duration` | Longest drawdown period (days) |
| `recovery_factor` | Total return / max drawdown |

### TradeStatistics

| Metric | Description |
|--------|-------------|
| `total_trades` | Total number of trades |
| `win_rate` | Percentage of winning trades |
| `profit_factor` | Gross profit / gross loss |
| `max_win` | Largest winning trade |
| `max_loss` | Largest losing trade |
| `avg_trade` | Average trade P&L |
| `median_trade` | Median trade P&L |
| `max_win_streak` | Longest winning streak |
| `max_loss_streak` | Longest losing streak |
| `avg_holding_period` | Average trade duration |

## Report Generator

### ReportConfig

Configure report output:

```python
from tradingagents.backtest import (
    ReportGenerator,
    ReportConfig,
    ReportFormat,
    ReportSection,
)

config = ReportConfig(
    format=ReportFormat.HTML,
    sections=[
        ReportSection.SUMMARY,
        ReportSection.TRADES,
        ReportSection.PERFORMANCE,
        ReportSection.RISK,
        ReportSection.CHARTS,
    ],
    include_charts=True,
    color_scheme={
        "primary": "#2196F3",
        "positive": "#4CAF50",
        "negative": "#F44336",
    },
)

generator = ReportGenerator(config)
report = generator.generate(result, analysis)
```

### Output Formats

| Format | Description |
|--------|-------------|
| `HTML` | Interactive HTML with embedded CSS |
| `PDF` | PDF document (requires WeasyPrint) |
| `JSON` | Structured JSON data |
| `MARKDOWN` | Plain Markdown text |

### Report Sections

| Section | Content |
|---------|---------|
| `SUMMARY` | High-level metrics overview |
| `TRADES` | Individual trade records |
| `PERFORMANCE` | Monthly/yearly returns |
| `RISK` | Risk metrics and analysis |
| `CHARTS` | Equity curves, drawdown charts |
| `POSITIONS` | Position history |

### Charts

Built-in SVG charts:

- **Equity Curve**: Portfolio value over time
- **Drawdown Chart**: Underwater equity chart
- **Monthly Returns Heatmap**: Color-coded monthly returns

```python
# Get chart data
charts = generator.generate_charts(result, analysis)

equity_svg = charts["equity_curve"]
drawdown_svg = charts["drawdown"]
heatmap_svg = charts["monthly_heatmap"]
```

## Factory Functions

Convenience functions for common configurations:

```python
from tradingagents.backtest import (
    create_backtest_engine,
    create_results_analyzer,
    create_report_generator,
)

# Create engine with common settings
engine = create_backtest_engine(
    initial_capital=100000,
    slippage_pct=0.1,
    commission_pct=0.1,
)

# Create analyzer
analyzer = create_results_analyzer()

# Create report generator
generator = create_report_generator(format="html")
```

## See Also

- [Results Analyzer API](../api/results-analyzer.md)
- [Report Generator API](../api/report-generator.md)
- [Backtesting Guide](../guides/backtesting.md)
