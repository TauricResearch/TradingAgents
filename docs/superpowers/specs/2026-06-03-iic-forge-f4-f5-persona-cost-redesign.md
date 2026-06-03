# IIC-FORGE F4/F5 Persona-Cost Redesign

| | |
|---|---|
| Date | 2026-06-03 |
| Status | Implemented on `feat/f4-f5-persona-cost-redesign` |
| Supersedes | Any F4/F5 wording that describes approved event studies as `N IIC personas x full TradingAgents graph` by default |

## Decision

The default approved event study is:

```text
triaged event -> strict alert evaluator -> light alert -> user approval
-> one balanced enriched TradingAgents graph -> full brief + analysis pack
-> secretary delivery -> optional directed follow-up using reusable pack
```

The IIC persona is an overlay inside the native TradingAgents graph. It enriches
the existing analyst, researcher, trader, and risk roles instead of wrapping the
whole graph in another persona shell.

Committee mode is explicit. It runs `value`, `momentum`, and `macro` profiles
only when the operator asks for comparison, disagreement analysis, or a
committee-style second opinion.

## Cost And Cache Controls

- Prompt-visible runtime retrieval timestamps were removed from yfinance data
  payloads so repeated runs preserve more stable prefixes.
- Default news prompt budget was lowered to `news_article_limit=20`,
  `global_news_article_limit=12`, and `global_news_lookback_days=7`.
- Cost rows keep DeepSeek prompt-cache hit/miss tokens, and the run recorder
  exposes a cache-hit ratio helper for reports and gates.
- Directed follow-ups reuse persisted Analysis Packs so the next run can focus
  on the requested lens instead of rebuilding the whole context from scratch.

## F2 Recovery

F2 is no longer a stub in this branch. The backtest harness and tests were
selectively restored from `origin/feat/iic-forge-05-f2` into the fork, then
wired through the F5 action-handler path:

```text
full event_alert brief -> accepted run_backtest action
-> brief-scoped F2 harness -> backtests/backtest_runs rows
```

Backtest actions are valid only on full `event_alert` briefs with persisted
run IDs. Light alerts (`event_alert_light`) can launch full studies, not
backtests.

## Combined Exit Gate

Use the combined F4/F5 approval-delivery gate:

```bash
python scripts/f4_f5_exit_gate.py --since 2026-06-03T09:00:00Z --window-hours 12
```

The artifact reports:

- light-alert latency
- strict alert evaluation pass/reject counts
- light and full delivery audit counts
- accepted approval lineage (`light brief -> action -> job -> full brief`)
- worker errors
- cost/cache summary
- operator false-positive/false-negative sample sign-off

Legacy `scripts/f4_exit_gate.py` and `scripts/f5_exit_gate.py` remain useful
for phase-specific checks, but the approval-through-delivery flow should be
judged with the combined gate.
