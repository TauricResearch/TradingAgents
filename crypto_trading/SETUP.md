# Crypto Trading Module - Setup Instructions

## Installation

### 1. Prerequisites

Ensure you have Python 3.9+ installed:
```bash
python --version
```

### 2. Install Dependencies

Install required packages:
```bash
pip install ccxt pandas numpy python-dotenv langchain-openai
```

Or if you have a requirements file:
```bash
pip install -r ../requirements.txt
```

### 3. Configure API Keys

Create a `.env` file in the project root (`TradingAgents/`) with the following keys:

```bash
# OpenAI API (required for LLM agents)
OPENAI_API_KEY=your_openai_api_key_here

# Exchange API keys (optional, for paper/live trading)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key

# Data provider API keys (optional)
GLASSNODE_API_KEY=your_glassnode_api_key  # For on-chain data
MESSARI_API_KEY=your_messari_api_key      # For crypto fundamentals
```

### 4. Set Python Path

The crypto module needs access to the main TradingAgents framework. Choose one method:

#### Option A: Set PYTHONPATH (Recommended)

Add to your shell profile (`.bashrc`, `.zshrc`, etc.):
```bash
export PYTHONPATH="/Users/nguyenminhduc/Desktop/TradingAgents:$PYTHONPATH"
```

Then reload:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

#### Option B: Install in Development Mode

From the TradingAgents root directory:
```bash
pip install -e .
```

This requires a `setup.py` file in the root.

#### Option C: Use Scripts As-Is

All scripts already include path setup code:
```python
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
```

So you can run them directly without additional setup!

## Running Crypto Features

### Test Data Integration

```bash
cd crypto_trading
python tests/test_crypto_data.py
```

### Test Crypto Agents

```bash
python tests/test_crypto_agents.py
```

### Run Backtesting

```bash
python scripts/run_crypto_backtest.py
```

### Run Paper Trading

```bash
python scripts/run_paper_trading.py
```

### Run 24/7 Trading Bot

```bash
python scripts/run_crypto_bot_24_7.py
```

### Run Examples

```bash
# Basic crypto data examples
python examples/crypto_analysis_example.py

# Agent integration examples
python examples/crypto_agent_integration.py

# Backtesting strategy examples
python examples/crypto_backtest_examples.py
```

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'tradingagents'`:

1. Make sure you're running from the correct directory
2. Check that PYTHONPATH is set correctly:
   ```bash
   echo $PYTHONPATH
   ```
3. Verify the path resolves correctly:
   ```bash
   python -c "import sys; print(sys.path)"
   ```

### Missing Dependencies

If you get import errors for packages:
```bash
pip install ccxt pandas numpy python-dotenv langchain-openai langchain-core
```

### API Key Errors

- Ensure `.env` file is in the TradingAgents root directory
- Load it in your code:
  ```python
  from dotenv import load_dotenv
  load_dotenv()
  ```
- Check environment variables:
  ```bash
  echo $OPENAI_API_KEY
  ```

### Data Fetch Errors

Some data sources require API keys:
- **Glassnode**: On-chain metrics (paid service)
- **Messari**: Crypto fundamentals (free tier available)
- **CCXT**: Exchange data (free, no key needed for public data)

## Directory Structure

```
crypto_trading/
├── SETUP.md                # This file
├── README.md               # Main documentation
│
├── docs/                   # All documentation
│   ├── README_CRYPTO.md
│   ├── CRYPTO_QUICK_START.md
│   └── ...
│
├── src/                    # Source code
│   ├── agents/            # Crypto analyst agents
│   ├── backtesting/       # Backtesting framework
│   ├── paper_trading/     # Paper trading engine
│   └── crypto_config.py   # Configuration
│
├── tests/                  # Test files
├── examples/               # Usage examples
├── scripts/                # Executable scripts
└── data/                   # Data storage
```

## Integration with Main Framework

To use crypto features with the main TradingAgents framework:

```python
import sys
import os

# Add project root to path
project_root = "/Users/nguyenminhduc/Desktop/TradingAgents"
sys.path.insert(0, project_root)

# Import main framework
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.crypto_config import get_crypto_config

# Import crypto agents
from crypto_trading.src.agents.crypto_technical_analyst import create_crypto_technical_analyst
from crypto_trading.src.agents.crypto_fundamentals_analyst import create_crypto_fundamentals_analyst

# Set crypto config
from tradingagents.dataflows.config import set_config
crypto_config = get_crypto_config()
set_config(crypto_config)

# Use framework with crypto support
ta = TradingAgentsGraph(
    debug=True,
    config=crypto_config,
    selected_analysts=["crypto_technical", "crypto_fundamentals"]
)

# Run analysis
_, decision = ta.propagate("BTC/USDT", "2024-10-07")
```

## Next Steps

1. Review the documentation in `docs/README_CRYPTO.md`
2. Run the tests to verify installation
3. Explore the examples
4. Try running paper trading simulation
5. Customize strategies for your use case

## Support

For issues or questions:
- Check documentation in `docs/`
- Review example code in `examples/`
- Consult main TradingAgents README
