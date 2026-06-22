# scripts/

Run TradingAgents analyses and build the report site.

| Script | What it does | Key args |
|--------|--------------|----------|
| `report_workflow.py` | **Main entry.** Reassemble reports, validate `docs/`, and compile `_site`. | `--analysis-date YYYYMMDD`, `--dry-run` |
| `run_one.py` | One-ticker headless run (max depth). | `--ticker` (req), `--date` |
| `run_top_tickers.sh` | Parallel run, one Docker container per ticker. | env: `CONCURRENCY`, `TRADINGAGENTS_DATE` |
| `build_reports_site.py` | Lower-level generated Markdown renderer used by `report_workflow.py`. | `--summary-analysis-date`, `--summary-only` |
| `reassemble_complete_reports.py` | Rebuild missing `complete_report.md`. | — |
| `prune_report_headings.py` | Normalize headings across reports. | — |
| `smoke_structured_output.py` | Smoke-test structured-output agents vs. a real LLM. | `provider`, `--deep-model`, `--quick-model` |

Run every ticker missing today's report via the `/run-missing` skill.

> **Derived artifacts are not committed.** `complete_report.md`, `docs/index.md`,
> and per-ticker `index.md` hubs are gitignored and regenerated from the
> committed stage files by `report_workflow.py`. An everyday-run commit should
> stage only new stage files
> under `docs/<TICKER>/<run>/` — additions-only, no modified aggregates.
> `docs/archive/**` is frozen and stays tracked.
