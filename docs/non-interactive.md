# Non-interactive analysis

```bash
tradingagents analyze NVDA
# Equivalent when running from the source checkout:
python -m cli.main analyze NVDA
```

`SYMBOL` is the only required argument. This command never opens the interactive
wizard, reads saved interactive preferences, asks for API keys, or asks whether
to save. In a terminal it shows live status without requiring input; use
`--no-progress` to disable the display. Configure provider credentials in
`.env` / environment variables first. A missing key fails rather than prompting.
The existing bare `tradingagents` command remains interactive; `backtest` is
unchanged. This is ordinary analysis, not a one-cell backtest.

## Defaults

- **Date:** today in the machine's local timezone, resolved at invocation time.
  It is the calendar date, not automatically the last market trading day.
- **Analysts:** all four: market, sentiment (`social`), news and fundamentals.
  Like the interactive workflow, crypto uses all applicable analysts (market,
  social and news); company fundamentals are not applicable to crypto.
- **Effort:** medium: **3 research-debate rounds and 3 risk-discussion rounds**.
  This is workflow depth, not a provider's token-level reasoning/thinking budget.
  Existing provider-specific reasoning settings remain available through `.env`.
- **Provider, models, language, credentials:** existing `.env` / `DEFAULT_CONFIG`
  settings, including the native OpenCode Go provider and custom headers.
- **Saving:** automatic; each invocation creates its own run directory so a
  second run of the same symbol/date does not overwrite the first one's files.
- **Progress:** live status on stderr when stdout and stderr are terminals;
  disabled automatically for `--json`, redirected output and `TERM=dumb`.

Explicit per-option CLI flags override the corresponding environment settings.
For round counts, the order is: `--debate-rounds` / `--risk-rounds`, then an
explicit `--effort`, then `TRADINGAGENTS_MAX_DEBATE_ROUNDS` /
`TRADINGAGENTS_MAX_RISK_ROUNDS`, then the medium default of 3 for each unset count.
Saved interactive preferences are deliberately not used by headless runs.

## Parameters

Place these **after `analyze`**. Root-level analysis flags before the subcommand
are rejected rather than silently ignored. `--clear-checkpoints` remains an
interactive-mode option; use `--no-checkpoint` for a fresh headless invocation.

| Parameter | Meaning |
| --- | --- |
| `SYMBOL` | Required ticker. Existing symbol normalization applies (`700.HK` → `0700.HK`, `BTCUSDT` → `BTC-USD`, etc.). |
| `--date YYYY-MM-DD` | Analysis date; defaults to today. Invalid/future dates fail before the graph runs. |
| `--analysts all` | All applicable analysts (default). Or a comma-separated subset: `market,social,news,fundamentals`. `sentiment` aliases `social`; order is canonical and duplicates are removed. |
| `--effort shallow\|medium\|deep` | 1 / 3 / 5 rounds of both debates. `--depth` is an alias. |
| `--debate-rounds N` | Positive research-debate count; overrides the effort preset. |
| `--risk-rounds N` | Positive risk-discussion count; overrides the effort preset. |
| `--asset-type auto\|stock\|crypto` | Defaults to auto-detection from the normalized ticker. |
| `--provider NAME` | Override the configured LLM provider. When changing providers, also supply both model flags. |
| `--quick-model ID` | Quick-thinking model override. |
| `--deep-model ID` | Deep-thinking model override. |
| `--backend-url URL` | API base URL override. |
| `--header 'Name: value'` | Repeatable custom HTTP header. Merges with configured headers case-insensitively; the last CLI value for a name wins. |
| `--language NAME` | Report language, such as `Chinese` or `English`. |
| `--temperature N` | Finite, non-negative sampling temperature. Model support still varies. |
| `--max-tokens N` | Positive output-token cap. |
| `--max-retries N` | Non-negative SDK retry budget; 0 disables retries. |
| `--checkpoint / --no-checkpoint` | Override the existing checkpoint setting; otherwise use the environment/default. |
| `--portfolio FILE` | Existing portfolio JSON file with holdings/cash. |
| `--results-dir DIR` | Root used for automatic per-run output directories. |
| `--output-dir DIR` | Exact output directory for this invocation. Must be new or empty; takes precedence over the results root. |
| `--progress / --no-progress` | Enable/disable status on stderr. Explicit `--progress` falls back to plain event lines when stderr is not a usable terminal. |
| `--json` | Emit one JSON summary on stdout; run diagnostics go to stderr. Reports are still saved. |

