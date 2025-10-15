# Crypto Quick Start Guide

## Installation (2 minutes)

```bash
# 1. Install crypto dependencies
pip install ccxt glassnode python-dotenv

# 2. Test the installation
python test_crypto_data.py
```

## Basic Usage (Copy & Paste)

### Get Bitcoin Price

```python
from tradingagents.dataflows.ccxt_vendor import get_crypto_ohlcv

btc_price = get_crypto_ohlcv("BTC/USDT", timeframe="1d", limit=7)
print(btc_price)
```

### Get Crypto Fundamentals

```python
from tradingagents.dataflows.messari_vendor import get_crypto_fundamentals_messari

btc_fundamentals = get_crypto_fundamentals_messari("bitcoin")
print(btc_fundamentals)
```

### Switch to Crypto Mode

```python
from tradingagents.crypto_config import get_crypto_config
from tradingagents.dataflows.config import set_config

# Enable crypto mode
crypto_config = get_crypto_config()
set_config(crypto_config)

# Now all data calls use crypto vendors automatically
```

## Run Examples

```bash
# Run comprehensive examples
python examples/crypto_analysis_example.py

# Run tests
python test_crypto_data.py
```

## Supported Assets

### Via CCXT (100+ exchanges)
- BTC/USDT, ETH/USDT, SOL/USDT
- Any trading pair on Binance, Coinbase, Kraken

### Via Messari
- bitcoin, ethereum, solana, cardano, avalanche, polkadot
- 500+ crypto assets

### Via Glassnode (requires API key)
- BTC, ETH (on-chain metrics)

## API Keys (Optional)

Most features work **without API keys**. Add keys only for:
- **Trading** (CCXT authenticated endpoints)
- **On-chain analytics** (Glassnode)

```bash
# .env file
BINANCE_API_KEY=your_key
GLASSNODE_API_KEY=your_key
```

## What Works Without API Keys?

✅ CCXT - All public market data
✅ Messari - Basic fundamentals and news
❌ Glassnode - Requires paid subscription

## Common Issues

### Import Error
```bash
pip install ccxt glassnode python-dotenv --upgrade
```

### Exchange Connection Error
```python
# Test connectivity
import ccxt
exchange = ccxt.binance()
print(exchange.fetch_ticker('BTC/USDT'))
```

## Next Steps

1. ✅ Phase 1 Complete - Data infrastructure
2. 🔜 Phase 2 - Adapt agents for crypto
3. 🔜 Phase 3 - Backtesting framework
4. 🔜 Phase 4 - Paper trading
5. 🔜 Phase 5 - Live deployment

## Documentation

- Full details: `CRYPTO_PHASE1_README.md`
- Migration plan: `CRYPTO_MIGRATION_PLAN.md`
- Examples: `examples/crypto_analysis_example.py`
- Tests: `test_crypto_data.py`

## Support

- CCXT Docs: https://docs.ccxt.com/
- Glassnode API: https://docs.glassnode.com/
- Messari API: https://messari.io/api/docs
