# Research Report CLI

Generate a local Markdown report with:

```text
python -m tradingagents.research_platform.cli_report NVDA --as-of 2026-01-05
```

By default the command uses `YFinanceProvider` and writes to
`research_reports/`.

## Optional Cache

```text
python -m tradingagents.research_platform.cli_report NVDA \
  --as-of 2026-01-05 \
  --cache-dir .research_cache
```

The cache stores normalized JSONL artifacts by symbol.

## Optional Manual Signal

```text
python -m tradingagents.research_platform.cli_report NVDA \
  --as-of 2026-01-05 \
  --direction buy \
  --signal-date 2026-01-02 \
  --position-pct 5 \
  --confidence 75 \
  --max-single-position-pct 3
```

Percent arguments accept either decimals (`0.05`) or human percentages (`5`).

When a manual signal is supplied, the CLI runs:

```text
TradeSignal -> RiskReview -> BacktestResult -> Markdown report
```

Without a signal, it still produces a data/notes/thesis report.