Changing `--provider` drops the previous provider's inherited backend URL and
headers, to avoid sending provider-specific credentials to a different service.
Pass `--backend-url` / `--header` explicitly for the new provider as needed.
Changing only a model within the same provider retains those settings.
Keep secret headers and API keys in an untracked `.env` / secret manager rather
than command-line arguments (which may be visible in shell history/process lists).

## Examples

```bash
# Today, all analysts, medium depth, existing provider configuration:
tradingagents analyze NVDA

# Historical date, fewer analysts and shallow research:
tradingagents analyze AAPL --date 2026-09-25 --analysts market,news --effort shallow

# Native OpenCode Go, with OPENCODE_GO_API_KEY already in .env:
tradingagents analyze NVDA --provider opencode-go --quick-model glm-5.3-flash --deep-model kimi-k3

# Chinese reports, deeper discussion, resume after a failure:
tradingagents analyze 0700.HK --language Chinese --effort deep --checkpoint

# Explicit output directory and a machine-readable summary:
tradingagents analyze NVDA --output-dir ./results/nvda-run-001 --json
```

For normal Go use you do not need header flags: the provider supplies its
User-Agent and session header. See [OpenCode Go](opencode-go.md) for protocol
selection, service usage requirements and persisting a session ID when resuming
across processes. Headless mode constructs a fresh graph for each invocation.

## Live status without interaction

The display shows each selected analyst and the research, trading, risk and
portfolio agents, with pending/running/waiting/completed/error states. It also
shows per-agent turn counts and execution time, continuously refreshed elapsed
time, report counts, LLM/tool call counts, available token usage and recent
agent/tool events. A turn includes each graph-node invocation (including
analyst tool-call loops); it is not necessarily one configured debate round.
Token counts reflect usage returned by the model, not a billing estimate.

Events come from the existing graph's callbacks. There is no second execution
loop, token streaming requirement, extra LLM request or prompt. Debate agents
wait between turns and complete when their manager starts judging. Resumed
node inputs restore already-produced report status; times and counters measure
only this invocation. Short/narrow terminals use a compact current-stage view.
Ordinary warnings remain visible; the observer never logs tool arguments or
raw model prompts. The live display is cleared on exit, including failures and
Ctrl+C; normal summaries and report paths still print after a successful run.

```bash
# Automatic live display in a terminal, no questions:
tradingagents analyze NVDA --language Chinese

# Keep the previous quiet behavior (warnings still appear):
tradingagents analyze NVDA --no-progress

# JSON stdout plus progress on stderr; plain lines when stderr is a file:
tradingagents analyze NVDA --json --progress > summary.json 2> progress.log
```

## Saved output and automation

Unless overridden, a run creates:

```text
~/.tradingagents/logs/runs/<SYMBOL>_<analysis-date>_<timestamp>_<unique-suffix>/
├── run.json
├── reports/
│   ├── complete_report.md
│   ├── 1_analysts/
│   ├── 2_research/
│   ├── 3_trading/
│   ├── 4_risk/
│   └── 5_portfolio/
└── <SYMBOL>/TradingAgentsStrategy_logs/full_states_log_<analysis-date>.json
```

Only report sections generated by the selected agents are written. The engine's
JSON state and the Markdown exports share the run directory. `run.json` and the
`--json` stdout object have the same summary: symbol, date, asset type, selected
analysts, provider/model names, round counts, decision, `needs_review`, output
directory and complete-report path. They do not dump headers, keys or holdings.

The ordinary persistent decision memory and checkpoint cache keep their existing
configured locations, so successful decisions still inform later ordinary runs
and an interrupted run can resume. The new command uses `propagate()` followed
by `save_reports()` rather than implementing a second agent workflow.

A completed analysis returns exit code **0**. Command-line usage errors return
**2**; configuration, API, graph and file-save failures return **1**, with an
error on stderr and no success JSON. An unparseable decision is still exported
with `decision: "REVIEW"` and `needs_review: true`; automation must check that
field rather than treating exit code 0 alone as a tradable signal.

```bash
tradingagents analyze NVDA --json > summary.json 2> diagnostics.log
```

On failure, partial files may remain in the run directory. An explicit
`--output-dir` must not reuse that nonempty directory; omit the flag or select a
new directory when resuming. The checkpoint is independent of the output path.
Use `tradingagents analyze --help` for the complete CLI reference.
