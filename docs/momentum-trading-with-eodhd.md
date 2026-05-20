---
title: "How I Built a Momentum Trading App with Claude Code and EODHD"
author: "Kevin Meneses González"
site: "CodeX"
published: 2026-05-01T11:46:00Z
source: "https://medium.com/codex/how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57"
domain: "medium.com"
language: "en"
description: "Most developers lose the first three days of a project before writing a single line of business logic."
word_count: 1862
---

![](https://miro.medium.com/v2/resize:fit:1400/format:webp/0*JCspJZjqb1aXyDCa)

Photo by Austin Hervias on Unsplash

Most developers lose the first three days of a project before writing a single line of business logic.

They’re fighting environment setup. Hunting documentation. Debugging import errors at midnight.

If you’re:

- building algorithmic trading tools,
- automating market analysis workflows,
- or prototyping fintech products with real financial data,

This matters.

Because the bottleneck isn’t your strategy. It’s everything around it.

## The Real Problem Isn’t the Algorithm

Every developer I know who’s tried to build a trading system has hit the same wall.

Not a math wall. A tooling wall.

You open a blank file. You know what you want to build — a momentum screener, a signal engine, a simple backtester. But before the strategy, you need to:

- Find a reliable financial data API (and actually understand its endpoints)
- Scaffold the project structure
- Handle authentication, rate limits, and error responses
- Write boilerplate that has nothing to do with trading logic

By the time you’re ready to write the interesting part, you’re already drained.

The real problem isn’t complexity. It’s context switching.

## Claude Code Changes the Setup Equation

Claude Code is Anthropic’s agentic coding tool. It runs in your terminal, reads your project, and executes real tasks — not just suggestions.

It doesn’t autocomplete. It builds.

You describe what you want. Claude Code reads your files, runs commands, installs dependencies, and iterates based on actual output. It operates inside your codebase like a senior developer who never needs to ask where things are.

For trading projects specifically, this changes the dynamic entirely.

Instead of spending two hours on boilerplate, you spend twenty minutes describing your goal and reviewing the result.

> If you’re curious about the data layer powering the examples below, EODHD APIs offer one of the most complete financial datasets available for developers — EOD prices, fundamentals, and real-time feeds across 70+ exchanges. [Start with a free API key here.](https://eodhd.com/?via=kmg&ref1=Meneses&utm_source=medium&utm_medium=post&utm_campaign=how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57&utm_content=Meneses)

## Claude Code: Commands, Tips, and Workflow Patterns

Before touching any trading logic, it’s worth understanding how to use Claude Code effectively. There’s a gap between “it works” and “it works fast.”

## Installation

```c
npm install -g @anthropic-ai/claude-code
claude
```

Claude Code requires Node.js 18+. Once installed, you launch it from the root of your project directory. It reads the local filesystem from that point forward.

## Key Commands to Know

Once you’re inside a Claude Code session, these slash commands do the heavy lifting:

Command: What it does

`- /init` Generates a `CLAUDE.md` file — your project memory

`/compact` Summarizes conversation history to save context window

`/clear` Resets the session (useful when switching tasks)

`/cost` Shows token usage for the current session `Shift+Tab` Toggles auto-accept mode — Claude executes without asking

## The CLAUDE.md File — Your Most Underrated Tool

Run `/init` at the start of every project. Claude Code generates a `CLAUDE.md` file that captures your project structure, conventions, and dependencies.

Every subsequent session, Claude reads this file first.

That means you don’t re-explain your codebase every time you open a new session. It knows where your modules live, what your naming conventions are, and what tools you’re using.

For a trading project, add explicit notes:

```c
## Project Context
- Uses EODHD API for all market data (EOD + intraday)
- Momentum strategy: 20-day vs 50-day SMA crossover + ROC filter
- Output: CSV signals + terminal summary
- Python 3.11, no external trading frameworks
```

This is the difference between a 10-minute session and a 40-minute session.

## How to Prompt Claude Code for Technical Tasks

Claude Code responds better to task-oriented prompts than to questions.

**Less effective:**

> “How do I fetch stock data from EODHD?”

**More effective:**

> “Create a `data_fetcher.py` module that pulls 6 months of EOD data from EODHD for a given ticker. Use `requests`, handle HTTP errors, and return a pandas DataFrame sorted by date ascending."

Specificity reduces back-and-forth. Include: the module name, the library preference, the return type, and the error handling expectation.

## Token Optimization Patterns

Claude Code sessions have a context window. If you’re building something complex, manage it deliberately:

- Use `/compact` before switching to a new feature — it keeps the memory without the noise
- Break large tasks into stages: scaffold first, implement second, test third
- If a session is drifting (Claude starts repeating itself or losing track), `/clear` and restart with a focused prompt

One more thing: Claude Code has a **headless mode** for automation.

```c
claude -p "Run all tests in /tests and report which ones fail" --output-format json
```

Useful when you want to integrate it into a CI pipeline or a shell script that audits your project overnight.

## EODHD: The Data Layer for Serious Projects

Financial data is the foundation of every trading system. And not all data providers are equal.

[EODHD](https://eodhd.com/?via=kmg&ref1=Meneses&utm_source=medium&utm_medium=post&utm_campaign=how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57&utm_content=Meneses) (End-Of-Day Historical Data) covers 70+ exchanges, with endpoints for EOD prices, fundamentals, intraday data, macroeconomic indicators, and more. It’s built for developers — clean REST API, consistent JSON responses, and solid documentation.

For a momentum strategy, you’ll primarily use two endpoints:

**1\. EOD Historical Data**

```c
GET https://eodhd.com/api/eod/{TICKER}.{EXCHANGE}?api_token=YOUR_KEY&fmt=json&from=2024-01-01
```

Returns daily OHLCV data. Clean, pageable, reliable.

**2\. Real-Time / Intraday Data**

```c
GET https://eodhd.com/api/intraday/{TICKER}.{EXCHANGE}?interval=1h&api_token=YOUR_KEY
```

For signal validation during market hours.

**Why EODHD specifically for trading projects:**

- **Coverage**: 150,000+ tickers across equities, ETFs, indices, forex, and crypto
- **Historical depth**: up to 30 years of daily data for most US equities
- **Fundamentals**: P/E, EPS, revenue — available in the same API ecosystem
- **Rate limits**: generous on paid plans; free tier covers basic EOD access for testing
- **Consistency**: JSON structure doesn’t change between tickers — you write the parser once

That last point matters more than it sounds. Inconsistent API responses are one of the most common sources of bugs in trading systems.

## Building the Momentum App: Step by Step

A momentum strategy is one of the most empirically robust in quantitative finance. The premise: assets that have outperformed recently tend to continue outperforming over the next 1–12 months.

Our implementation uses:

- **20-day vs 50-day SMA crossover** as the trend filter
- **Rate of Change (ROC-10)** as the momentum signal
- EODHD for all price data

## Step 1: Project Setup with Claude Code

Open your terminal in a new project directory and launch Claude Code:

```c
mkdir momentum-trader && cd momentum-trader
claude
```

Prompt:

```c
Scaffold a Python project for a momentum trading screener. 
Create: main.py, data_fetcher.py, signals.py, config.py.
Add a requirements.txt with: requests, pandas, numpy, python-dotenv.
Add a .env.example with EODHD_API_KEY placeholder.
```

Claude Code will create all files, write placeholder structure, and set up the `.env` pattern. What would take 15 minutes manually happens in under two.

## Step 2: Fetching Price Data from EODHD

In `data_fetcher.py`:

```c
import os
import requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("EODHD_API_KEY")
BASE_URL = "https://eodhd.com/api/eod"
def get_eod_data(ticker: str, exchange: str = "US", period: str = "d", months: int = 6) -> pd.DataFrame:
    from datetime import datetime, timedelta
    start = (datetime.today() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    
    url = f"{BASE_URL}/{ticker}.{exchange}"
    params = {
        "api_token": API_KEY,
        "fmt": "json",
        "from": start,
        "period": period
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    df = pd.DataFrame(response.json())
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "open", "high", "low", "close", "volume"]]
```

Clean. No external trading libraries. Just `requests` and `pandas`.

## Step 3: Calculating Momentum Signals

In `signals.py`:

```c
import pandas as pd
import numpy as np
def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    # Trend filter: SMA crossover
    df["sma_20"] = df["close"].rolling(window=20).mean()
    df["sma_50"] = df["close"].rolling(window=50).mean()
    df["trend_up"] = df["sma_20"] > df["sma_50"]
    
    # Momentum signal: Rate of Change (10 days)
    df["roc_10"] = df["close"].pct_change(periods=10) * 100
    
    # Combined signal
    df["signal"] = np.where(
        (df["trend_up"]) & (df["roc_10"] > 5),
        "BUY",
        np.where(
            (~df["trend_up"]) & (df["roc_10"] < -5),
            "SELL",
            "HOLD"
        )
    )
    
    return df
```

ROC \> 5% + uptrend = BUY. ROC < -5% + downtrend = SELL. Everything else = HOLD.

Simple. Auditable. A solid base to extend.

## Step 4: Running the Screener

In `main.py`:

```c
from data_fetcher import get_eod_data
from signals import add_signals
WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "META"]
def run_screener():
    results = []
    
    for ticker in WATCHLIST:
        df = get_eod_data(ticker)
        df = add_signals(df)
        latest = df.iloc[-1]
        
        results.append({
            "Ticker": ticker,
            "Close": round(latest["close"], 2),
            "ROC_10": round(latest["roc_10"], 2),
            "SMA_20": round(latest["sma_20"], 2),
            "SMA_50": round(latest["sma_50"], 2),
            "Signal": latest["signal"]
        })
        print(f"{ticker}: {latest['signal']} | ROC={latest['roc_10']:.1f}% | Close={latest['close']:.2f}")
    
    import pandas as pd
    pd.DataFrame(results).to_csv("signals_output.csv", index=False)
    print("\nSignals saved to signals_output.csv")
if __name__ == "__main__":
    run_screener()
```

Run it:

```c
python main.py
```

Sample output:

```c
AAPL: BUY | ROC=7.3% | Close=213.45
MSFT: HOLD | ROC=2.1% | Close=418.20
NVDA: BUY | ROC=12.8% | Close=875.60
TSLA: SELL | ROC=-6.4% | Close=172.30
META: BUY | ROC=9.1% | Close=521.80
```

From here you can extend this into:

- a daily cron job that emails you the signals each morning
- a backtester that runs this logic over 5 years of EODHD data
- a Telegram bot that notifies you on BUY/SELL transitions
- a web dashboard that visualizes signal history per ticker

Claude Code can scaffold any of those in a single session. That’s the actual leverage.

## FAQs

❓ **Is Claude Code free to use?**  
✅ Claude Code is billed through your Anthropic API usage — there’s no fixed subscription. You pay per token consumed during sessions. For a typical development session (1–2 hours of active work), costs are generally under $5. Heavy sessions with large codebases can go higher. Use `/cost` during sessions to monitor spend.

❓ **Does EODHD offer a free tier for testing?**  
✅ Yes. EODHD provides a free API key that gives access to EOD historical data for a limited set of tickers. It’s enough to run the momentum screener in this article and evaluate the API structure before committing to a paid plan. [Register here.](https://eodhd.com/?via=kmg&ref1=Meneses&utm_source=medium&utm_medium=post&utm_campaign=how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57&utm_content=Meneses)

❓ **Can I use this momentum strategy in production?**  
✅ The code in this article is a working prototype, not a production system. For real deployment, you’d add position sizing, slippage estimates, portfolio-level risk controls, and a proper backtesting framework (Backtrader or VectorBT work well with EODHD data). Treat this as a tested starting point, not a finished product.

❓ **What exchanges does EODHD cover beyond US equities?**  
✅ [**EODHD**](https://eodhd.com/?via=kmg&ref1=Meneses&utm_source=medium&utm_medium=post&utm_campaign=how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57&utm_content=Meneses) covers 70+ exchanges globally — including LSE, TSX, Euronext, ASX, NSE, Bovespa, and crypto markets. The same API structure applies across all of them, which means the code in this article works for European or Asian stocks by simply changing the `exchange` parameter (e.g., `"LSE"`, `"XETRA"`, `"TSX"`).

❓ **How does Claude Code handle large codebases?**  
✅ Claude Code reads your project directory recursively and uses the `CLAUDE.md` file as a persistent context anchor. For large projects, it's best practice to use `/compact` frequently, break tasks into isolated sessions, and keep your `CLAUDE.md` updated with current project state. It handles codebases of 50k+ lines reliably — the limiting factor is session context, not file size.

## The Shift Has Already Happened

A year ago, “build a trading screener” meant a weekend project.

Today, with Claude Code and a solid [data API](https://eodhd.com/?via=kmg&ref1=Meneses&utm_source=medium&utm_medium=post&utm_campaign=how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57&utm_content=Meneses), it’s an afternoon.

The tools have changed. The bottleneck has moved from implementation to decision-making — what strategy to test, what data to trust, what signals to act on.

That’s the right problem to have.

*If you’re a software or API company looking to explain your product through high-quality educational content (not marketing fluff), feel free to connect with me on LinkedIn: 👉* [*linkedin.com/in/kevin-meneses-gonzalez*](https://www.linkedin.com/in/kevin-meneses-gonzalez/)

Try [**EODHD**](https://eodhd.com/?via=kmg&ref1=Meneses&utm_source=medium&utm_medium=post&utm_campaign=how-i-built-a-momentum-trading-app-with-claude-code-and-eodhd-a20a7556fc57&utm_content=Meneses) now