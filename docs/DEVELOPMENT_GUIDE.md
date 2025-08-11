# TradingAgents Backtest Development Guide

## Project Structure

```
TradingAgents/
├── tradingagents/
│   └── backtest/
│       ├── __init__.py
│       ├── ta_flow_strategy.py    # Strategy wrapper
│       ├── engine.py               # Simulation engine
│       ├── metrics.py              # Performance metrics
│       ├── output.py               # Output and reporting
│       └── persistence.py          # Database storage
├── cli/
│   └── commands/
│       └── backtest.py             # CLI commands
├── tests/
│   ├── unit/                       # Unit tests
│   ├── integration/                # Integration tests
│   └── conftest.py                 # Test fixtures
├── docs/
│   ├── 001-007_*.md               # Implementation tickets
│   ├── API_REFERENCE.md           # API documentation
│   └── BACKTEST_README.md         # User guide
└── requirements.txt                # Dependencies
```

## Development Setup

### Environment Setup

```bash
# Create virtual environment
conda create -n tradingagents python=3.11
conda activate tradingagents

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

### Required Environment Variables

```bash
export OPENAI_API_KEY=your_openai_api_key
export FINNHUB_API_KEY=your_finnhub_api_key
```

## Running Tests

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit -v

# Run specific test file
pytest tests/unit/test_ta_flow_strategy.py -v

# Run with coverage
pytest tests/unit --cov=tradingagents.backtest --cov-report=html
```

### Integration Tests

```bash
# Run integration tests
pytest tests/integration -v -m integration

# Skip slow tests
pytest -m "not slow"
```

### Test Coverage

```bash
# Generate coverage report
pytest --cov=tradingagents.backtest --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html
```

## Code Style Guide

### Python Style

- Follow PEP 8
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use docstrings for all public methods

### Example:

```python
from typing import List, Dict, Optional

def calculate_metrics(
    equity_curve: List[float],
    trades: List[Trade],
    initial_capital: float
) -> PerformanceMetrics:
    """Calculate performance metrics from backtest results.
    
    Args:
        equity_curve: List of portfolio values over time
        trades: List of executed trades
        initial_capital: Starting capital amount
        
    Returns:
        PerformanceMetrics object with calculated metrics
        
    Raises:
        ValueError: If equity_curve is empty
    """
    if not equity_curve:
        raise ValueError("Equity curve cannot be empty")
    
    # Implementation
    return metrics
```

### Import Order

1. Standard library imports
2. Third-party imports
3. Local application imports

```python
import logging
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import numpy as np
from rich.console import Console

from tradingagents.backtest.metrics import PerformanceMetrics
from tradingagents.default_config import DEFAULT_CONFIG
```

## Adding New Features

### 1. Create Feature Branch

```bash
git checkout -b feature/new-indicator
```

### 2. Implement Feature

Follow the existing patterns:

```python
# In metrics.py
def _calculate_new_indicator(self, data: List[float]) -> float:
    """Calculate new indicator.
    
    Args:
        data: Input data series
        
    Returns:
        Calculated indicator value
    """
    # Implementation
    return result
```

### 3. Add Tests

```python
# In test_metrics_calculator.py
def test_new_indicator_calculation(self):
    """Test new indicator calculation."""
    calculator = MetricsCalculator()
    result = calculator._calculate_new_indicator([1, 2, 3, 4, 5])
    assert result == expected_value
```

### 4. Update Documentation

- Add to API_REFERENCE.md
- Update relevant ticket documentation
- Add usage example to BACKTEST_README.md

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)

# Or for specific module
logger = logging.getLogger('tradingagents.backtest')
logger.setLevel(logging.DEBUG)
```

### Common Issues

#### Issue: "No price data available"
**Solution:** Check internet connection and ticker symbol validity

#### Issue: LLM timeout
**Solution:** Increase timeout or use faster model

```python
config = {
    "quick_think_llm": "gpt-4o-mini",  # Faster model
    "max_debate_rounds": 1,  # Reduce rounds
}
```

#### Issue: Memory error with large backtests
**Solution:** Process in chunks or reduce date range

## Performance Optimization

### 1. Use Offline Mode

Always set `online_tools = False` for backtesting to use cached data.

### 2. Optimize LLM Usage

```python
config = {
    "quick_think_llm": "gpt-4o-mini",  # Use faster model
    "max_debate_rounds": 1,  # Reduce debate rounds
}
```

### 3. Batch Processing

Process multiple backtests efficiently:

```python
tickers = ["AAPL", "GOOGL", "MSFT"]
results = []

for ticker in tickers:
    result = engine.run(ticker=ticker, ...)
    results.append(result)
    
    # Save periodically to avoid memory issues
    if len(results) % 10 == 0:
        save_results(results)
        results.clear()
```

## Database Schema

### backtests table

```sql
CREATE TABLE backtests (
    id INTEGER PRIMARY KEY,
    ticker VARCHAR(10),
    start_date DATE,
    end_date DATE,
    initial_capital DECIMAL(10,2),
    final_capital DECIMAL(10,2),
    total_return DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    -- ... other metrics
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### trades table

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    backtest_id INTEGER,
    trade_date DATE,
    action VARCHAR(10),
    price DECIMAL(10,4),
    shares DECIMAL(10,4),
    fee DECIMAL(10,4),
    FOREIGN KEY (backtest_id) REFERENCES backtests(id)
);
```

## Contributing

### Pull Request Process

1. Create feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass
4. Update documentation
5. Submit PR with clear description

### Commit Messages

Follow conventional commits:

```
feat: add new performance metric
fix: correct slippage calculation
docs: update API reference
test: add integration tests for persistence
refactor: simplify metrics calculation
```

## Release Process

1. Update version in `setup.py`
2. Update CHANGELOG.md
3. Run full test suite
4. Create release tag
5. Build and publish package

```bash
# Build package
python setup.py sdist bdist_wheel

# Upload to PyPI (if applicable)
twine upload dist/*
```

## Monitoring and Maintenance

### Log Files

Logs are stored in:
- `logs/backtest_*.log` - Backtest execution logs
- `results_dir/*/message_tool.log` - Agent communication logs

### Database Maintenance

```python
# Backup database
from tradingagents.backtest.persistence import DataMigration

DataMigration.backup_database("results.sqlite", "backup/results_backup.sqlite")

# Export to CSV
repository = BacktestRepository()
DataMigration.export_to_csv(repository, backtest_id=1, output_dir="exports/")
```

### Performance Monitoring

Monitor key metrics:
- Execution time per backtest
- Memory usage
- Database size
- API call counts

## Future Enhancements

### Planned Features

1. **Multi-asset Portfolio Backtesting**
   - Support multiple positions
   - Portfolio rebalancing
   - Correlation analysis

2. **Advanced Risk Metrics**
   - VaR (Value at Risk)
   - CVaR (Conditional VaR)
   - Sortino ratio

3. **Real-time Integration**
   - Live trading connection
   - Paper trading mode
   - Alert system

4. **Performance Optimization**
   - Parallel processing
   - GPU acceleration for metrics
   - Distributed backtesting

### Extension Points

The framework is designed to be extensible:

1. **Custom Strategies**: Implement the `decide()` method
2. **Custom Metrics**: Extend `MetricsCalculator`
3. **Custom Output Formats**: Extend `ReportManager`
4. **Custom Data Sources**: Implement data fetcher interface