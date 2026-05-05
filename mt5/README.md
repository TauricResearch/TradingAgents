# MT5 (Exness) Bridge

This repo does not place MT5 orders by default. The stable approach is:

1) Python generates a JSON signal file
2) An MT5 Expert Advisor reads the file and executes pending orders with SL/TP

## 1) Install the EA

1. Open MetaTrader 5
2. File → Open Data Folder
3. Copy [TradingAgentsEA.mq5](file:///c:/Users/AD/Desktop/A_T/TradingAgents/mt5/TradingAgentsEA.mq5) into:
   - `MQL5/Experts/`
4. In MetaEditor, compile it
5. Attach EA to an `XAUUSD` chart

EA inputs you will likely adjust:
- `SignalFileName`: `tradingagents_signal.json`
- `UseCommonFiles`: `true`
- `MagicNumber`: any unique value
- `MaxDailyLossUsd`: `40.0`
- `MaxPositions`: `2`

## 2) Where the JSON file should be written

If `UseCommonFiles=true`, the EA reads from the MT5 Common Files folder:

- `%APPDATA%\\MetaQuotes\\Terminal\\Common\\Files\\tradingagents_signal.json`

## 3) Generate a quick offline signal (no LLM, levels-only)

From the repo root:

```powershell
cd C:\Users\AD\Desktop\A_T\TradingAgents
.\.venv\Scripts\python scripts\export_mt5_signal_levels_only.py --date 2026-05-05 --symbol-data XAUUSD=X --symbol-mt5 XAUUSD --risk-usd 10 --max-positions 2
```

The command prints the exact path it wrote.

## 4) Notes

- The levels-only exporter uses yfinance-like vendor data via the existing router. For a true MT5-aligned feed, add an MT5 OHLCV vendor later.
- The EA enforces `SYMBOL_TRADE_STOPS_LEVEL` and will skip orders that violate minimum distances.
