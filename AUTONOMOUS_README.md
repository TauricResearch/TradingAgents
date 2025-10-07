# 🤖 Autonomous Trading System

A 24/7 intelligent trading system that monitors your IBKR portfolio, analyzes multiple data sources, and provides actionable trading signals.

## 🚀 Features

### Real-Time Monitoring
- **IBKR Portfolio Sync** - Live connection to your Interactive Brokers account
- **Position Tracking** - Monitor P&L, cost basis, and performance
- **Risk Management** - Automatic alerts for position limits and losses

### Multi-Source Intelligence
- **Congressional Trades** - Track politician stock trades via QuiverQuant
- **Insider Trading** - Monitor SEC filings and insider activity
- **Market Sentiment** - News analysis and social media sentiment
- **Technical Analysis** - Support/resistance, RSI, moving averages
- **AI Analysis** - TradingAgents multi-agent evaluation

### Smart Alerts
- **Trading Signals** - Specific entry/exit prices with confidence scores
- **Risk Warnings** - Position concentration and loss alerts
- **Opportunity Detection** - Congressional trades matching your portfolio
- **Multi-Channel** - Discord, Telegram, Email notifications

## 📋 Prerequisites

1. **Interactive Brokers Account** with TWS or IB Gateway
2. **API Keys**:
   - OpenAI API key (required)
   - Alpha Vantage API key (required)
   - QuiverQuant API key (optional, for congressional trades)
   - Discord Webhook URL (optional, for alerts)

## 🛠️ Installation

### 1. Install Dependencies

```bash
# Install autonomous system requirements
pip install -r requirements_autonomous.txt

# Install base TradingAgents requirements
pip install -r requirements.txt
```

### 2. Configure IBKR

1. Open TWS or IB Gateway
2. Enable API connections:
   - File → Global Configuration → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Add "127.0.0.1" to trusted IPs
3. Note the port:
   - TWS Paper: 7497
   - TWS Live: 7496
   - IB Gateway Paper: 4002
   - IB Gateway Live: 4001

### 3. Set Environment Variables

Create or update `.env` file:

```bash
# === REQUIRED ===
OPENAI_API_KEY=your-openai-key
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key

# === IBKR Settings ===
IBKR_HOST=127.0.0.1
IBKR_PORT=7497  # Paper trading port
IBKR_CLIENT_ID=1

# === Optional Data Sources ===
QUIVER_API_KEY=your-quiver-key  # For congressional trades
POLYGON_API_KEY=your-polygon-key  # For real-time data
NEWS_API_KEY=your-news-api-key  # For news aggregation

# === Notifications (at least one recommended) ===
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# === Trading Settings ===
TRADING_ENABLED=false  # Set to true to enable trading
PAPER_TRADING=true    # Use paper account
MAX_POSITION_SIZE=0.20  # Max 20% per position
CONFIDENCE_THRESHOLD=70  # Min confidence for trades
```

## 🎯 Quick Start

### 1. Test Connection

```bash
# Test IBKR connection
python -c "from autonomous.ibkr_connector import IBKRConnector; import asyncio; asyncio.run(IBKRConnector().connect())"
```

### 2. Start Monitoring (Safe Mode)

```bash
# Start with monitoring only (no trading)
TRADING_ENABLED=false python autonomous_trader.py
```

### 3. Paper Trading

```bash
# Test with paper account
PAPER_TRADING=true TRADING_ENABLED=true python autonomous_trader.py
```

### 4. Live Trading (⚠️ Use with caution!)

```bash
# Live trading - BE VERY CAREFUL
PAPER_TRADING=false TRADING_ENABLED=true python autonomous_trader.py
```

## 📊 System Architecture

