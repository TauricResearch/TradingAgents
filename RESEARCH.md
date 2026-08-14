# TradingAgents — Research Improvements

> Fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents),
> licensed under Apache-2.0.
> Original paper: [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138).

## Roadmap

| # | Status | Improvement | Upstream issue | PR |
|---|--------|-------------|----------------|----|
| A1 | ✅ Done | Fix look-ahead bias in social-sentiment pipeline | [#1220](https://github.com/TauricResearch/TradingAgents/issues/1220) | [#1232](https://github.com/TauricResearch/TradingAgents/pull/1232) |
| A2 | 🚧 Planned | Reproducible backtesting / evaluation harness | [#119](https://github.com/TauricResearch/TradingAgents/issues/119) | — |
| A3 | 📋 Planned | Fix first-speaker fabrication in multi-agent debates | [#1176](https://github.com/TauricResearch/TradingAgents/issues/1176) | — |

## A1: Look-ahead bias fix
- **Problem**: historical runs fed today's StockTwits/Reddit posts into the
  sentiment prompt as if they covered the requested period.
- **Fix**: both fetchers now filter by the analysis window; empty results
  degrade to explicit placeholders; prompt labels show the real window.
- **Validation**: 9 new regression tests; full suite 576 passed / 2 skipped.
