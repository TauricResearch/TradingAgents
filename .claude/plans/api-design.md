# Design Plan

Use this to debate and finalize an internal or external API contract before writing a single line of implementation.

---

## Task

### Task 1: Setup toml
- As a tech-choice.md. I select panda-ta for calculation. You update toml, add depenncy needed.

### Task 2: Set up LLM provider
- Regrading tech-choice.md and archimate.puml. You create a provider class as a class factory. After and you implement the Anthropic API. You read key in .env, I will propose for you.

### Task 3: Insfrastructure layer
- Regrading tech-choice.md and archimate.puml. You must focus on binace api.
- You implement model and data structure to fetch data. Must focus on Params.
   - Arg
   - 
```
    kline-url: https://api.binance.com/api/v3/klines
    ticker: https://api.binance.com/api/v3/ticker/
    depth: https://api.binance.com/api/v3/depth
```

### Task 4: Remove all LLM provider exclude claudeAPI
- You review the project, remove all of providers exluced claude API.

### Task 5: Reviewing
You review all projects, by default, the project call SPY and report. But my input is BTCUSDT. How can I check that cli call binace insteanf of yfinance.
### Task 6: Remove all yfinance in source code
- You have to scan all code, remove all yfinance.
- In dataflow/ interface.py, remove all yfinance factory remove all. You must appyly Binance api for this.

### Task 7: Logs Enhancement
- The first step, you must print promting string before call CLAUDE API.
### Task 8: Questionary enhancement
- You have to append the query to ask user about kline that usert want into CLI. You need to check binance_models, The query must be included internal and start_time and end_time. By defaults, start_time and end_endtime must be 2 months. start_time and end_time have formatted: DD/MM/YYY

### Task 9: SMA enhancemence
- SMA is a indicators used in market_analysis. But sma 10, 50, 200 is not suitable for analysze. You must change to sma 34, sma 56, sma 89. Other indicators depended on sma must be change.

### Task 9.1: Fix bug
- Regrading logs
```text
21:38:04 [Tool Call] get_stock_data(symbol=BTCUSDT, start_date=2025-12-01, end_date=2026-04-05)
21:38:04 [Data] No kline data found for symbol 'BTCUSDT' between 2025-12-01 and 2026-04-05
21:38:08 [Tool Call] get_stock_data(symbol=BTCUSDT, start_date=2025-10-01, end_date=2026-04-05)
21:38:08 [Data] No kline data found for symbol 'BTCUSDT' between 2025-10-01 and 2026-04-05
21:38:10 [Tool Call] get_stock_data(symbol=BTCUSDT, start_date=2025-01-01, end_date=2025-12-31)
21:38:10 [Data] No kline data found for symbol 'BTCUSDT' between 2025-01-01 and 2025-12-31
21:38:12 [Tool Call] get_stock_data(symbol=BTCUSDT, start_date=2024-01-01, end_date=2024-12-31)
21:38:13 [Data] No kline data found for symbol 'BTCUSDT' between 2024-01-01 and 2024-12-31
```
I inputed 01/03/2026 formatted DD-M-YY, but the tools parse incorrectly. You must fix that.

### Task 10: Fibonacci retracement
Step 1: After you get stock in binance. You must calculate fibonaci  Fibonacci retracement at level: 0, 0.236, 0.382, 0.5. 0.618 and 1 as a new tools
Step 2: You must update system_message, describe the fibonacci retracement and update prompt context. Noted that. If symbol is BTCUSDT, you must check 0.5, if the price above 0.5 that means short uptrend. Allcoin check 0.618
---





## When to use
- Before implementing a repository interface in `domain/`
- Before defining application-layer command/query handlers
- Before exposing a new endpoint in `interfaces/`

## After finish
- Task Tracking
- You create task tracking in my notion. Get back to me if you do not access.