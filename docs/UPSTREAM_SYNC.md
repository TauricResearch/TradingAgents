# Upstream sync (TauricResearch → this fork)

This fork tracks [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
and also carries workspace-only work (HTTP `/decide` service, Indian news/sentiment,
MCX commodities, 1-day gap prompts, structured mode, external-signal prior, etc.).

**Never** use GitHub's "Sync fork" / `gh repo sync --force`. Those overwrite fork files.

## One command (local)

From the repo root:

```bash
python scripts/sync_upstream.py
```

That fetches `upstream`, creates `sync/upstream-YYYYMMDD` from `origin/main`,
merges `upstream/main`, and either:

- prints "clean merge — open a PR", or
- lists conflict files and stops so they can be resolved with the policy below.

## Automatic weekly PR

`.github/workflows/sync-upstream.yml` runs Monday 06:00 UTC and on
`workflow_dispatch`. It opens a PR when `upstream/main` is ahead. It does
**not** auto-merge: overlapping files almost always need a keep-both resolution.

## Conflict policy

| File class | Rule |
|---|---|
| Fork-only (`scripts/decide.py`, `scripts/service.py`, `indian_news.py`, Docker/deploy, retro scripts, holding-recommendation, external-signal, structured mode, commodity asset type) | Keep ours. Upstream has no equivalent. |
| Shared agents / dataflows / graph | Keep **both**: fork prompts/fields/callers **and** the upstream fix. |
| Tests | Keep both suites. |
| `pyproject.toml` / README / CHANGELOG | Take upstream version/docs, keep our extra deps (`fastapi`, `uvicorn`). |

Recurring overlap (resolve by combining, never by `-X ours` / `-X theirs`):

- `tradingagents/agents/trader/trader.py` — 1-day horizon + debate ablation + external signal **and** technical-report grounding
- `tradingagents/agents/managers/{research,portfolio}_manager.py` — gap prompts + external signal **and** "don't force a direction"
- `tradingagents/agents/utils/rating.py` + `graph/signal_processing.py` — holding-recommendation parser **and** `REVIEW` sentinel
- `tradingagents/graph/trading_graph.py` — `external_signal_*` kwargs **and** checkpoint lifecycle / `REVIEW`
- `tradingagents/dataflows/stocktwits.py` — `.NS`→`.NSE` mapping **and** look-ahead window
- `tradingagents/dataflows/yfinance_news.py` — use shared `date_window.in_window`; Indian RSS keeps `utils.in_news_window` (wrapper)

After resolving: run `pytest -q` and open a PR. Do not push straight to `main`.
