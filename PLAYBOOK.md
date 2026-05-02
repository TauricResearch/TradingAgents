# TradingAgents Playbook

> **Purpose:** Practical guide for running TradingAnalyses effectively. Not theory — what to do, what settings to pick, and what to watch for.

---

## 1. Architecture in One Picture

```
┌──────────────────────────────────────────────────────────────────┐
│                        ONE TRADING DECISION                       │
│                                                                  │
│  ┌─────────────┐   ┌──────────────────┐   ┌───────────────────┐ │
│  │ Analyst Team │──▶│ Research Team    │──▶│    Trader         │ │
│  │ (pick 1-4)   │   │ Bull vs Bear     │   │ (composes plan)   │ │
│  └─────────────┘   │ + Judge/Mgr      │   └────────┬──────────┘ │
│                    └──────────────────┘            │            │
│                                                   ▼            │
│  ┌────────────────────┐   ┌──────────────────────────────┐     │
│  │ Risk Management    │──▶│  Portfolio Manager           │     │
│  │ Agg / Neutral / Con│   │  (final buy/sell/hold call)  │     │
│  └────────────────────┘   └──────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

**Key principle:** Specialization + adversarial debate. No single agent makes the call alone.

---

## 2. Setup Checklist

### 2.1 Environment

```bash
cd TradingAgents
uv sync                    # or: source .venv/bin/activate if already done
source .venv/bin/activate
```

### 2.2 API Keys

```bash
# OpenRouter (recommended — access to multiple models through one key)
OPENROUTER_API_KEY=sk-or-v1-...

# Or individual providers
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=...
```

### 2.3 Verification

```bash
tradingagents --help       # CLI available
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"
```

---

## 3. Running an Analysis

### 3.1 Interactive CLI (Recommended for exploration)

```bash
tradingagents analyze
```

Walks you through 8 steps:

| Step | Decision | Default | Notes |
|------|----------|---------|-------|
| 1 | Ticker | SPY | Use exchange suffix for non-US: `7203.T`, `0700.HK` |
| 2 | Analysis date | Today | Historical dates OK (backtesting) |
| 3 | Output language | English | Internal debate stays in English |
| 4 | Analyst team | Select from 4 | More analysts = more cost, more perspective |
| 5 | Research depth | 1 round | More rounds = deeper debate, more tokens |
| 6 | LLM provider | Pick one | OpenRouter recommended for model choice |
| 7 | Thinking models | Per provider | Deep = reasoning, Shallow = fast tasks |
| 8 | Effort/thinking mode | Per provider | Higher = more cost, potentially better |

### 3.2 Programmatic API (For automation)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "openai/gpt-5.4"          # Reasoning-heavy tasks
config["quick_think_llm"] = "openai/gpt-5.4-mini"     # Fast/cheap tasks
config["max_debate_rounds"] = 2
config["max_risk_discuss_rounds"] = 2
config["output_language"] = "English"
config["checkpoint_enabled"] = True

graph = TradingAgentsGraph(
    selected_analysts=["market", "news", "fundamentals"],
    config=config,
    debug=True
)

_, decision = graph.propagate("NVDA", "2025-12-15")
print(decision)
```

### 3.3 CLI Flags

```bash
tradingagents analyze --checkpoint           # Enable resume on crash
tradingagents analyze --clear-checkpoints    # Reset all cached state
```

---

## 4. Configuration Deep Dive

### 4.1 LLM Provider & Model Selection

| Provider | Deep Think Model | Quick Think Model | Cost Profile |
|----------|-----------------|-------------------|-------------|
| OpenAI | `gpt-5.4` | `gpt-5.4-mini` | High |
| Google | `gemini-3.1-pro` | `gemini-3.1-flash` | Medium |
| Anthropic | `claude-4.6` | `claude-4.6-mini` | High |
| OpenRouter | Any model via one key | Any model | Variable |

**Practical guidance:**
- **Deep think** handles complex reasoning (debate, risk assessment). Spend tokens here.
- **Quick think** handles formatting, extraction, simple classification. Save money here.
- OpenRouter gives access to all providers through one API key — use model names like `openai/gpt-5.4` or `anthropic/claude-4.6`.

### 4.2 Analyst Team Selection

| Analyst | Data Source | When to Include | Cost Impact |
|---------|------------|-----------------|-------------|
| Market | OHLCV + technical indicators (RSI, MACD, etc.) | Always — cheapest signal | Low |
| News | Company + global news | When events matter (earnings, macro) | Medium |
| Social | Social media sentiment | Meme stocks, retail-driven names | Medium |
| Fundamentals | Financial statements, ratios | Long-term / value analysis | Medium-High |

**Rule of thumb:** Start with Market + News. Add others when the thesis needs them.

### 4.3 Debate Rounds

```python
config["max_debate_rounds"] = 1          # Fast, minimal debate
config["max_debate_rounds"] = 2          # Reasonable depth (recommended)
config["max_debate_rounds"] = 3+         # Deep but expensive
```

Each round = bull argument + bear argument + judge synthesis. Token cost scales linearly.

### 4.4 Data Vendors

```python
config["data_vendors"] = {
    "core_stock_apis": "yfinance",       # Price data
    "technical_indicators": "yfinance",  # RSI, MACD, etc.
    "fundamental_data": "yfinance",      # Financials
    "news_data": "yfinance",             # News articles
}
```

| Vendor | Pros | Cons |
|--------|------|------|
| yfinance | Free, no API key needed | Rate-limited, data quality varies |
| alpha_vantage | More structured, more indicators | Requires API key, has rate limits |

---

