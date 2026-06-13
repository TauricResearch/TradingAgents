# Stock Holdings Management Guide

## Overview

This guide explains how to use the stock holdings management system in the TradingAgents project. The system allows you to track, analyze, and manage your stock portfolio with automated updates through GitHub Actions.

## Features

- **Portfolio Tracking**: Maintain a list of stock holdings with purchase and current prices
- **Automatic Updates**: GitHub Actions workflows automatically update holdings data
- **Portfolio Analytics**: Calculate gains/losses, sector distribution, and performance metrics
- **Data Management**: Add, update, and retrieve holdings using simple Python APIs

## File Structure

```
TradingAgents/
├── data/
│   └── holdings.json              # Main holdings data file
├── scripts/
│   └── fetch_holdings.py          # Data management script
├── tradingagents/
│   └── holdings_api.py            # Python API for holdings
├── tests/
│   └── test_holdings.py           # Unit tests
├── .github/workflows/
│   └── update-holdings.yml        # Automated update workflow
└── docs/
    └── HOLDINGS_GUIDE.md          # This file
```

## Data Format

### holdings.json Structure

```json
{
  "holdings": [
    {
      "id": 1,
      "symbol": "AAPL",
      "company_name": "Apple Inc.",
      "quantity": 100,
      "purchase_price": 150.25,
      "current_price": 180.50,
      "purchase_date": "2024-01-15",
      "sector": "Technology",
      "status": "active"
    }
  ],
  "portfolio_summary": {
    "total_holdings": 1,
    "total_quantity": 100,
    "total_invested": 15025.00,
    "total_current_value": 18050.00,
    "total_gain_loss": 3025.00,
    "gain_loss_percentage": 20.12,
    "last_updated": "2026-06-13T00:00:00Z"
  }
}
```

## Usage

### 1. Using the HoldingsManager Script

#### Display Portfolio Report

```bash
python scripts/fetch_holdings.py
```

Output:
```
================================================================================
STOCK HOLDINGS PORTFOLIO REPORT
================================================================================
Last Updated: 2026-06-13T10:30:00Z
--------------------------------------------------------------------------------
Total Holdings: 3
Total Quantity: 225 shares
Total Invested: $51,256.25
Current Value: $81,768.75
Total Gain/Loss: $30,512.50 (+59.56%)
--------------------------------------------------------------------------------

Detailed Holdings:
Symbol     Company                  Qty  Purchase    Current  Gain/Loss    Return %
--------------------------------------------------------------------------------
AAPL       Apple Inc.             100   $150.25    $180.50    $3,025.00      +20.17%
MSFT       Microsoft Corporation   50   $310.00    $380.75    $3,537.50      +22.81%
GOOGL      Alphabet Inc.           75   $120.50    $155.30    $2,610.00      +28.81%
================================================================================
```

#### Using the HoldingsManager API

```python
from scripts.fetch_holdings import HoldingsManager

# Initialize manager
manager = HoldingsManager("data/holdings.json")

# Add a new holding
manager.add_holding(
    symbol="TSLA",
    company_name="Tesla Inc.",
    quantity=50,
    purchase_price=250.00,
    current_price=280.00,
    purchase_date="2024-06-01",
    sector="Technology"
)

# Update a stock price
manager.update_holding_price("AAPL", 185.00)

# Get a specific holding
apple_holding = manager.get_holding_by_symbol("AAPL")

# Get portfolio summary
summary = manager.calculate_portfolio_summary()
print(f"Total Value: ${summary['total_current_value']}")
print(f"Gain/Loss: ${summary['total_gain_loss']}")
```

### 2. Using the HoldingsAPI

The `HoldingsAPI` provides a read-focused interface for querying holdings data.

