# TradingAgents - Indian Stock Market Integration

## Overview

This module extends the TradingAgents framework to support the Indian stock market (NSE/BSE), providing comprehensive analysis capabilities tailored for Indian equities, market dynamics, and regulatory environment.

## Features

### 🇮🇳 Indian Market Support
- **NSE (National Stock Exchange)** and **BSE (Bombay Stock Exchange)** integration
- Indian market hours and holidays
- INR currency support
- SEBI regulations compliance
- T+1 settlement cycle

### 📊 Data Sources
- **Primary**: Alpha Vantage (with Indian stocks support)
- **Secondary**: Yahoo Finance (for NSE/BSE tickers)
- **Fallback**: Direct NSE API (unofficial)
- **News**: Indian financial news sources
- **Sentiment**: Indian social media and forums

### 🔧 Core Components

#### 1. Configuration (`tradingagents/indian_config.py`)
- Market parameters and trading hours
- Major Indian stocks database
- Sector classifications
- Risk management parameters
- Market holidays calendar

#### 2. Ticker Utilities (`tradingagents/dataflows/ticker_utils.py`)
- NSE/BSE ticker formatting (`.NS`, `.BO` suffixes)
- Cross-exchange ticker conversion
- Ticker validation and processing
- Support for major Indian stocks

#### 3. Data Interface (`tradingagents/dataflows/indian_interface.py`)
- Unified data access layer
- Multiple data source fallbacks
- Indian market-specific data formatting
- Error handling and rate limiting

#### 4. Market Analysts
- **Fundamentals Analyst**: Indian accounting standards, SEBI compliance
- **Market Analyst**: Technical analysis with Indian market patterns
- **Sector Analysis**: Indian industry dynamics

#### 5. Agent Toolkit (`tradingagents/agents/utils/indian_agent_toolkit.py`)
- Comprehensive toolkit for Indian market operations
- Risk management and position sizing
- Portfolio analysis and tracking
- Market timing and execution

#### 6. CLI Interface (`cli/indian_cli.py`)
- Command-line interface for analysis
- Market status and overview
- Stock and sector analysis
- Portfolio management

## Installation

### Prerequisites
```bash
# Install Python dependencies
pip install -r requirements.txt

# Additional Indian market dependencies
pip install alpha-vantage click beautifulsoup4 lxml
```

### Environment Setup
```bash
# Set up API keys (optional but recommended)
export ALPHA_VANTAGE_API_KEY="your_alpha_vantage_key"
export NEWS_API_KEY="your_news_api_key"
export TWITTER_API_KEY="your_twitter_api_key"
```

## Quick Start

### 1. Basic Usage
```python
from tradingagents.agents.utils.indian_agent_toolkit import indian_toolkit

# Check market status
status = indian_toolkit.check_market_status()
print(f"Market is {'open' if status['is_market_open'] else 'closed'}")

# Analyze a stock
analysis = indian_toolkit.analyze_fundamentals("RELIANCE", "NSE")
print(analysis['analysis'])

# Get technical analysis
technical = indian_toolkit.analyze_technical("TCS", "NSE", lookback_days=30)
print(technical['technical_analysis'])
```

### 2. CLI Usage
```bash
# Check market status
python cli/indian_cli.py market status

# Analyze a stock
python cli/indian_cli.py stock analyze RELIANCE --exchange NSE

# Get market overview
python cli/indian_cli.py market overview

# Analyze a sector
python cli/indian_cli.py sector analyze banking

# Calculate position size
python cli/indian_cli.py portfolio position-size RELIANCE 2500 2400 1000000 --risk 2
```

### 3. Example Script
```bash
# Run the comprehensive example
python examples/indian_market_example.py
```

## Supported Stocks

### Major Indian Stocks
- **Banking**: HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK
- **IT**: TCS, INFY, HCLTECH, WIPRO, TECHM
- **Energy**: RELIANCE, ONGC, IOC, BPCL
- **FMCG**: HINDUNILVR, ITC, NESTLEIND, BRITANNIA
- **Auto**: MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO
- **Pharma**: SUNPHARMA, DRREDDY, CIPLA, DIVISLAB

### Sectors Supported
- Banking, IT, FMCG, Auto, Pharma, Energy, Telecom, Metals, Cement, NBFC

## API Reference

### Core Functions

#### Market Data
```python
# Get historical data
data = indian_toolkit.get_indian_stock_data("RELIANCE", "2024-01-01", "2024-12-31", "NSE")

# Get real-time quote
quote = indian_toolkit.get_indian_stock_quote("TCS", "NSE")

# Get fundamentals
fundamentals = indian_toolkit.get_indian_fundamentals("HDFCBANK", "NSE")
```

#### Analysis
```python
# Fundamental analysis
fund_analysis = indian_toolkit.analyze_fundamentals("INFY", "NSE")

# Technical analysis
tech_analysis = indian_toolkit.analyze_technical("MARUTI", "NSE", lookback_days=60)

# Market conditions
market_conditions = indian_toolkit.analyze_market_conditions()

# Sector analysis
sector_analysis = indian_toolkit.get_sector_analysis("banking")
```

