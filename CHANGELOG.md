# Changelog

## 1.0.0 (2026-11-24)

- TradingAgents: Towards Agentic Finance Research.

### Research

- Agents: Equity Research, Macro Strategy, Quant Research and Risk Analysis research in parallel and report back.
- Skills: sixteen built-in research methods, from an earnings review to a DCF valuation.
- Your own agents and skills, as Markdown files.
- Plan mode: review and revise a research plan before it runs.
- Sources: every figure is cited to the data it came from.

### Data and models

- Data: with a Tauric API key, market data, fundamentals, filings, news, economic series and prediction-market odds.
- Compute: statistics, risk, technical indicators, valuation and portfolio construction over the data read.
- Models: Tauric AI, OpenAI, Anthropic, Google, DeepSeek, OpenRouter, AI subscriptions (ChatGPT), or self-hosted models.

### Sessions and output

- Sessions: resume any session, and sync sessions to your Tauric account.
- Export: a PDF report or Markdown; `/copy` copies the answer.
- Scripting: `tradingagents -p` answers one question; `--json` streams events; `--limit` caps time, tokens and steps.

### Install

- `curl -fsSL https://tauric.ai/tradingagents/install.sh | sh` or `npm i -g @tauric/tradingagents`; updates are offered at start.
