# TradingAgents GUI

A Streamlit dashboard for the TradingAgents framework. Run analyses, watch
the agents stream their output live, browse history, and keep notes.

## Install

The GUI lives in this repo as an optional extra. From the repo root:

```bash
pip install '.[gui]'
```

Or, equivalently:

```bash
pip install -e .         # the framework itself
pip install streamlit    # the GUI runtime
```

## Launch

```bash
tradingagents-gui        # console script (after `pip install`)
# or:
streamlit run gui/app.py
```

Streamlit prints a local URL (default http://localhost:8501) and opens
your browser. Use `--server.port 8502` etc. to change the port.

## Pages

- **Home** — overview, recent runs, and where files live
- **Run** — pick ticker / date / provider / model / vendors and run an
  analysis. The page streams live: each section's tab fills as that
  agent finishes, with running token + tool-call counts. You can cancel
  a run mid-stream; you can attach a note to the run from the same page.
- **History** — every analysis ever recorded, whether launched from the
  GUI or the CLI. The on-disk JSON state logs are the source of truth
  for transcripts; SQLite holds metadata (provider, models, tokens,
  decision). Click a run to re-open the full debate transcript.
- **Notes** — markdown notes, optionally pinned to a ticker or a run.
  Searchable.
- **Memory** — the rolling decision log (`~/.tradingagents/memory/trading_memory.md`)
  rendered with pending vs resolved entries. Pending entries fill in
  with a realised-return reflection on the next same-ticker run.
- **Settings** — API keys per provider and default run config. Keys
  present in your shell environment / `.env` always win and show as
  read-only here; otherwise keys are stored in
  `~/.tradingagents/gui_config.json` (chmod 0600).

## Architecture

```
gui/
  app.py             Streamlit entry (home page)
  launcher.py        tradingagents-gui console script
  config.py          Load/save gui_config.json (API keys + defaults)
  storage.py         SQLite layer for runs and notes
  runner.py          Subprocess manager (main process side)
  runner_worker.py   Worker subprocess that runs propagate()
  log_browser.py     Read on-disk run logs and the memory log
  pages/
    1_Run.py
    2_History.py
    3_Notes.py
    4_Memory.py
    5_Settings.py
```

### Why a subprocess?

Each analysis runs in a separate Python process so a crash in LangGraph
or a model client kills the worker, not the whole GUI. The worker writes
NDJSON events to stdout (one JSON object per line); the main process has
a reader thread that parses them into a queue, which Streamlit drains
each refresh.

### Where data lives

| Path | Contents |
|---|---|
| `~/.tradingagents/gui_config.json` | API keys + GUI defaults (chmod 0600) |
| `~/.tradingagents/gui.db` | SQLite — runs, notes |
| `~/.tradingagents/logs/<TICKER>/.../full_states_log_<DATE>.json` | Full debate transcript per run |
| `~/.tradingagents/memory/trading_memory.md` | Rolling decision log |
| `~/.tradingagents/cache/` | Cached price/news data + LangGraph checkpoints |

Override any path with the corresponding env var:
`TRADINGAGENTS_RESULTS_DIR`, `TRADINGAGENTS_CACHE_DIR`,
`TRADINGAGENTS_MEMORY_LOG_PATH`.

## Notes

- Default model names in the framework (`gpt-5.4`, `gpt-5.4-mini`) are
  placeholders. Set real model identifiers on the Settings page —
  e.g. `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4-5`, `gemini-2.5-flash`.
- Closing your browser tab won't kill an in-flight analysis; reopen
  the page and it'll still be running. Closing the Streamlit server
  (Ctrl+C) will leave any in-flight worker subprocesses orphaned —
  the OS reaps them when the parent exits.
- The framework's CLI (`tradingagents`) and the GUI share the same
  on-disk state, so runs from one show up in the other.
