# Non-interactive analysis

```bash
tradingagents analyze NVDA
# Equivalent from a source checkout:
python -m cli.main analyze NVDA
```

`SYMBOL` is the only required argument. The command uses the **same CLI runner,
streamed state processing, native dashboard, report writer and log format as
interactive mode**, with inputs supplied by flags/configuration rather than
questions. Bare `tradingagents` remains interactive; `backtest` is unchanged.

Configure credentials in `.env` / the environment first. Headless mode never
opens the wizard, asks for a key, or reads/writes saved interactive preferences.
Missing credentials fail instead of prompting.

## Defaults and precedence

- **Date:** today in the machine's local timezone, resolved at invocation time;
  not automatically the last market trading day.
- **Analysts:** market, sentiment (`social`), news and fundamentals. Auto-detected
  crypto runs use all applicable analysts (market, social and news).
- **Effort:** medium, meaning **3 research-debate and 3 risk-discussion rounds**.
  This is workflow depth, not a model's internal reasoning token budget.
- **Provider/models/language/headers:** existing `.env` / `DEFAULT_CONFIG`.
  OpenCode Go and custom headers continue to work without extra setup.
- **Saving:** native incremental logs/sections are always saved. A complete
  report is automatically exported as well, unless `--no-save-report` is given.
- **Display:** the native live dashboard appears in a normal terminal; no
  questions are asked. The optional final full-report print is off by default.

Explicit flags override their corresponding environment settings. Round-count
precedence remains: individual `--debate-rounds` / `--risk-rounds`, explicit
`--effort`, environment round overrides, then 3 for each unset count. These
requested headless defaults do not overwrite saved interactive preferences.

## Native directories and logging

With the default results root, an example historical run writes:

```text
~/.tradingagents/logs/
├── GOOG/
│   ├── 2026-09-27/
│   │   ├── message_tool.log
│   │   ├── run.json
│   │   └── reports/
│   │       ├── market_report.md
│   │       ├── sentiment_report.md
│   │       ├── news_report.md
│   │       ├── fundamentals_report.md
│   │       ├── investment_plan.md
│   │       ├── trader_investment_plan.md
│   │       └── final_trade_decision.md
│   └── TradingAgentsStrategy_logs/
│       └── full_states_log_2026-09-27.json
└── reports/
    └── GOOG_<YYYYMMDD_HHMMSS>/
        ├── complete_report.md
        ├── 1_analysts/
        ├── 2_research/
        ├── 3_trading/
        ├── 4_risk/
        └── 5_portfolio/
```

There are **two native report locations**, serving different purposes:

1. `<results_dir>/<symbol>/<analysis-date>/reports` holds the incremental,
   flat-named sections. These are written as states arrive, not only at the
   end. An interrupted/failed run retains the sections already generated.
   Only selected/generated sections are written.
2. `<results_dir>/reports/<symbol>_<timestamp>` is the interactive **Save report?**
   default export location: the consolidated Markdown report and team subfolders.
   Headless mode defaults to the equivalent of answering Yes and accepting that
   path. `--output-dir` selects an explicit export path; `--no-save-report` skips
   this extra export, not the native incremental files/log.

`message_tool.log` uses the native timestamped `[System]`, `[User]`, `[Agent]`,
`[Data]` / `[Control]` and `[Tool Call]` events. Tool call arguments and generated
text are included just as in interactive mode. Treat these logs/reports as
private data. Configuration headers/keys are not dumped into the run summary.
Warnings from external data providers remain visible on stderr; they are not
silently suppressed or converted into fabricated report data.

**Rerun behavior matches interactive mode:** the same symbol/date reuses its
directory; the message/tool log appends, generated section files overwrite,
and the final-state JSON replaces that date's prior snapshot. Existing files
for unselected sections are not automatically deleted. Use the selected-agent
list in `run.json` or the complete export to identify the current run's output.
An explicitly reused export directory likewise overwrites generated names and
leaves unrelated files alone. Choose a different results root/export path when
separate archives are needed; default export timestamps have second precision.

The previous headless `runs/` naming is no longer used. Existing `runs/` contents
are not migrated, removed or modified. To change the common results root, use
`TRADINGAGENTS_RESULTS_DIR` or `--results-dir`.

## Live view and post-run choices

Both CLI modes now use `cli.run.run_analysis` and the existing `cli.display`
layout: **Progress**, **Messages & Tools**, **Current Report**, and the statistics
footer (agents/reports, LLM/tool calls, available tokens and elapsed time).
The elapsed/statistics display refreshes even while a model call is in flight.
Native incremental journaling runs independently of whether a display is enabled.