#### Risk Management
```python
# Position sizing
position = indian_toolkit.calculate_position_size(
    symbol="RELIANCE", 
    entry_price=2500, 
    stop_loss=2400, 
    portfolio_value=1000000, 
    risk_percentage=0.02
)

# Risk assessment
risk = indian_toolkit.assess_stock_risk("TCS", "NSE")
```

#### Utilities
```python
# Ticker formatting
formatted = indian_toolkit.format_ticker("RELIANCE", "NSE")  # Returns "RELIANCE.NS"

# Ticker validation
is_valid = indian_toolkit.validate_ticker("TCS.NS")  # Returns True

# Get sector stocks
banking_stocks = indian_toolkit.get_sector_stocks("banking")
```

### Configuration Options

#### Market Parameters
```python
from tradingagents.indian_config import get_indian_config

config = get_indian_config()
print(config['trading_hours'])  # {'open': '09:15', 'close': '15:30', ...}
print(config['market_parameters']['settlement'])  # 'T+1'
print(config['risk_parameters']['max_position_size'])  # 0.05 (5%)
```

#### Ticker Utilities
```python
from tradingagents.dataflows.ticker_utils import TickerManager

manager = TickerManager()
result = manager.process_ticker("RELIANCE", "NSE")
print(result['formatted_ticker'])  # 'RELIANCE.NS'
print(result['cross_exchange_ticker'])  # '500325.BO'
```

## Integration with TradingAgents Framework

### Graph Integration
The Indian market components integrate seamlessly with the existing TradingAgents graph-based system:

```python
# Example integration with trading graph
from tradingagents.graph.trading_graph import TradingGraph
from tradingagents.agents.analysts.indian_fundamentals_analyst import IndianFundamentalsAnalyst
from tradingagents.agents.analysts.indian_market_analyst import IndianMarketAnalyst

# Initialize analysts
fund_analyst = IndianFundamentalsAnalyst()
market_analyst = IndianMarketAnalyst()

# Use in trading decisions
symbol = "RELIANCE"
fund_analysis = fund_analyst.analyze_fundamentals(symbol, "NSE")
market_analysis = market_analyst.analyze_stock_technical(symbol, "NSE")

# Combine analyses for trading decision
# (Integration with existing graph logic)
```

### Agent Toolkit Integration
```python
# Use Indian toolkit in existing agents
from tradingagents.agents.utils.indian_agent_toolkit import indian_toolkit

# Replace US data calls with Indian equivalents
indian_data = indian_toolkit.get_indian_stock_data(symbol, start_date, end_date, "NSE")
# Instead of: us_data = get_YFin_data(symbol, start_date, end_date)
```

## Testing

### Run Tests
```bash
# Run all Indian market tests
python -m pytest tests/test_indian_market.py -v

# Run specific test categories
python -m pytest tests/test_indian_market.py::TestIndianConfig -v
python -m pytest tests/test_indian_market.py::TestTickerUtils -v
```

### Test Coverage
- Configuration validation
- Ticker utilities (formatting, validation, conversion)
- Data source integration
- Analyst functionality
- Error handling
- Integration tests

## CLI Commands Reference

### Market Commands
```bash
# Market status
python cli/indian_cli.py market status

# Market overview
python cli/indian_cli.py market overview --date 2024-01-15
```

### Stock Commands
```bash
# Comprehensive analysis
python cli/indian_cli.py stock analyze RELIANCE --exchange NSE --days 30

# Get quote
python cli/indian_cli.py stock quote TCS --exchange NSE

# Historical data
python cli/indian_cli.py stock data HDFCBANK --days 60 --output csv
```

### Sector Commands
```bash
# Sector analysis
python cli/indian_cli.py sector analyze banking --date 2024-01-15

# List available sectors
python cli/indian_cli.py sector list
```

### Portfolio Commands
```bash
# Position sizing
python cli/indian_cli.py portfolio position-size RELIANCE 2500 2400 1000000 --risk 2

# Portfolio analysis (requires portfolio JSON file)
python cli/indian_cli.py portfolio analyze --file my_portfolio.json
```

### Utility Commands
```bash
# Validate ticker
python cli/indian_cli.py utils validate RELIANCE --exchange NSE

# List major stocks
python cli/indian_cli.py utils stocks

# Show configuration
python cli/indian_cli.py utils config
```

## Data Sources and APIs

### Primary: Alpha Vantage
- **Endpoint**: `https://www.alphavantage.co/query`
- **Rate Limit**: 5 calls/minute (free tier)
- **Coverage**: NSE/BSE stocks, fundamentals, technical indicators
- **Setup**: Set `ALPHA_VANTAGE_API_KEY` environment variable

