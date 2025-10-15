# Crypto Features Installation Guide

## Quick Install (2 minutes)

```bash
# Navigate to project directory
cd /Users/nguyenminhduc/Desktop/TradingAgents

# Install crypto dependencies
pip install ccxt glassnode python-dotenv

# Verify installation
python -c "import ccxt; print('CCXT version:', ccxt.__version__)"

# Run test suite
python test_crypto_data.py
```

## Expected Output

```
================================================================================
  CRYPTO DATA INFRASTRUCTURE TEST SUITE - PHASE 1
================================================================================

✅ CCXT: PASSED
✅ MESSARI: PASSED
⚠️  GLASSNODE: SKIPPED (API key required)

Results: 2/2 tests passed

🎉 All crypto data tests passed! Phase 1 implementation complete.
```

## Detailed Installation

### Step 1: Check Python Version

```bash
python --version
# Should be Python 3.9 or higher
```

### Step 2: Install Dependencies

```bash
pip install ccxt
pip install glassnode
pip install python-dotenv
```

Or install all at once:
```bash
pip install ccxt glassnode python-dotenv
```

### Step 3: Verify Installation

```bash
# Test CCXT
python -c "import ccxt; exchange = ccxt.binance(); print(exchange.fetch_ticker('BTC/USDT'))"

# Test imports
python -c "from tradingagents.dataflows.ccxt_vendor import get_crypto_ohlcv; print('✅ Imports OK')"
```

### Step 4: Set Up API Keys (Optional)

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your API keys (only if you need them)
# For basic usage, you DON'T need any API keys!
```

## What Works Without API Keys?

✅ **CCXT** - All public market data
- Price data (OHLCV)
- Tickers
- Order books
- Recent trades
- All exchanges

✅ **Messari** - Basic data
- Asset profiles
- Tokenomics
- News
- Market metrics

❌ **Glassnode** - Requires paid API key
- On-chain metrics
- Whale activity
- Exchange flows

## Testing Your Installation

### Test 1: Basic Connectivity

```bash
python test_crypto_data.py
```

### Test 2: Run Examples

```bash
python examples/crypto_analysis_example.py
```

### Test 3: Quick Python Test

```python
# test_quick.py
from tradingagents.dataflows.ccxt_vendor import get_crypto_ticker

# Get Bitcoin price
ticker = get_crypto_ticker("BTC/USDT", "binance")
print(ticker)
```

Run it:
```bash
python test_quick.py
```

## Troubleshooting

### Error: ModuleNotFoundError: No module named 'ccxt'

**Solution**:
```bash
pip install ccxt --upgrade
```

### Error: SSL Certificate Verify Failed

**Solution** (macOS):
```bash
/Applications/Python\ 3.x/Install\ Certificates.command
```

Or:
```bash
pip install certifi
```

### Error: Exchange Connection Timeout

**Solutions**:
1. Check internet connection
2. Try different exchange:
   ```python
   get_crypto_ticker("BTC/USDT", "coinbase")
   ```
3. Check if exchange is down: https://status.binance.com/

### Error: Rate Limit Exceeded

**Solution**: CCXT automatically handles rate limits. If you see this, wait a few seconds and retry.

### Import Error: tradingagents not found

**Solution**: Run from project root:
```bash
cd /Users/nguyenminhduc/Desktop/TradingAgents
python test_crypto_data.py
```

## Advanced Setup

### Using Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Installing from requirements.txt

```bash
pip install -r requirements.txt
```

This will install all dependencies including:
- ccxt (crypto exchange integration)
- glassnode (on-chain analytics)
- python-dotenv (environment variables)
- All existing TradingAgents dependencies

## API Key Setup (Optional)

### Get API Keys

**CCXT (for trading - not needed for data)**:
- Binance: https://www.binance.com/en/my/settings/api-management
- Coinbase: https://www.coinbase.com/settings/api
- Kraken: https://www.kraken.com/u/security/api

**Glassnode (for on-chain data)**:
- Sign up: https://studio.glassnode.com/
- Plans start at $30/month

**Messari (optional - free tier available)**:
- Sign up: https://messari.io/api
- Free tier: 20 requests/minute

### Configure .env File

```bash
# .env
BINANCE_API_KEY=your_actual_api_key_here
BINANCE_API_SECRET=your_actual_secret_here

GLASSNODE_API_KEY=your_glassnode_key_here
MESSARI_API_KEY=your_messari_key_here
```

**⚠️ Important**: Never commit .env file to git!

## Verifying Everything Works

### Complete Verification Script

```python
# verify_install.py
import sys

def verify():
    print("Checking crypto installation...\n")

    # Test 1: CCXT
    try:
        import ccxt
        print("✅ CCXT installed:", ccxt.__version__)
    except ImportError:
        print("❌ CCXT not installed")
        return False

    # Test 2: Connectivity
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"✅ Exchange connectivity OK (BTC price: ${ticker['last']:,.2f})")
    except Exception as e:
        print(f"❌ Exchange connectivity failed: {e}")
        return False

    # Test 3: Imports
    try:
        from tradingagents.dataflows.ccxt_vendor import get_crypto_ohlcv
        from tradingagents.dataflows.messari_vendor import get_crypto_fundamentals_messari
        print("✅ TradingAgents crypto modules OK")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

    print("\n🎉 Installation verified! Ready to use crypto features.")
    return True

if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
```

Run it:
```bash
python verify_install.py
```

## Next Steps After Installation

1. ✅ Run test suite: `python test_crypto_data.py`
2. ✅ Try examples: `python examples/crypto_analysis_example.py`
3. ✅ Read docs: `CRYPTO_QUICK_START.md`
4. ✅ Start building: Use crypto features in your agents

## Common Use Cases

### Use Case 1: Fetch BTC Price

```python
from tradingagents.dataflows.ccxt_vendor import get_crypto_ohlcv

btc_data = get_crypto_ohlcv("BTC/USDT", timeframe="1d", limit=30)
print(btc_data)
```

### Use Case 2: Analyze Fundamentals

```python
from tradingagents.dataflows.messari_vendor import get_crypto_fundamentals_messari

fundamentals = get_crypto_fundamentals_messari("bitcoin")
print(fundamentals)
```

### Use Case 3: Enable Crypto Mode

```python
from tradingagents.crypto_config import get_crypto_config
from tradingagents.dataflows.config import set_config

# Switch to crypto configuration
set_config(get_crypto_config())
```

## Getting Help

### Documentation
- Quick Start: `CRYPTO_QUICK_START.md`
- Full Docs: `CRYPTO_PHASE1_README.md`
- Implementation: `CRYPTO_IMPLEMENTATION_SUMMARY.md`

### External Resources
- CCXT Docs: https://docs.ccxt.com/
- Messari API: https://messari.io/api/docs
- Glassnode API: https://docs.glassnode.com/

### Issues
- Check test output: `python test_crypto_data.py`
- Verify imports: `python -c "import ccxt; print('OK')"`
- Check internet connectivity
- Review error messages carefully

## Uninstallation

If you want to remove crypto features:

```bash
# Uninstall packages
pip uninstall ccxt glassnode python-dotenv

# Remove files (optional)
rm -rf tradingagents/dataflows/ccxt_vendor.py
rm -rf tradingagents/dataflows/glassnode_vendor.py
rm -rf tradingagents/dataflows/messari_vendor.py
rm -rf tradingagents/crypto_config.py
```

**Note**: Existing stock functionality will continue to work.

---

**Installation complete! You're ready to use crypto features.** 🚀