The display goes to stderr, is automatically disabled for `--json` or redirected
stdout/stderr, and closes on success, failure or Ctrl+C. `--progress` explicitly
enables it; with no usable terminal, that flag uses plain status events instead
of terminal control sequences. `--no-progress` disables only the display.

The interactive post-run questions have explicit headless equivalents:

| Interactive choice | Headless equivalent |
| --- | --- |
| Save report? Yes (default) | `--save-report` (default) |
| Save report? No | `--no-save-report` |
| Save path | `--output-dir DIR` (complete export only) |
| Display full report? Yes | `--show-report` |
| Display full report? No | `--no-show-report` (default) |
| Clear saved checkpoints | `--clear-checkpoints` (explicit, clears all just like the native flag) |

The full report, when requested, also goes to stderr. JSON stdout remains one
parseable summary. No prompts are reintroduced by any of these flags.

```bash
tradingagents analyze GOOG --language Chinese
tradingagents analyze GOOG --date 2026-09-27 --no-progress
tradingagents analyze GOOG --show-report
tradingagents analyze GOOG --no-save-report
tradingagents analyze GOOG --output-dir ./exports/goog --json
tradingagents analyze GOOG --json --progress > summary.json 2> progress.log
```

## Parameters

Put flags **after `analyze`**. Use `tradingagents analyze --help` for the full
reference. Root analysis flags before this subcommand are rejected, not ignored.

| Parameter | Meaning |
| --- | --- |
| `SYMBOL` | Required ticker; existing symbol normalization applies. |
| `--date YYYY-MM-DD` | Today by default; invalid/future dates fail before requests. |
| `--analysts all` | Or a comma-separated subset of `market,social,news,fundamentals`; `sentiment` aliases `social`. |
| `--effort shallow\|medium\|deep` | 1 / 3 / 5 rounds; `--depth` is an alias. |
| `--debate-rounds N`, `--risk-rounds N` | Positive per-debate overrides. |
| `--asset-type auto\|stock\|crypto` | Auto-detection by default. |
| `--provider NAME` | Changing provider also requires both model flags. |
| `--quick-model ID`, `--deep-model ID` | Model overrides. |
| `--backend-url URL` | Provider API base URL. |
| `--header 'Name: value'` | Repeatable; merges case-insensitively, last CLI value wins. Keep secrets in `.env`. |
| `--language NAME` | Report language. |
| `--temperature N`, `--max-tokens N`, `--max-retries N` | Sampling, output cap and retry budget. |
| `--checkpoint / --no-checkpoint` | Override environment checkpoint settings. |
| `--clear-checkpoints` | Delete all saved checkpoints before starting; never happens implicitly. |
| `--portfolio FILE` | Existing holdings/cash JSON input. |
| `--results-dir DIR` | Root for native logs, JSON states and default exports. |
| `--output-dir DIR` | Complete-report export path; does not move the native ticker/date logs. |
| `--save-report / --no-save-report` | Enable/disable complete export; native logs/sections are always saved. |
| `--show-report / --no-show-report` | Print the full report without asking; default off. |
| `--progress / --no-progress` | Display control; independent of logging/saving. |
| `--json` | One JSON summary on stdout; everything else goes to stderr. |

Changing providers still drops inherited endpoint/headers to avoid forwarding
provider-specific credentials to another service. Set the new endpoint/headers
explicitly as needed. Changing only a model within one provider preserves them.
`--output-dir` cannot be combined with `--no-save-report`.

## Execution parity and automation

Both CLI entry points now share initial-state creation (instrument identity,
portfolio context, pending-decision settlement and historical memory cutoff),
ordered analyst execution, tool loops, debates, state streaming, per-section
journaling, final JSON logging, decision recording and checkpoint teardown.
The workflow is executed once. Full `values` snapshots are consumed as snapshots,
without retaining an ever-growing list of earlier states. Checkpoint resume
still feeds `None`; graph-execution failure keeps the checkpoint. Successful
analysis records the decision once and clears it. A later export failure does
not undo that recorded analysis or recreate its cleared checkpoint. Memory/cache locations are not relocated into report folders.

Headless `run.json` lives beside `message_tool.log`. Its `status` transitions from
`running` to `completed`, `failed` or `interrupted`, so a failed rerun cannot leave
an older success summary looking current. The successful stdout JSON matches
this file. `output_dir` is the native ticker/date directory, `log_file` is its
message/tool log, and `report` is the complete export path (null when disabled).

Usage errors return 2; runtime/configuration/export failures return 1 with no
success JSON. A completed analysis returns 0, but automation must still check
`needs_review`: an unparseable decision is exported as `REVIEW`, not a position.
Go session headers and provider-specific compatibility rules are unchanged;
see [OpenCode Go](opencode-go.md) for session persistence and service scope.