## 5. Understanding the Output

### 5.1 Decision Format

The final output is a structured decision from the Portfolio Manager containing:
- **Signal**: Buy / Sell / Hold
- **Position size**: Relative sizing recommendation
- **Rationale**: Synthesis of all team inputs
- **Risk factors**: What could go wrong

### 5.2 Report Artifacts

After each run, reports are saved to:

```
~/.tradingagents/logs/<TICKER>/<DATE>/reports/
├── market_report.md
├── news_report.md
├── sentiment_report.md
├── fundamentals_report.md
├── investment_plan.md          (Research Team decision)
├── trader_investment_plan.md   (Trader plan)
└── complete_report.md          (Consolidated)
```

### 5.3 Decision Memory

The system maintains a persistent memory log:
```
~/.tradingagents/memory/trading_memory.md
```

- Each run appends its decision
- On the next run for the same ticker, past decisions are fed back into the prompt
- The system generates reflections on what worked/didn't
- **This is how the system "learns" over time**

---

## 6. Cost Management

### 6.1 Token Budget Estimation

A typical run with 4 analysts, 2 debate rounds, OpenRouter:

| Stage | Est. Input Tokens | Est. Output Tokens |
|-------|-------------------|-------------------|
| Analyst reports (4x) | ~8,000 | ~4,000 |
| Research debate (2 rounds) | ~12,000 | ~6,000 |
| Trader plan | ~10,000 | ~2,000 |
| Risk debate (2 rounds) | ~8,000 | ~4,000 |
| Portfolio decision | ~12,000 | ~1,000 |
| **Total** | **~50,000** | **~17,000** |

**Ways to reduce cost:**
1. Use fewer analysts (Market only = ~60% reduction)
2. Set `max_debate_rounds = 1`
3. Use cheaper quick_think model (gpt-5.4-mini vs gpt-5.4)
4. Use Gemini Flash for quick tasks

### 6.2 Monitoring

The CLI displays live stats:
- LLM call count
- Tool call count
- Token in/out
- Elapsed time

---

## 7. Common Workflows

### 7.1 Quick Scan (Low Cost)

```python
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
analysts = ["market"]           # Technicals only
```

**Use case:** Screening multiple tickers for signals.

### 7.2 Standard Analysis (Balanced)

```python
config["max_debate_rounds"] = 2
config["max_risk_discuss_rounds"] = 2
analysts = ["market", "news", "fundamentals"]
```

**Use case:** Due diligence on a specific position.

### 7.3 Deep Dive (Maximum Signal)

```python
config["max_debate_rounds"] = 3
config["max_risk_discuss_rounds"] = 3
analysts = ["market", "news", "social", "fundamentals"]
config["deep_think_llm"] = "openai/gpt-5.4"
```

**Use case:** High-conviction decision before significant capital allocation.

### 7.4 Backtesting a Date

```python
_, decision = graph.propagate("AAPL", "2025-03-15")  # Historical date
```

The agents will only have access to data available up to that date.

---

## 8. Persistence & Recovery

### 8.1 Checkpoints (Crash Recovery)

```bash
tradingagents analyze --checkpoint
```

- Saves state after each agent node
- Crashed run resumes from last completed step
- SQLite stored at `~/.tradingagents/cache/checkpoints/<TICKER>.db`
- Auto-cleared on successful completion

### 8.2 Memory (Cross-Run Learning)

- Always on, no flag needed
- Appends decisions to `~/.tradingagents/memory/trading_memory.md`
- Injects recent same-ticker decisions + cross-ticker lessons into prompts
- Limit with `config["memory_log_max_entries"] = 10`

---

## 9. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ConnectionError` on data fetch | yfinance rate limit | Wait 30s, retry. Or switch to Alpha Vantage |
| LLM returns empty response | Model too weak for reasoning task | Upgrade deep_think_llm |
| Run hangs on debate | LLM not returning structured output | Check model supports JSON/structured output |
| `cnda` / `conda` not found | README out of date | Use `uv` instead (already set up) |
| Python 3.14 build fails | PyO3 doesn't support 3.14 yet | Use Python 3.13 |
| "No API key" error | .env not loaded | Run from project root, verify `.env` exists |
| Ollama connection refused | Local model not running | `ollama run <model>` first |

---

## 10. Limitations (Read This)

1. **Not financial advice.** The README says it explicitly. The system is a research tool.
2. **Garbage in, garbage out.** yfinance data quality varies. News sentiment is noisy.
3. **LLM reasoning is non-deterministic.** Same inputs → different outputs on reruns.
4. **No real-time execution.** This generates decisions, it doesn't place trades.
5. **Memory is primitive.** The "learning" is prompt injection of past text, not actual model training.
6. **Backtesting looks clean.** Past analysis dates work, but there's no slippage, commissions, or execution modeling.

---

## 11. Quick Reference Card

```bash
# Activate environment
source .venv/bin/activate

# Interactive analysis
tradingagents analyze

# With checkpoint resume
tradingagents analyze --checkpoint

# Reset checkpoints
tradingagents analyze --clear-checkpoints

# Direct Python execution
python main.py

# Run tests
uv run pytest -v
uv run pytest -v -m smoke   # Quick smoke tests only
```

```python
# Programmatic quick start
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "openai/gpt-5.4"
config["quick_think_llm"] = "openai/gpt-5.4-mini"

graph = TradingAgentsGraph(
    selected_analysts=["market", "news"],
    config=config,
    debug=True
)
_, decision = graph.propagate("SPY", "2025-01-15")
```

---

*Last updated: 2026-05-02 | Project version: 0.2.4*
