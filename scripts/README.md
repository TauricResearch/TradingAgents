# scripts/

Run TradingAgents analyses and build the report site.

| Script | What it does | Key args |
|--------|--------------|----------|
| `report_workflow.py` | **Main entry.** Reassemble reports, validate `docs/`, and compile `_site`. | `--analysis-date YYYYMMDD`, `--dry-run` |
| `build_publish_site.py` | Merge unpublished local reports with the compiled `gh-pages` history. | `--analysis-date`, `--base-ref`, `--dry-run` |
| `publish_site.sh` | Incrementally publish new reports, preserving prior dates and Git history. | `--analysis-date`, `--build-only`, `--dry-run` |
| `run_one.py` | One-ticker headless run (max depth). | `--ticker` (req), `--date` |
| `run_top_tickers.sh` | Parallel run, one Docker container per ticker. | env: `CONCURRENCY`, `TRADINGAGENTS_DATE` |
| `build_reports_site.py` | Lower-level generated Markdown renderer used by `report_workflow.py`. | `--summary-analysis-date`, `--summary-only` |
| `reassemble_complete_reports.py` | Rebuild missing `complete_report.md`. | — |
| `prune_report_headings.py` | Normalize headings across reports. | — |
| `smoke_structured_output.py` | Smoke-test structured-output agents vs. a real LLM. | `provider`, `--deep-model`, `--quick-model` |

Run every ticker missing today's report via the `/run-missing` skill.

## Missing-report launcher mode

`run_missing_today_claude.sh`, `run_missing_today_gemini.sh`, and
`run_missing_today_gpt.sh` use CLIProxyAPI by default. Set one shared variable
to use each provider's direct API instead:

```bash
export TRADINGAGENTS_MODE=direct
bash scripts/run_missing_today_gemini.sh --check-only
bash scripts/run_missing_today_claude.sh --check-only
bash scripts/run_missing_today_gpt.sh --check-only
```

`TRADINGAGENTS_CLAUDE_MODE`, `TRADINGAGENTS_GEMINI_MODE`, and
`TRADINGAGENTS_GPT_MODE` override the shared setting for their own launcher.
Each mode accepts `proxy` or `direct`. Direct mode uses the corresponding
provider API key from the environment or project `.env`.
The older `run_all_today.sh` has no proxy/direct selector.

## Incremental releases

Install the documentation dependencies with `python3 -m pip install '.[docs]'`.
Place completed runs in `docs/<TICKER>/<YYYYMMDD>_<MODEL>_<RUN_TIMESTAMP>/`.
Use a new run folder when correcting a published report: existing published
folders are immutable and are skipped, even if their local Markdown changes.

```bash
# Offline preview against the locally cached origin/gh-pages commit:
bash scripts/publish_site.sh --analysis-date 20260923 --dry-run
bash scripts/publish_site.sh --analysis-date 20260923 --build-only

# Fetch the latest deployment, add this date's unpublished runs, and publish:
bash scripts/publish_site.sh --analysis-date 20260923
```

Omit `--analysis-date` to add all unpublished local runs, including backfills.
Each release starts from `gh-pages`, compiles only unpublished runs using the
report workflow, merges daily summaries, ticker indexes and sitemaps, then
checks that all historical report pages are unchanged and reachable. Old assets
remain available for old pages. Historical report pages keep their original
navigation; the homepage and updated ticker hubs link to the merged history.

The normal push extends the prior deployment commit. If another release lands
while building, the push fails safely; rerun to rebuild against that deployment.
Running again after a successful release creates no additional release commit.
`PUBLISH_RETAIN_DATES` only limits which **local** dates to consider; it never
deletes published dates. The build refuses to exceed a 1,000,000,000-byte site
budget instead of pruning historical reports.

Builds use temporary directories before installing `_site/`. Previous local
previews are kept in `.tradingagents/site-backups/`; these backups accumulate
and can be removed manually once no longer needed. Dry runs leave `_site/` and
`docs/` unchanged. Missing or malformed published history stops the release.

`report_workflow.py` and the pre-commit hook still build from local Markdown
only. Use `publish_site.sh` for releases: it restores historical content from
`gh-pages` even if a local-only build has replaced `_site/`.

All report Markdown under `docs/` is currently gitignored. Incremental releases
preserve published HTML, **not** original Markdown, stage outputs, or raw market
data. Back up those source files separately if you need to rerun analyses.