```
┌─────────────────────────────────────────────────┐
│              AUTONOMOUS TRADER                   │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │   IBKR   │  │   Data   │  │    AI    │     │
│  │ Connector│  │Aggregator│  │ Analysis │     │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘     │
│        └─────────────┼─────────────┘           │
│                      │                          │
│              ┌───────▼────────┐                │
│              │Signal Processor│                │
│              └───────┬────────┘                │
│                      │                          │
│         ┌────────────┼────────────┐            │
│         │            │            │            │
│    ┌────▼───┐  ┌────▼───┐  ┌────▼───┐       │
│    │ Alerts │  │  Risk  │  │ Orders │       │
│    │ Engine │  │ Manager│  │(Future)│       │
│    └────────┘  └────────┘  └────────┘       │
│                                                │
└─────────────────────────────────────────────────┘
```

## 📱 Alert Examples

### Trading Signal Alert
```
🎯 ACTION: BUY
📈 TICKER: NVDA
💰 ENTRY: $132.50 - $133.00
🎯 TARGET 1: $138.00 (+4.1%)
🛑 STOP LOSS: $129.00 (-2.6%)
📊 CONFIDENCE: 85%
📝 REASONING:
• Congressional buying detected
• Strong technical breakout
• Positive earnings momentum
```

### Risk Warning Alert
```
⚠️ Risk Alert: AVGO
AVGO is down 5.2%
Current: $912.45
P&L: -$2,145.00
Consider stop loss or hedging
```

## 🕐 Schedule

The system runs these tasks automatically:

| Task | Frequency | Description |
|------|-----------|-------------|
| Portfolio Sync | 5 min | Update positions and P&L |
| Market Scan | 15 min | Look for opportunities |
| Congressional Check | 1 hour | New politician trades |
| News Monitor | 30 min | Sentiment analysis |
| Risk Check | 30 min | Portfolio risk assessment |
| Daily Summary | 4:30 PM | End of day report |

## 🛡️ Safety Features

1. **Position Limits** - Max 20% in any single position
2. **Daily Loss Limit** - Stops at 5% daily loss
3. **Paper Trading Mode** - Test without real money
4. **Manual Confirmation** - Required for large trades
5. **Stop Loss** - Automatic stop loss recommendations
6. **Circuit Breakers** - Halts during extreme volatility

## 🔧 Customization

### Add Custom Indicators

Edit `autonomous/signal_processor.py`:

```python
async def calculate_custom_indicator(self, ticker: str):
    # Your custom logic here
    pass
```

### Modify Alert Channels

Edit `autonomous/alert_engine.py`:

```python
async def _send_custom_channel(self, title, message):
    # Your custom notification method
    pass
```

### Change Trading Rules

Edit `autonomous/config/settings.py`:

```python
MAX_POSITION_SIZE = 0.15  # 15% instead of 20%
CONFIDENCE_THRESHOLD = 80  # Require 80% confidence
```

## 📈 Performance Monitoring

View logs and metrics:

```bash
# View real-time logs
tail -f autonomous_trader.log

# Check alert history
python -c "from autonomous.alert_engine import AlertEngine; print(AlertEngine().alert_history)"
```

## 🐛 Troubleshooting

### IBKR Connection Issues
- Ensure TWS/Gateway is running
- Check API settings are enabled
- Verify port number matches config
- Check firewall isn't blocking connection

### No Alerts Received
- Verify at least one notification channel is configured
- Check webhook URLs are correct
- Test with console output first

### High API Usage
- Reduce `MARKET_SCAN_INTERVAL` in config
- Use fewer models or smaller LLMs
- Implement caching for repeated queries

## ⚠️ Disclaimer

**This system is for educational and research purposes only.**

- Trading involves substantial risk of loss
- Past performance doesn't guarantee future results
- Always do your own research
- Start with paper trading
- Never risk more than you can afford to lose

## 📚 Resources

- [IBKR API Documentation](https://interactivebrokers.github.io/)
- [QuiverQuant API](https://www.quiverquant.com/api)
- [TradingAgents Documentation](../README.md)
- [Discord Webhooks Guide](https://discord.com/developers/docs/resources/webhook)

## 🤝 Support

For issues or questions:
1. Check the logs: `autonomous_trader.log`
2. Review configuration in `.env`
3. Test components individually
4. Open an issue with error details

---

**Remember**: Start small, test thoroughly, and never trade with money you can't afford to lose! 🎯