### Secondary: Yahoo Finance
- **Library**: `yfinance`
- **Rate Limit**: ~30 calls/minute
- **Coverage**: NSE (.NS) and BSE (.BO) tickers
- **Advantages**: Free, reliable, good historical data

### Fallback: NSE Direct API
- **Endpoint**: `https://www.nseindia.com/api`
- **Rate Limit**: ~20 calls/minute
- **Coverage**: Real-time NSE data
- **Note**: Unofficial API, may require session management

### News Sources (Planned)
- Economic Times API
- Moneycontrol scraping
- Business Standard RSS
- NSE/BSE announcements

## Market-Specific Considerations

### Indian Market Characteristics
- **Trading Hours**: 9:15 AM - 3:30 PM IST (Monday-Friday)
- **Pre-open Session**: 9:00 AM - 9:15 AM IST
- **Settlement**: T+1 (Trade + 1 day)
- **Circuit Breakers**: ±20% for individual stocks, ±10% for indices
- **Lot Sizes**: Vary by stock (usually 1 for equity)

### Regulatory Environment
- **SEBI**: Securities and Exchange Board of India
- **Disclosure Requirements**: Quarterly results, annual reports
- **FII/DII Limits**: Foreign and domestic institutional investor limits
- **Insider Trading**: Strict regulations and monitoring

### Currency and Conversion
- **Base Currency**: INR (Indian Rupees)
- **USD-INR Tracking**: Important for FII flows and global correlation
- **Currency Hedging**: Available for international exposure

## Risk Management

### Position Sizing
```python
# Conservative approach for Indian markets
position = indian_toolkit.calculate_position_size(
    symbol="RELIANCE",
    entry_price=2500,
    stop_loss=2400,  # 4% stop loss
    portfolio_value=1000000,  # 10 Lakh INR
    risk_percentage=0.02  # 2% portfolio risk
)
```

### Risk Parameters
- **Maximum Position Size**: 5% of portfolio (configurable)
- **Default Stop Loss**: 8% (higher volatility adjustment)
- **Volatility Adjustment**: 1.2x (Indian markets more volatile)
- **Liquidity Threshold**: ₹10 Lakh daily volume minimum

### Risk Assessment
- **Fundamental Risks**: Debt levels, promoter holding, pledge status
- **Technical Risks**: Volatility, support/resistance levels
- **Market Risks**: FII flows, currency movement, policy changes
- **Sector Risks**: Regulatory changes, competition, cyclical factors

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Install missing dependencies
pip install -r requirements.txt
pip install alpha-vantage click beautifulsoup4
```

#### API Rate Limits
```python
# Use multiple data sources
# Alpha Vantage: 5 calls/min
# Yahoo Finance: 30 calls/min
# NSE Direct: 20 calls/min
```

#### Data Quality Issues
```python
# Check data availability
data = indian_toolkit.get_indian_stock_data("SYMBOL", start_date, end_date)
if "Error" in data or "No data" in data:
    print("Data not available, try different source or date range")
```

### Performance Optimization
- Use data caching for repeated requests
- Implement proper rate limiting
- Batch API calls where possible
- Use async operations for multiple stocks

## Contributing

### Adding New Stocks
1. Update `MAJOR_INDIAN_STOCKS` in `indian_config.py`
2. Add NSE-BSE mapping in `ticker_utils.py`
3. Update sector classifications
4. Add tests for new stocks

### Adding New Data Sources
1. Create new API client in `indian_market_utils.py`
2. Add to data source fallback chain
3. Implement rate limiting and error handling
4. Add configuration options

### Extending Analysis
1. Create new analyst class inheriting from base
2. Implement Indian market-specific logic
3. Add to agent toolkit
4. Create CLI commands

## Roadmap

### Phase 1 (Current)
- ✅ Basic NSE/BSE support
- ✅ Fundamental and technical analysis
- ✅ CLI interface
- ✅ Risk management tools

### Phase 2 (Planned)
- 🔄 Real-time news integration
- 🔄 Social media sentiment analysis
- 🔄 Advanced technical indicators
- 🔄 Backtesting with Indian data

### Phase 3 (Future)
- 📋 Options and derivatives support
- 📋 Mutual fund analysis
- 📋 IPO tracking and analysis
- 📋 Algorithmic trading integration

## Support and Resources

### Documentation
- [Indian Stock Market Basics](https://www.nseindia.com/)
- [SEBI Regulations](https://www.sebi.gov.in/)
- [Alpha Vantage API Docs](https://www.alphavantage.co/documentation/)

### Community
- GitHub Issues: Report bugs and feature requests
- Discussions: Ask questions and share insights
- Examples: Check `examples/` directory for more use cases

### Commercial Support
For enterprise features, custom integrations, or professional support, please contact the development team.

---

**Disclaimer**: This software is for educational and research purposes. Always consult with qualified financial advisors before making investment decisions. The developers are not responsible for any financial losses incurred from using this software. 