# TradingAgents Upstream Sync Report

**Date**: 2026-06-15 00:00 (GMT+8)
**Repository**: `david188888/TradingAgents`
**Upstream**: `TauricResearch/TradingAgents`

---

## Summary

| Item | Status |
|------|--------|
| New commits | **46** |
| Merge result | **CONFLICT — aborted** |
| Open PRs (upstream) | 10 |

---

## New Upstream Commits (46)

```
3cddf1e fix(llm): use the OpenAI Responses API only for native endpoints
308757c fix(data): catch http.client transport errors in StockTwits
eeb84aa fix(reddit): go RSS-first with 429 backoff and robust transport errors
9fd54f8 fix(data): reject stale yfinance OHLCV instead of reporting wrong prices
7df18fc refactor(data): unify vendor errors under a VendorError hierarchy
db05903 feat(data): add Polymarket prediction markets as a keyless vendor
ddfb840 feat(data): add FRED macro indicators as an optional vendor
895ed13 feat(llm): add Amazon Bedrock as a first-class provider
295e84c feat(llm): add NVIDIA NIM, Kimi, Groq, and Mistral providers
20d3b07 feat(llm): unify OpenAI-compatible providers behind a registry + generic endpoint
4e7821d fix(graph): register get_verified_market_snapshot in the market ToolNode
0c1231a fix(data): keep future/undated news out of historical windows
e4be7cc fix(data): add Alpha Vantage request timeout and stop mislabeling bad keys
a597063 fix(cli): correct invalid escape sequence in confirm_ollama_endpoint docstring
dab0768 fix(data): include the requested end date in yfinance fetches
6560883 fix(data): respect the configured vendor chain and log vendor failures
76add90 fix(cli): unify ticker handling with the data-path symbol normalizer
7c8fe2f fix(data): normalize symbols on the identity and reflection paths
2a58c22 ci: add test/lint/smoke workflow, declare python-dotenv, recommend Python 3.12
04f434e chore: README housekeeping and remove stale TODO
2e67782 feat(cli): skip interactive LLM selection when configured via environment (#873)
1ff3f07 fix: support commodity/forex/crypto tickers and never invent prices (#781)
2f85be6 chore(llm): add latest models and default to GPT-5.5
c93b92c feat(markets): add China A-share benchmarks and document non-US tickers
d6762d6 chore: gitignore .env.enterprise and reports/
8694bd0 fix(llm): send MiniMax reasoning_split via extra_body so the openai SDK accepts it (#826)
2c9f1bf fix(cli): consolidate duplicate get_ticker and only announce non-stock asset type
8a22594 feat(config): expose sampling temperature and document reproducibility
47cbb32 feat(market): verified market-data snapshot to ground numeric claims
e80636f feat(sentiment): structured output for the Sentiment Analyst
a66aa8f fix(deps): require yfinance >=1.4.1 and tolerate non-Date index column
3543e53 fix(dataflows): fall back to Reddit RSS search when JSON 403s
d7b40a2 fix(graph): resolve instrument identity to stop wrong-company hallucination
61522e1 fix(llm): skip Anthropic effort kwarg on non-supporting models (#831)
e848b5e fix(llm): gate MiniMax reasoning_split by model capability (#826)
3e5e99b fix(graph): integrate #487 + #567 — sentiment label, route, propagate asset_type
a2e7ac1 Merge #567 — analysis-only crypto asset mode
b16fe53 Merge #487 — analyst execution planning and timing hooks
249caba Merge remote-tracking branch 'upstream/main' into analyst-phase1-observability
a2f343b Merge remote-tracking branch 'upstream/main' into crypto-analysis-mvp
5bae826 Merge remote-tracking branch 'upstream/main' into crypto-analysis-mvp
99ec63f merge upstream main into crypto-analysis-mvp
e7ec980 feat: add analysis-only crypto asset mode
f4519bc use execution plan metadata for first analyst
4300b68 merge upstream main into analyst-phase1-observability
2d2c9e6 add analyst execution planning and timing hooks
```

### Key Changes by Category

- **New LLM Providers**: Amazon Bedrock, NVIDIA NIM, Kimi, Groq, Mistral; unified OpenAI-compatible registry
- **New Data Vendors**: Polymarket prediction markets, FRED macro indicators
- **Major Fixes**: yfinance stale data rejection, Reddit RSS fallback, symbol normalization, instrument identity resolution
- **Crypto Support**: Analysis-only crypto asset mode (#567)
- **CI**: New test/lint/smoke workflow
- **Models**: Default upgraded to GPT-5.5

---

## Merge Conflict Report

**Status**: Merge aborted — 17 files with conflicts.

### Conflicting Files

| # | File | Area |
|---|------|------|
| 1 | `.env.example` | Config |
| 2 | `.gitignore` | Config |
| 3 | `README.md` | Docs |
| 4 | `cli/main.py` | CLI |
| 5 | `cli/utils.py` | CLI |
| 6 | `tradingagents/agents/analysts/news_analyst.py` | Agents |
| 7 | `tradingagents/agents/utils/agent_states.py` | Agents |
| 8 | `tradingagents/agents/utils/agent_utils.py` | Agents |
| 9 | `tradingagents/dataflows/interface.py` | Data |
| 10 | `tradingagents/dataflows/y_finance.py` | Data |
| 11 | `tradingagents/default_config.py` | Config |
| 12 | `tradingagents/graph/conditional_logic.py` | Graph |
| 13 | `tradingagents/graph/setup.py` | Graph |
| 14 | `tradingagents/graph/trading_graph.py` | Graph |
| 15 | `tradingagents/llm_clients/anthropic_client.py` | LLM |
| 16 | `tradingagents/llm_clients/factory.py` | LLM |
| 17 | `tradingagents/llm_clients/openai_client.py` | LLM |

### Conflict Concentration

- **Graph layer** (4 files): Major refactoring in conditional_logic, setup, trading_graph
- **LLM clients** (3 files): Provider registry changes affect anthropic, openai, factory
- **CLI** (2 files): Ticker handling and main entry changes
- **Data** (2 files): Interface and yfinance changes
- **Config** (3 files): .env, .gitignore, default_config

### Recommended Next Steps

1. **Manual merge required** — conflicts span core modules (graph, llm, data)
2. Prioritize merging LLM client changes first (provider registry is the biggest structural shift)
3. Review `agent_states.py` and `agent_utils.py` carefully — asset_type propagation changes
4. Test after merge: run `python cli/main.py` with a simple ticker to verify no regressions

---

## Open PRs on Upstream (10)

| # | Title | Author | State |
|---|-------|--------|-------|
| 1035 | fix(fred): validate series_id and degrade gracefully | Handsomemikezzz | OPEN |
| 1033 | fix(dataflows): log swallowed vendor errors | nyxst4ck | DRAFT |
| 1032 | feat(llm): add local LLM response cache | hansonxhj | OPEN |
| 1031 | feat: Add stock holdings management system | what168gp-jpg | OPEN |
| 1030 | fix(deps): regenerate stale uv.lock | macd2 | OPEN |
| 1029 | fix(cli): declare python-dotenv dependency | Gujiassh | OPEN |
| 1027 | fix(graph): don't reprint unchanged trailing message | LukiPrince | OPEN |
| 1025 | feat(news): add geopolitical risk analysis | jaylew20250206 | OPEN |
| 1017 | Honor env backend URL after provider selection | gyx09212214-prog | OPEN |
| 1004 | feat: 切换信息源 | 3-Flamingo | OPEN |