```python
from tradingagents.holdings_api import get_api_instance

# Get API instance
api = get_api_instance("data/holdings.json")

# Get all holdings
all_holdings = api.get_all_holdings()

# Get specific holding
holding = api.get_holding_by_symbol("AAPL")

# Get holdings by sector
tech_stocks = api.get_holdings_by_sector("Technology")

# Get portfolio summary
summary = api.get_portfolio_summary()

# Calculate individual returns
returns = api.calculate_individual_return("AAPL")
print(f"AAPL Return: {returns['return_percent']}%")

# Get top performers
top_5 = api.get_top_performers(limit=5)

# Get sector distribution
distribution = api.get_sector_distribution()
print(f"Technology: {distribution.get('Technology', 0)}%")

# Get comprehensive statistics
stats = api.get_stats()
```

### 3. GitHub Actions Workflow

The `update-holdings.yml` workflow automatically updates your holdings data:

**Triggers:**
- Daily at 9:00 AM UTC (market open)
- On push to main branch
- Manual trigger (workflow_dispatch)

**What it does:**
1. Checks out the repository
2. Sets up Python environment
3. Runs the holdings update script
4. Commits changes if data has been updated
5. Creates a workflow summary

#### Manual Trigger

Go to: **GitHub Actions → Update Stock Holdings → Run workflow**

## API Reference

### HoldingsManager

```python
class HoldingsManager:
    def load_holdings() -> dict
    def save_holdings() -> None
    def calculate_portfolio_summary() -> dict
    def add_holding(symbol, company_name, quantity, purchase_price, 
                   current_price, purchase_date, sector) -> dict
    def update_holding_price(symbol, new_price) -> bool
    def get_portfolio_summary() -> dict
    def get_all_holdings() -> list
    def get_holding_by_symbol(symbol) -> dict | None
    def print_portfolio_report() -> None
```

### HoldingsAPI

```python
class HoldingsAPI:
    def get_all_holdings() -> List[Dict]
    def get_holding_by_symbol(symbol) -> Optional[Dict]
    def get_holdings_by_sector(sector) -> List[Dict]
    def get_portfolio_summary() -> Dict
    def calculate_individual_return(symbol) -> Optional[Dict]
    def get_top_performers(limit=5) -> List[Dict]
    def get_sector_distribution() -> Dict[str, float]
    def get_stats() -> Dict
```

## Testing

Run the test suite:

```bash
pytest tests/test_holdings.py -v
```

## Examples

### Example 1: Track Portfolio Performance

```python
from tradingagents.holdings_api import get_api_instance

api = get_api_instance()
summary = api.get_portfolio_summary()

print(f"Portfolio Value: ${summary['total_current_value']:,.2f}")
print(f"Total Gain/Loss: ${summary['total_gain_loss']:,.2f}")
print(f"Return: {summary['gain_loss_percentage']:.2f}%")
```

### Example 2: Analyze Sector Distribution

```python
from tradingagents.holdings_api import get_api_instance

api = get_api_instance()
distribution = api.get_sector_distribution()

for sector, percentage in distribution.items():
    print(f"{sector}: {percentage:.1f}%")
```

### Example 3: Find Top Performers

```python
from tradingagents.holdings_api import get_api_instance

api = get_api_instance()
top_performers = api.get_top_performers(limit=3)

for stock in top_performers:
    print(f"{stock['symbol']}: {stock['return_percent']:+.2f}%")
```

## Troubleshooting

### Missing holdings.json

Ensure the `data/holdings.json` file exists with valid JSON structure.

### Workflow Not Running

Check GitHub Actions logs: **Settings → Actions → Workflows**

### Import Errors

Ensure you're running scripts from the project root directory:

```bash
cd /path/to/TradingAgents
python scripts/fetch_holdings.py
```

## Best Practices

1. **Backup Data**: Keep backups of `data/holdings.json` before major updates
2. **Regular Updates**: Run the workflow regularly to keep prices current
3. **Verify Data**: Always verify new holdings before adding to the portfolio
4. **Document Changes**: Commit changes with clear messages
5. **Test Changes**: Run tests after making modifications

## Contributing

To contribute improvements:

1. Create a feature branch
2. Make your changes
3. Run tests: `pytest tests/test_holdings.py`
4. Submit a pull request

## Support

For issues or questions, please refer to the main README.md or open an issue in the repository.
