# Momentum Dashboard

Real-time momentum analysis dashboard for TradingAgents.

## Features

✅ **21 EMA Trend Filter** - Long above, short below
✅ **Bollinger Band Squeeze** - Identify low-volatility consolidation
✅ **Volume Momentum** - Confirm breakouts
✅ **RSI Indicator** - Overbought/oversold signals
✅ **Multi-timeframe** - 1H/Daily/Weekly analysis
✅ **Magnificent Seven** + Custom watchlists

## Quick Start

### 1. Install Dependencies
```bash
pip install streamlit plotly yfinance pandas numpy
```

### 2. Run Dashboard
```bash
cd tradingagents/dashboards/momentum
streamlit run app.py
```

### 3. CLI Scanner (No UI)
```bash
python -m tradingagents.dashboards.momentum
```

## Signals

| Signal | Meaning |
|--------|---------|
| STRONG_BUY | Bullish trend + high strength |
| BUY | Moderate bullish |
| WATCH_FOR_BREAKOUT | Squeeze detected, potential move |
| HOLD | No clear signal |
| SELL | Moderate bearish |
| STRONG_SELL | Bearish trend + low strength |

## Architecture

```
momentum/
├── __init__.py     # Core scanner & indicators
├── app.py          # Streamlit UI
└── README.md       # This file
```

## Integration

To integrate with TradingAgents main workflow:

```python
from tradingagents.dashboards.momentum import MomentumScanner

scanner = MomentumScanner(["AAPL", "NVDA", "TSLA"])
signals = scanner.scan_all()

# Use signals in trading decisions
for signal in signals:
    if signal["signal"] == "STRONG_BUY":
        # Execute buy logic
        pass
```

## Future Enhancements

- [ ] Real-time WebSocket data (Polygon.io)
- [ ] Alert notifications (email/Telegram)
- [ ] Portfolio tracking
- [ ] Backtesting mode
- [ ] Multi-exchange support

---

Built for TradingAgents by OpenClaw Community