# Portfolio Analysis Feature

## Overview

The Portfolio Analysis feature extends TradingAgents to analyze entire portfolios of stocks, providing comprehensive insights on diversification, risk, correlation, and rebalancing recommendations.

## Features

### Core Capabilities
- **Multi-stock parallel analysis**: Analyze multiple stocks concurrently for faster results
- **Portfolio-level metrics**: Calculate correlation, beta, volatility, Sharpe ratio, and diversification scores
- **Risk assessment**: Identify concentration risks, sector exposure, and correlation risks
- **Rebalancing suggestions**: AI-powered recommendations for portfolio optimization
- **Comprehensive PDF reports**: Visual charts including allocation pie charts, correlation heatmaps, sector breakdown, and performance graphs

### Analysis Components

#### Individual Stock Analysis
Each position in your portfolio is analyzed using the full TradingAgents framework:
- Market Analyst
- Sentiment Analyst (optional)
- News Analyst (optional)
- Fundamentals Analyst (optional)
- Research Team debate
- Trading recommendations
- Risk management review

#### Portfolio-Level Analysis
- **Correlation Matrix**: Understand how your positions move together
- **Sector Diversification**: See your exposure across different sectors
- **Position Weights**: Identify over/under-weighted positions
- **Performance Metrics**: Beta, volatility, Sharpe ratio, max drawdown
- **Risk Concentration**: Warnings for concentrated positions or sectors

## Usage

### Command Line Interface

#### Option 1: Interactive CLI
```bash
python -m cli.main analyze-portfolio
```

The CLI will prompt you to enter:
1. Portfolio name
2. Analysis date
3. Your positions (ticker, shares, average cost)
4. Analyst selection
5. Research depth
6. LLM settings

#### Option 2: Programmatic Usage
```python
from tradingagents.portfolio.models import Portfolio, Position
from tradingagents.portfolio.portfolio_graph import PortfolioAnalysisGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Define your positions
positions = {
    "AAPL": Position(ticker="AAPL", shares=100, avg_cost=150.00),
    "MSFT": Position(ticker="MSFT", shares=50, avg_cost=300.00),
    "NVDA": Position(ticker="NVDA", shares=75, avg_cost=450.00),
}

# Create portfolio
portfolio = Portfolio(
    positions=positions,
    analysis_date="2024-12-01",
    name="My Portfolio"
)

# Configure analysis
config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 1
config["quick_think_llm"] = "gpt-4o-mini"
config["deep_think_llm"] = "gpt-4o-mini"

# Initialize and run analysis
portfolio_graph = PortfolioAnalysisGraph(
    selected_analysts=["market", "fundamentals"],
    debug=True,
    config=config
)

result = portfolio_graph.analyze_portfolio(portfolio)

# Access results
print(result.portfolio_recommendation)
print(result.risk_assessment)
print(result.rebalancing_suggestions)
```

### Test the Feature

Run the included test script:
```bash
python test_portfolio_analysis.py
```

## Output

### Console Output
- Real-time progress updates for each stock analysis
- Portfolio summary (value, P/L, allocations)
- Portfolio metrics (beta, volatility, Sharpe ratio)
- Risk assessment
- Rebalancing suggestions

### Saved Files

Results are saved in `results/portfolio/{analysis_date}/`:
- `portfolio_analysis.json`: Complete analysis results in JSON format
- `portfolio_analysis_{date}.pdf`: Comprehensive PDF report with charts

### PDF Report Sections

1. **Cover Page**: Portfolio summary, total value, P/L
2. **Portfolio Visualizations**:
   - Allocation pie chart
   - Position performance bar chart
   - Sector allocation bar chart
   - Correlation heatmap
3. **Portfolio Overview**: Summary and recommendations
4. **Risk Assessment**: Detailed risk analysis
5. **Rebalancing Suggestions**: Specific recommendations
6. **Individual Stock Analyses**: Detailed breakdown for each position

## Configuration

### Performance Optimization

Adjust `max_workers` for parallel processing:
```python
result = portfolio_graph.analyze_portfolio(portfolio, max_workers=3)
```
- Higher values = faster but more API calls
- Recommended: 2-4 workers

### Cost Optimization

Use cheaper LLMs for testing:
```python
config["quick_think_llm"] = "gpt-4o-mini"
config["deep_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 1
```

Select fewer analysts:
```python
selected_analysts=["market", "fundamentals"]  # Instead of all 4
```

## Requirements

### Python Packages
```bash
pip install reportlab matplotlib seaborn
```

All requirements are in `requirements.txt`.

### API Keys
- OpenAI API key (or Anthropic/Google)
- Alpha Vantage API key (for fundamental/news data)

## Metrics Explained

### Portfolio Beta
- Measures portfolio volatility relative to the market (SPY)
- Beta > 1: More volatile than market
- Beta < 1: Less volatile than market

### Sharpe Ratio
- Risk-adjusted return metric
- Higher is better (>1 is good)
- Negative means returns below risk-free rate

### Diversification Score
- 0 to 1 scale (1 = best diversification)
- Based on correlation between positions
- <0.5 = high correlation, poor diversification

### Max Drawdown
- Largest peak-to-trough decline
- Measures downside risk
- Lower is better

## Backward Compatibility

The portfolio analysis feature is **completely separate** from single-stock analysis:
- Single stock: `python -m cli.main analyze`
- Portfolio: `python -m cli.main analyze-portfolio`

All existing functionality remains unchanged.

## Limitations

- Requires historical price data (uses yfinance)
- Analysis date cannot be in the future
- Parallel analysis increases API costs
- Correlation analysis requires at least 60 days of overlapping price data
- Sector data may not be available for all tickers

## Examples

### Example Portfolio Input
```
Portfolio name: Tech Holdings
Analysis date: 2024-12-01

Position #1
  Ticker: AAPL
  Shares: 100
  Average cost: $150.00

Position #2
  Ticker: MSFT
  Shares: 50
  Average cost: $300.00

Position #3
  Ticker: GOOGL
  Shares: 25
  Average cost: $120.00
```

### Example Output
```
Portfolio Summary:
  Total Cost Basis: $36,000.00
  Total Market Value: $42,500.00
  Unrealized P/L: $6,500.00 (+18.06%)

Portfolio Metrics:
  Beta: 1.15
  Volatility: 22.3% (annualized)
  Sharpe Ratio: 1.42
  Diversification Score: 0.68/1.00

Sector Allocation:
  - Technology: 85.0%
  - Communication: 15.0%

⚠️ High concentration in Technology sector (85.0%) - consider diversifying
```

## Support

For issues or questions:
1. Check the main README.md
2. Review PORTFOLIO_ANALYSIS.md (this file)
3. Run test_portfolio_analysis.py to verify setup
4. Open an issue on GitHub

## Future Enhancements

Potential future features:
- Portfolio optimization suggestions
- Historical portfolio performance tracking
- Tax-loss harvesting recommendations
- Monte Carlo simulation for risk projections
- Factor analysis (value, growth, momentum)
- ESG scoring
