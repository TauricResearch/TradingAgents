# IIC-FORGE

> An always-on **autonomous investment-intelligence desk**, built on the
> [TradingAgents](https://github.com/TauricResearch/TradingAgents) multi-agent
> LLM core. It senses the market 24/7, decides what is worth a deep look, runs
> the multi-persona analysis automatically, and delivers briefs you can act on,
> refine, or backtest — straight from the brief.

IIC-FORGE wraps the TradingAgents research framework (a multi-agent LLM
stock-analysis graph) in a production pipeline: ingest → triage → promote →
analyze → compose → deliver. The full architecture is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
   sensing (F3)         orchestration (F4)       secretary + delivery (F5)
   ───────────          ──────────────────       ─────────────────────────
   adapters ─┐                                      ┌─ morning digest
   polygon   ├─► triage ─► events ─► promoter ─►    │  event alerts ─► telegram
   rss       │   dedupe    (sqlite)   (queue)       │  refinement      email
   gdelt     │   salience             ▲             │                  cli
   macro     │   ticker-tag           │ worker      └─ dashboard
   telegram ─┘   watchlist            │ (personas)
                  auto-promote         └─ briefs ◄─ TradingAgents graph (F1)
```

## How it works

1. **Sense** — source adapters (`tradingagents/sensing/adapters/`) poll/stream
   external feeds (Polygon news, RSS, GDELT, FRED macro, Telegram channels) and
   `XADD` normalized envelopes onto a Redis stream.
2. **Triage** — `sensing/triage.py` consumes the stream: two-stage dedupe
   (exact fingerprint + semantic via `sqlite-vec`), scores **salience** with an
   LLM, tags tickers, writes `events`, and **auto-promotes** high-salience
   watchlist tickers.
3. **Promote** — `orchestrator/promoter.py` polls `events` for salient,
   watchlist-relevant rows and enqueues `queue_jobs` (with per-ticker cooldown).
4. **Work** — `orchestrator/worker.py` leases one job at a time and runs the
   multi-persona TradingAgents graph; a per-persona failure degrades the brief
   rather than failing the job.
5. **Compose** — `secretary/` turns runs into **event-alert briefs**, the
   **morning digest**, and **refinement** replies (the operator can re-run
   analysis with overrides, depth-capped).
6. **Deliver** — `delivery/` renders and sends via Telegram / email / CLI; the
   Streamlit **dashboard** exposes the same state visually.

SQLite (`~/.tradingagents/iic.db`, WAL mode) is the system of record; Redis is
only the ingest stream + dedupe fingerprint cache.

## Component map

| Layer | Module | Role |
|---|---|---|
| Sensing | `tradingagents/sensing/` | 24/7 ingest → dedupe → salience → watchlist |
| Orchestration | `tradingagents/orchestrator/` | promote salient events → lease jobs → run personas |
| Analysis | `tradingagents/graph/`, `tradingagents/agents/` | the TradingAgents multi-persona deep-dive |
| Secretary | `tradingagents/secretary/` | compose digests, event alerts, refinement |
| Delivery | `tradingagents/delivery/` | telegram / email / cli channels + bot |
| Dashboard | `tradingagents/dashboard/` | Streamlit ops panel |
| Persistence | `tradingagents/persistence/` | SQLite store + schema |
| Backtest | `tradingagents/backtest/` | validation harness (F6, in progress) |

## Phase status

| Phase | Scope | Status |
|---|---|---|
| F0 | repo/init, model clients, capabilities | ✅ |
| F1 | deep-dive quality baseline (personas, structured output) | ✅ |
| F2 | data vendors (polygon, futu, osint, options) | ✅ |
| F3 | sensing layer (adapters, triage, watchlist) — 24h soak gate **passed** | ✅ |
| F4 | orchestrator (promoter, worker, queue) | ✅ |
| F5 | secretary, delivery, dashboard, refinement | ✅ |
| F6 | backtest validation | ⏳ in progress |

Phase specs live under [`docs/superpowers/specs/`](docs/superpowers/specs/);
each phase has a measurable exit gate (`scripts/f*_exit_gate.py`) whose report
is written to `docs/superpowers/artifacts/`.

## Quickstart

Requires Python ≥ 3.10 and a running Redis (a Docker container is fine).

```bash
# 1. Install (editable)
pip install -e .
# optional vendor/sensing extras:
pip install -e ".[sensing,polygon,osint]"

# 2. Configure — copy the example and fill in keys
cp .env.example .env      # then edit .env (see Configuration below)

# 3. Redis (e.g. the iic-redis container)
docker run -d --name iic-redis -p 6379:6379 -v /srv/iic/redis:/data \
  redis:7-alpine redis-server --appendonly yes

# 4. Seed the ticker reference table (~12k US equities + crypto)
tradingagents forge sense reseed-tickers

# 5. One-off deep-dive (no daemons needed)
tradingagents deepdive AAPL
```

The console script `tradingagents` (= `cli.main:app`) is the entry point;
`forge` is its operational sub-app. You can also run any command with
`python -m cli.main forge ...`.

## Common commands

```bash
# Watchlist (the promotion gate)
tradingagents forge watchlist add NVDA
tradingagents forge watchlist list

# Sensing ops
tradingagents forge sense reseed-tickers       # populate `tickers`
tradingagents forge sense sweep-watchlist      # TTL prune

# Orchestrator
tradingagents forge orchestrator status        # queue + recent jobs

# Secretary / delivery
tradingagents forge morning-digest now         # compose + send the digest
tradingagents forge digest tail                # recent digests
tradingagents forge action-handler run         # brief_actions consumer loop

# Dashboard
streamlit run tradingagents/dashboard/app.py --server.port=8501 --server.address=127.0.0.1
```

## Configuration

Config lives in `tradingagents/default_config.py` and is env-overridable;
secrets go in `.env` (never committed). Key variables:

| Variable | Purpose |
|---|---|
| `DEEPSEEK_API_KEY` (or `OPENAI_`/`ANTHROPIC_`/`GOOGLE_API_KEY`) | LLM provider (default `llm_provider=deepseek`) |
| `POLYGON_API_KEY` | Polygon news adapter + ticker seed |
| `FRED_API_KEY` | macro adapter (FRED releases) |
| `RSS_FEEDS` | comma-separated RSS feed URLs |
| `GDELT_QUERY` | GDELT DOC query — **must** wrap OR-lists in `()` and avoid `&` (e.g. `'(earnings OR "Federal Reserve" OR stocks)'`) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SENSING_SESSION` | Telegram sensing adapter |
| `TELEGRAM_SENSING_CHANNELS` | comma-separated channel usernames to ingest (the session account must **join** them) |
| `TELEGRAM_BOT_ALLOWED_CHAT_IDS` | numeric chat id(s) the delivery bot accepts |
| `TRADINGAGENTS_IIC_DB_PATH` | SQLite path (default `~/.tradingagents/iic.db`) |

## Operations

- **systemd units** (`ops/systemd/`): one per sensing adapter, plus triage,
  promoter, worker, dashboard, telegram bot, and the morning/watchlist timers.
  A `redis-server.service` docker alias satisfies the `Requires=` dependency.
- **Runbooks** (`ops/runbooks/`): per-phase exit-gate procedures (pre-flight,
  run, evaluate).
- **Backups** (`ops/backup.sh`): SQLite `.backup` + Redis AOF snapshot.

Bring up the sensing + orchestration stack:

```bash
sudo cp ops/systemd/*.service ops/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now redis-server.service
sudo systemctl start iic-triage iic-sense-rss iic-sense-polygon iic-sense-gdelt \
                     iic-sense-macro iic-sense-telegram iic-promoter iic-worker
```

> The committed units target this deployment (conda interpreter, repo at
> `/home/ziwei-huang/TradingAgents/TradingAgents`, logs to journal). Adjust
> `User=`, `WorkingDirectory=`, and the interpreter path for another host.

## Design decisions

- **SQLite as the system of record** — one WAL-mode file written by sensing,
  orchestrator, and secretary concurrently (`busy_timeout` set for contention).
- **Cost guards ship disabled** — rate/budget guards are coded but
  `enabled=False` through F0–F5: measure first, enforce later.
- **Everything is resumable** — sensing cursors, orchestrator job leases, and
  idempotent writes let any unit restart without duplicate work.
- **The operator is in the loop** — briefs carry actions (backtest, refine,
  dismiss); refinement re-runs analysis with the operator's overrides.
- **Prompt-cache aware** — LLM prompts keep a byte-stable instruction prefix
  (variable context at the tail) to maximize DeepSeek prefix-cache reuse; token
  usage and cache hit/miss are recorded to the `costs` table.

## Testing

```bash
python -m pytest tests -q            # full suite
python -m pytest tests/sensing -q    # one subsystem
```

Note: an autouse fixture injects placeholder API keys, so integration tests
that need real keys must `load_dotenv(override=True)` inside the test body.

## Built on TradingAgents

IIC-FORGE is a downstream application of the
[TradingAgents](https://github.com/TauricResearch/TradingAgents) framework by
Tauric Research. The multi-persona analysis graph (`tradingagents/agents/`,
`tradingagents/graph/`) is theirs; IIC-FORGE adds the sensing, orchestration,
secretary, delivery, and operations layers around it.

### Citation

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Yiqiao Jin and Yushi Bai and Yue Zhao and Yizhou Sun and Tao Lin},
      archivePrefix={arXiv},
      eprint={2412.20138},
      primaryClass={q-fin.TR}
}
```

## License

See [LICENSE](LICENSE).
