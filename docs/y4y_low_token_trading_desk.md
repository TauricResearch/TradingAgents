# Y4Y Low-Token Trading Desk on TradingAgents

Goal: keep TauricResearch/TradingAgents' useful trading-firm structure, but stop paying for the full 11+ LLM call workflow on every ticker. The desk should spend LLM tokens only after cheap deterministic gates say a symbol is worth human/agent attention.

## Executive design

```
Universe -> deterministic scanner -> evidence pack -> cheap desk -> gated full desk -> executor/report
```

### Tier 0 — deterministic scanner, no LLM
Runs on a broad watchlist using market data only.

Inputs:
- OHLCV / intraday quote
- ATR, RSI, MACD, moving averages, volume ratio
- spread / liquidity / options volume if available
- existing positions and risk budget
- event calendar flags: earnings, FOMC, CPI, Fed speakers

Output per symbol:
```json
{
  "symbol": "NVDA",
  "score": 0-100,
  "direction_bias": "long|short|neutral",
  "why": ["above VWAP", "volume_ratio>1.8", "RSI reset"],
  "risk_flags": ["earnings<3d", "spread_wide"],
  "eligible": true
}
```

Hard gates before any LLM:
- skip if spread too wide
- skip if volume below threshold
- skip if ATR/stop distance makes risk too large
- skip if earnings/FOMC/event risk violates profile
- skip if no clean stop/target plan
- skip if already max positions

### Tier 1 — cheap analyst desk, 1 cheap LLM call per finalist
Only top 3-5 scanner names reach this.

Use a cheap/fast model, not frontier:
- Preferred API: `deepseek/deepseek-v4-flash` through OpenRouter or DeepSeek direct
- Backup cheap: `stepfun/step-3.7-flash` if free in UI, otherwise worse value than DeepSeek V4 Flash
- Local option: Ollama / LM Studio via repo's `openai_compatible` provider for summaries only

Prompt shape must be compressed and structured:
- max ~1,500-2,500 input tokens per symbol
- only the deterministic evidence pack, not raw articles/logs
- output strict JSON: pass/fail, direction, catalysts, stop, target, confidence

Tier 1 does NOT run bull/bear/risk debates. It is a triage filter.

### Tier 2 — focused TradingAgents run, 1-2 symbols only
Use the actual repo graph, but restrict analysts based on the setup:

| Setup | `selected_analysts` | Reason |
|---|---|---|
| intraday / scalping | `("market", "news")` | technicals + live catalyst only |
| swing trade | `("market", "news", "fundamentals")` | adds valuation/earnings context |
| sentiment/crowded retail name | `("market", "social", "news")` | meme/social risk matters |
| earnings/FOMC/high-vol | full set | only when event risk justifies spend |

Config:
```python
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["news_article_limit"] = 5
config["global_news_article_limit"] = 3
config["global_news_lookback_days"] = 3
config["temperature"] = 0.0
config["checkpoint_enabled"] = True
```

Model routing:
```python
config["llm_provider"] = "openrouter"
config["quick_think_llm"] = "deepseek/deepseek-v4-flash"
config["deep_think_llm"] = "deepseek/deepseek-v4-flash"   # default low-burn
```

Escalate `deep_think_llm` to Sonnet/GPT only if:
- proposed trade score >= 80
- real-money profile and position size > normal starter
- event risk requires nuanced reasoning
- cheap desk and deterministic gates disagree
- final output would trigger actual order placement

### Tier 3 — execution/risk gate, no creative LLM
Final gate should be deterministic code, not vibes.

Checks:
- max dollars at risk
- stop distance and quantity
- position correlation / sector concentration
- daily loss stop
- option liquidity / bid-ask spread if options
- no 0DTE unless explicitly allowed
- market hours / no after-hours bracket unless supported

Output:
- `EXECUTE`, `WATCH`, or `REJECT`
- reason code
- exact position size
- stop, target, invalidation

## Token-burn reductions vs stock TradingAgents

1. **Do not run full framework on the whole universe.** Scanner handles breadth.
2. **Reduce analyst set dynamically.** Most names do not need social + fundamentals + macro every run.
3. **Summarize data before LLM.** Feed compact evidence packs, not raw news/articles/tool dumps.
4. **Cache daily slow data.** Fundamentals/news/global macro should not be refetched every 5 minutes.
5. **Use cheap model for all routine nodes.** Frontier model only for rare escalation.
6. **Keep debate rounds at 1.** Multi-round debate is expensive and usually redundant for screening.
7. **Use structured outputs.** JSON avoids long narrative reports until a trade is actually actionable.
8. **Only write full markdown report for actionable finalists.** Otherwise log compact JSON.

## Practical model budget

Default cheap route:
- Quick + deep: DeepSeek V4 Flash
- Reasoning effort: low / none unless provider supports cheap thinking mode
- Output cap: 600-900 tokens for triage, 1,500 for final full report

Escalation route:
- Cheap model makes the case
- Premium model acts as final committee chair only after deterministic gate passes
- One premium call maximum per trade idea

## Recommended desk roles

### Deterministic Scanner
Code-only. Produces ranked candidates and evidence packs.

### Tape/Technical Analyst
Usually TradingAgents `market` analyst. Cheap model. Verifies setup.

### Catalyst Analyst
TradingAgents `news` analyst with article limits reduced. Cheap model.

### Fundamentals Analyst
Only for swing trades / multi-day debit options / high conviction equities.

### Sentiment Analyst
Only for meme/high-retail names or when social squeeze risk matters.

### Bull/Bear Research Pair
Keep, but one round only. Use cheap model. Their job is to find disconfirming evidence, not write essays.

### Risk Officer
Mostly deterministic. LLM can summarize risk, but sizing/eligibility is code.

### Portfolio Manager
Default cheap model. Escalate only on real-money/actionable trades.

## Output format for Discord

Keep final report tiny:

```
SYMBOL — ACTION / WATCH / REJECT
Bias: long/short/neutral | Score: 84/100 | Risk: low/med/high
Entry: x.xx | Stop: x.xx | Target: x.xx | Size: $150 risk / N shares/contracts
Why: 3 bullets max
Reject/Watch reason: if not executing
```

## First implementation target

Use the repo as a research engine, not an always-on auto-trader:

1. Build `scripts/y4y_low_token_desk.py`
2. It runs scanner across a watchlist
3. It selects top N
4. It runs TradingAgents only on those finalists with a reduced analyst set
5. It writes `results/y4y_desk/latest.json`
6. A separate executor can consume only `EXECUTE` records after deterministic risk checks

## Safety stance

Paper first. No direct live execution until:
- 30+ trading days forward-tested
- costs/slippage included
- exact Alpaca/RH execution constraints wired
- daily stop-loss and position watcher verified
- premium-model escalation does not change deterministic risk limits
