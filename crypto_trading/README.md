# Crypto Trading Module

This directory contains all cryptocurrency trading-related functionality for the TradingAgents framework.

## Directory Structure

```
crypto_trading/
├── docs/               # All crypto-related documentation
│   ├── README_CRYPTO.md                      # Main crypto documentation
│   ├── CRYPTO_QUICK_START.md                 # Quick start guide
│   ├── INSTALL_CRYPTO.md                     # Installation instructions
│   ├── CRYPTO_MIGRATION_PLAN.md              # Migration documentation
│   ├── CRYPTO_IMPLEMENTATION_SUMMARY.md      # Implementation summary
│   ├── CRYPTO_PHASE1_README.md               # Phase 1: Data layer
│   ├── CRYPTO_PHASE2_README.md               # Phase 2: Agent integration
│   ├── CRYPTO_PHASE2_SUMMARY.md              # Phase 2 summary
│   ├── CRYPTO_PHASE3_README.md               # Phase 3: Backtesting
│   ├── CRYPTO_PHASE3_SUMMARY.md              # Phase 3 summary
│   ├── PHASE4_PAPER_TRADING_COMPLETE.md      # Phase 4: Paper trading
│   └── PHASE4_SUMMARY.md                     # Phase 4 summary
│
├── src/                # Source code
│   ├── agents/         # Crypto-specific analyst agents
│   │   ├── crypto_fundamentals_analyst.py
│   │   ├── crypto_technical_analyst.py
│   │   ├── crypto_news_analyst.py
│   │   ├── crypto_sentiment_analyst.py
│   │   └── crypto_tools.py
│   ├── backtesting/    # Backtesting engine and utilities
│   │   ├── crypto_data_loader.py
│   │   ├── crypto_strategy_evaluator.py
│   │   └── crypto_backtest_engine.py
│   ├── paper_trading/  # Paper trading engine
│   │   └── paper_trading_engine.py
│   └── crypto_config.py  # Crypto-specific configuration
│
├── tests/              # Test files
│   ├── test_crypto_data.py
│   ├── test_crypto_agents.py
│   ├── test_crypto_backtest.py
│   └── test_paper_trading.py
│
├── examples/           # Example usage scripts
│   ├── crypto_analysis_example.py
│   ├── crypto_agent_integration.py
│   └── crypto_backtest_examples.py
│
├── scripts/            # Executable scripts
│   ├── run_crypto_backtest.py
│   ├── run_crypto_bot_24_7.py
│   ├── run_paper_trading.py
│   ├── demo_paper_trading_dashboard.py
│   └── quick_dashboard_test.py
│
└── data/               # Data storage
    ├── paper_trading_data/
    └── test_paper_trading_data/
```

## Quick Start

### 1. Install Dependencies

```bash
pip install ccxt pandas numpy python-dotenv
```

### 2. Configure API Keys

Add to your `.env` file:
```bash
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key
```

### 3. Run Examples

```bash
# Test crypto data fetching
python tests/test_crypto_data.py

# Test crypto agents
python tests/test_crypto_agents.py

# Run backtesting
python scripts/run_crypto_backtest.py

# Run paper trading
python scripts/run_paper_trading.py
```

## Documentation

For detailed documentation, see:
- **Getting Started**: `docs/CRYPTO_QUICK_START.md`
- **Installation**: `docs/INSTALL_CRYPTO.md`
- **Main Documentation**: `docs/README_CRYPTO.md`

## Features

### Phase 1: Data Layer ✅
- Real-time cryptocurrency data via CCXT
- Support for 100+ exchanges
- OHLCV data, order books, trades
- Error handling and rate limiting

### Phase 2: Crypto-Specific Agents ✅
- Technical Analysis Agent (RSI, MACD, Bollinger Bands)
- Fundamental Analysis Agent (on-chain metrics, tokenomics)
- News Analysis Agent (crypto-specific news sources)
- Sentiment Analysis Agent (social media, Fear & Greed Index)

### Phase 3: Backtesting Framework ✅
- Historical data loading and preprocessing
- Strategy evaluation with performance metrics
- Risk-adjusted returns analysis
- Visualization and reporting

### Phase 4: Paper Trading ✅
- Real-time paper trading simulation
- Portfolio management and tracking
- Performance monitoring dashboard
- Trade execution logging

## Integration with Main Framework

The crypto module integrates seamlessly with the main TradingAgents framework:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from crypto_trading.src.crypto_config import CRYPTO_CONFIG

# Initialize with crypto support
ta = TradingAgentsGraph(
    debug=True,
    config=CRYPTO_CONFIG,
    selected_analysts=["crypto_technical", "crypto_fundamentals", "crypto_news"]
)

# Run analysis
_, decision = ta.propagate("BTC/USDT", "2024-10-07")
```

## Testing

Run all crypto tests:
```bash
cd crypto_trading
python tests/test_crypto_data.py
python tests/test_crypto_agents.py
python tests/test_crypto_backtest.py
python tests/test_paper_trading.py
```

## Contributing

When adding new crypto functionality:
1. Add source code to `src/`
2. Add tests to `tests/`
3. Add examples to `examples/`
4. Update relevant documentation in `docs/`

## License

Same as main TradingAgents project.
