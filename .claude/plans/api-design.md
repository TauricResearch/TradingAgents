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

---





## When to use
- Before implementing a repository interface in `domain/`
- Before defining application-layer command/query handlers
- Before exposing a new endpoint in `interfaces/`

## After finish
- Task Tracking
- You create task tracking in my notion. Get back to me if you do not access.