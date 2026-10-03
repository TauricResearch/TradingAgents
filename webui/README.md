# `webui` — the browser front end

For setting it up and using it, see [SETUP.md](../SETUP.md). This describes how
it is built, for anyone changing it.

## What it is not

It is not a second implementation of the pipeline. `runs.py` drives
`TradingAgentsGraph` the way `cli/run.py` does — same initial state, same
stream, same decision recording, same report tree — and turns the stream into
events a browser can read. A change to the graph reaches the UI without the UI
being touched; a feature that belongs in the pipeline does not belong here.

The two things that genuinely are new: a portfolio that outlives a single run,
and a reader for broker CSV exports.

## Layout

| File | Holds |
|---|---|
| `server.py` | the HTTP surface: routes, request models, SSE |
| `runs.py` | the queue, the worker, and one run's event log |
| `store.py` | the saved portfolio, read and written as `--portfolio` JSON |
| `importers.py` | broker positions CSV → `PortfolioContext` |
| `paths.py` | writing a path the way it should be read on screen |
| `serve.py` | launching uvicorn, shared by `python -m webui` and `tradingagents ui` |
| `static/` | one page, no framework and no build step |

No build step is deliberate: the front end is three files served from the
package, so `pip install` is the whole install and there is no toolchain to
keep working.

## Design decisions worth knowing

**One worker, not a pool.** Runs execute strictly one at a time. The book view
exists to queue a run per holding, and running those in parallel would multiply
provider spend per minute and collide with rate limits. The queue is visible in
the UI instead of hidden behind concurrency.

**Every event is retained per run.** A subscriber gets the whole backlog and
then the live stream, taken together under one lock so an event in between can
be neither missed nor delivered twice. This is what makes a reload during a
ten-minute analysis survivable; it also means a run's memory grows with its
transcript, which is why finished runs are evicted past `max_runs`.

**Three portfolio states, preserved end to end.** No book, a flat book, and a
book with positions are distinct all the way from the HTTP layer to the agent
prompt. `portfolio: null` is not an empty position list. Collapsing them would
invent a fact about someone's account.

**An import previews, it does not save.** A parse that misreads a column would
otherwise overwrite a book entered by hand. `POST /api/portfolio/import` returns
the parsed book; `?save=true` commits it, and only the UI's explicit save does
that.

**The server is local-first.** Loopback, no auth. It holds a broker export and
spends provider keys. Binding elsewhere warns rather than refuses, because a
container has to.

**Run history is in memory.** It starts empty after a restart. What persists is
what a CLI run persists: the report tree and the memory log. This is a real
limitation, documented rather than hidden — a durable run index would mean
owning a schema and its migrations.

## HTTP API

Everything is under `/api`; `/api/docs` serves the generated reference.

| Method | Path | Does |
|---|---|---|
| `GET` | `/api/config` | providers, their models, analysts, report sections, defaults |
| `GET` | `/api/analysts?ticker=` | the analysts that ticker's asset type supports |
| `GET` | `/api/portfolio` | the saved book, or `null` |
| `PUT` | `/api/portfolio` | save a book |
| `DELETE` | `/api/portfolio` | delete it; runs go back to no portfolio context |
| `POST` | `/api/portfolio/import` | parse a CSV body; `?save=true` to commit |
| `GET` | `/api/runs` | every run this process has executed, newest first |
| `POST` | `/api/runs` | queue one |
| `POST` | `/api/runs/book` | queue one per holding, as a batch |
| `GET` | `/api/runs/{id}` | one run with its reports and transcript |
| `POST` | `/api/runs/{id}/cancel` | stop it; queued stops now, running at its next step |
| `GET` | `/api/runs/{id}/events` | SSE, replayed from the run's first event |
| `GET` | `/api/history` | past decisions from the memory log, with outcomes |

The import endpoint takes the CSV as a raw request body rather than a multipart
upload, which keeps `python-multipart` out of the dependency list.

### Event kinds

Each SSE frame is one JSON object with `seq`, `kind`, `at`, and a payload.

| `kind` | Payload | Meaning |
|---|---|---|
| `status` | `status`, and `rating`/`error` when it ends | the run changed state |
| `message` | `type`, `content` | an agent message or a tool call |
| `report` | `key`, `content` | a section was filed or revised |
| `agent` | `agent`, `state` | an agent finished |
| `stats` | `stats` | LLM calls and token counts so far |

`stats` is emitted at most once a second and only between graph steps, so it
stands still while a slow step is in flight and catches up afterwards.

## Adding things

**A report panel.** Add it to `REPORT_SECTIONS` if it is a state field, or
`DERIVED_SECTIONS` if it lives inside a nested one, then place it in
`DISPLAY_ORDER`. The front end reads the order and labels from `/api/config`;
nothing in `app.js` needs to know.

**A broker.** `importers.py` looks columns up through synonym tables rather than
by position. Most formats need a new name in `_SYMBOL_COLUMNS` and friends, not
new code. Add a fixture to `tests/test_webui_importers.py` with the broker's
real preamble and footer — those are what break parsers, not the columns.

**An LLM provider.** Not here. One `ProviderSpec` row in
`tradingagents/llm_clients/openai_client.py` plus a key in `api_key_env.py`, and
the UI picks it up from `/api/config` automatically. `digitalocean` is the
worked example.

## If `tradingagents ui` says `No module named 'webui'`

An editable install records the packages that existed when it was made, and
`webui` is new in this branch. A checkout installed with `pip install -e .`
beforehand will not see it. Reinstall:

```bash
pip install -e ".[webui]"
```

A normal (non-editable) install is unaffected; the wheel carries `webui` and
`webui/static` through `packages.find` and `package-data`.

## Tests

```bash
pytest tests/test_webui_server.py tests/test_webui_importers.py
```

The server tests stub `RunManager._execute`, because the worker is a daemon
thread that outlives the test: the suite's network block is a monkeypatch undone
at teardown, so a run that starts late would otherwise reach the real internet.
Replacing the execution is what keeps the suite offline.

To exercise the real graph without a provider key, point the `openai_compatible`
provider at a local server that answers chat completions with canned prose:

```bash
TRADINGAGENTS_LLM_PROVIDER=openai_compatible \
TRADINGAGENTS_LLM_BACKEND_URL=http://localhost:8799/v1 \
TRADINGAGENTS_DEEP_THINK_LLM=mock TRADINGAGENTS_QUICK_THINK_LLM=mock \
tradingagents ui
```

Every agent falls back to free text when a structured call returns nothing,
which is a supported path, so the whole pipeline runs and the UI streams a real
run for nothing.
