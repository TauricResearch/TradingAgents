# IIC-FORGE

> An always-on, **local-first investment-intelligence desk** built on the
> [TradingAgents](https://github.com/TauricResearch/TradingAgents) multi-agent
> LLM core. It senses the market 24/7, triages what matters, and — **on your
> approval** — runs an enriched TradingAgents analysis and delivers a brief you
> can act on, refine, or backtest.

IIC-FORGE wraps the TradingAgents research framework (a multi-agent LLM
stock-analysis graph) in a stateful, persistent pipeline coordinated by a
long-lived **Secretary** service. It is decision-support only — it never places
orders.

The authoritative design is the program-level spec,
[`docs/superpowers/specs/2026-05-25-iic-forge-program-design.md`](docs/superpowers/specs/2026-05-25-iic-forge-program-design.md);
per-phase specs and plans live alongside it under
[`docs/superpowers/specs/`](docs/superpowers/specs/) and
[`docs/superpowers/plans/`](docs/superpowers/plans/).

## Three operational modes

The system supports three first-class modes, all writing through the same
Secretary and state store:

- **Event-triggered alerts** — when triage flags a significant event for a
  watchlist instrument, you get a **terse light alert** asking whether to
  commission a full study. The heavy analysis runs **only after you approve**
  (see *The approval gate* below).
- **Morning digest** — a scheduled daily brief over the watchlist.
- **On-demand deep-dive** — you pick a ticker; you get a full research brief
  with risk debate, synchronously.

## Architecture

```
SENSE (F3)            TRIAGE (F3)              ORCHESTRATOR (F4)         SECRETARY (F1)
adapters ─┐                                    promoter polls events     stateful service:
polygon   ├─► redis ─► triage ─► events ─────► salient + watchlist ───►  • composes the
rss       │   stream   dedupe    (sqlite)      + high-confidence            LIGHT alert
gdelt     │            salience                      │                    • one job per
macro     │            ticker-tag                    │ (light alert,        affected ticker
telegram ─┘            watchlist                      │  no study yet)     • on approval →
                       auto-promote                   ▼                      enqueues study
                                          ┌─────────────────────────┐            │
   on-demand CLI ───────────────────────►│  approve? (you decide)  │            ▼
   morning timer ──────────────────────► │  telegram buttons / CLI  │   TradingAgents graph
                                          └────────────┬────────────┘   balanced IIC
                                                       │ approved      persona overlay
                                                       ▼                       ▼
                                          worker leases job ───────►   STATE (SQLite + fs)
                                          runs the full study         runs, briefs, events,
                                                                      watchlist, actions
                                                       │                       │
                       DELIVERY (F5)  ◄────────────────┴───────────────────────┘
                       telegram / email / cli  +  Streamlit dashboard
```

SQLite (`~/.tradingagents/iic.db`, WAL mode) is the system of record; Redis is
only the ingest stream + dedupe fingerprint cache. Long-form analyst reports
live on disk under `data/runs/<run_id>/`, referenced by path from SQLite.

## The approval gate (F4, IIC-FORGE-09)

Event alerts **do not** auto-run the expensive study. The flow is
*light alert → approve → study*, matching the intended design
([`…-09-f4-approval-gate-design.md`](docs/superpowers/specs/2026-06-01-iic-forge-09-f4-approval-gate-design.md)):

1. The **promoter** finds a triaged event that is watchlist-relevant and
   high-confidence, makes **one cheap `quick_think_llm` summary call**, and
   writes an event-scoped `event_alert_light` brief — plus one pending
   `run_full_study` action **per affected ticker**, and a same-day suppression
   so a ticker alerts at most once per day.
2. You **approve per ticker** — Telegram inline buttons
   (`[Study NVDA] … [Study all] [Dismiss all]`) or the CLI:

   ```bash
   tradingagents forge alert list                 # pending light alerts
   tradingagents forge alert approve <brief-id>   # 8-char id from `list`; --ticker to pick one
   tradingagents forge alert dismiss <brief-id>
   ```
3. On approval the **action-handler** enqueues the existing heavy `event_alert`
   job; the **worker** runs the full balanced TradingAgents study and links
   the full brief back to the light one via `parent_brief_id`.

Because studies fire at *your* approval rate, the F4 SLA is **alert latency**
(event → light-alert, p95 ≤ 5 min), not study throughput. The legacy
auto-enqueue path is retained behind `alert_approval_gate_enabled=False`.

## How a study works (the personas)

The default full study runs **one TradingAgents graph** with the enriched
`balanced` IIC persona overlay. That overlay modifies the native TradingAgents
analyst, researcher, trader, and risk roles in-place; it is not a second layer
of outer personas wrapped around the original graph.

After the default full brief, directed follow-ups reuse the persisted
**Analysis Pack** context so a request like "make this more aggressive" can
focus the next run instead of replaying every prompt from scratch.

Committee mode is explicit and opt-in. It runs the `value`, `momentum`, and
`macro` profiles only when the operator asks for comparison, disagreement
analysis, or a committee-style second opinion.

Persona memory is **hybrid**: decision-maker reflections are partitioned per
`(persona_id, component)` (no cross-persona leakage), while a shared
`outcome_log` lets personas learn from each other's *outcomes* via `sqlite-vec`
similarity.

## Component map

| Layer | Module | Role |
|---|---|---|
| Sensing | `tradingagents/sensing/` | 24/7 ingest → dedupe → salience → watchlist |
| Orchestration | `tradingagents/orchestrator/` | promote events → light alert → on approval, lease + run study |
| Analysis | `tradingagents/graph/`, `tradingagents/agents/` | the TradingAgents graph with IIC persona overlays |
| Secretary | `tradingagents/secretary/` | compose light alerts, full briefs, digest, refinement |
| Delivery | `tradingagents/delivery/` | telegram / email / cli channels + bot |
| Dashboard | `tradingagents/dashboard/` | Streamlit ops panel |
| Persistence | `tradingagents/persistence/` | SQLite store + schema (`sqlite-vec`) |

## Phase status

Phases and numbering follow the program design (§7). Each shipped phase has a
measurable exit gate (`scripts/f*_exit_gate.py`) whose report lands in
[`docs/superpowers/artifacts/`](docs/superpowers/artifacts/).

| Phase | Scope | Status |
|---|---|---|
| F0 | Forge the fork — base engine + capabilities | ✅ |
| F1 | Decision core: stateful Secretary, personas, persistence, deep-dive | ✅ |
| F2 | Validation: backtest + benchmark harness | ✅ restored from `origin/feat/iic-forge-05-f2` and wired to accepted backtest actions |
| F3 | Always-on sensing + triage — 24h soak gate **passed** | ✅ |
| F4 | Autonomous trigger loop, reworked into the **approval gate** (IIC-FORGE-09) | ✅ |
| F5 | Delivery + operations (3 channels, scheduler, dashboard, refinement) | ✅ |
| F6 | Geospatial LiveMap (read-only) | ⬜ not started |

> The approval gate fuses the F4 trigger loop with F5 delivery. Use
> `scripts/f4_f5_exit_gate.py` for the combined approval-through-delivery exit
> gate.

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
`forge` is its operational sub-app. Any command also runs as
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
python scripts/f4_f5_exit_gate.py --since 2026-06-03T09:00:00Z --window-hours 12

# Event-alert approval gate
tradingagents forge alert list                 # pending light alerts
tradingagents forge alert approve <brief-id>   # approve (all tickers, or --ticker NVDA)
tradingagents forge alert dismiss <brief-id>
tradingagents forge action-handler run         # consumer: turns approvals into study jobs

# Secretary / delivery
tradingagents forge morning-digest now         # compose + send the digest
tradingagents forge digest tail                # recent digests

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
| `IIC_TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_ALLOWED_CHAT_IDS` | delivery/approval bot token + allowed chat id(s) |
| `TRADINGAGENTS_IIC_DB_PATH` | SQLite path (default `~/.tradingagents/iic.db`) |

Notable tunables in `default_config.py`:

| Key | Default | Meaning |
|---|---|---|
| `alert_approval_gate_enabled` | `True` | light-alert → approve → study (vs. legacy auto-enqueue) |
| `alert_salience_threshold` / `alert_ticker_confidence_threshold` | `0.85` / `0.9` | how selective the alert trigger is |
| `alert_pending_ttl_hours` | `24` | how long a pending approval stays valid |
| cost / rate guards | `enabled=False` | coded but off through F0–F5 (measure first) |

## Operations

- **systemd units** (`ops/systemd/`): one per sensing adapter, plus triage,
  promoter, worker, **action-handler**, dashboard, telegram bot, and the
  morning (06:00) / watchlist timers. A `redis-server.service` docker alias
  satisfies the `Requires=` dependency.
- **Runbooks** (`ops/runbooks/`): per-phase exit-gate procedures (pre-flight,
  run, evaluate).
- **Backups** (`ops/backup.sh`): SQLite `.backup` + Redis AOF snapshot.

Bring up the sensing + orchestration + approval stack:

```bash
sudo cp ops/systemd/*.service ops/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now redis-server.service
sudo systemctl start iic-triage iic-sense-rss iic-sense-polygon iic-sense-gdelt \
                     iic-sense-macro iic-sense-telegram \
                     iic-promoter iic-worker iic-action-handler
# optional, for phone approvals + alert delivery:
sudo systemctl start iic-telegram-bot
```

> The committed units target this deployment (conda interpreter, repo at
> `/home/ziwei-huang/TradingAgents/TradingAgents`, logs to journal). Adjust
> `User=`, `WorkingDirectory=`, and the interpreter path for another host.

## Design decisions

- **Stateful Secretary from F1** — not a passive post-processor. It owns run
  intent, suppression, watchlist TTLs, and brief composition; persistence
  arrives at F1, not later.
- **SQLite as the system of record** — one WAL-mode file written by sensing,
  orchestrator, and secretary concurrently (`busy_timeout` for contention);
  full schema (incl. F2–F5 tables) defined upfront so later phases add tables,
  never reshape them.
- **The operator is in the loop** — event alerts are *light* and require
  explicit approval before any expensive analysis; refinement re-runs analysis
  with the operator's overrides; backtests and refinements are **never**
  auto-triggered.
- **Default analysis is one balanced graph** — IIC enriches the native
  TradingAgents roles in-place. Committee mode is explicit and reserved for
  comparison or disagreement analysis.
- **Disagreement is signal** — synthesis renders Consensus / Divergence /
  Recommendation; the divergence section is never averaged away.
- **Cost guards ship disabled** — rate/budget guards are coded but
  `enabled=False` through F0–F5: measure first, enforce later.
- **Everything is resumable** — sensing cursors, orchestrator job leases, and
  idempotent writes let any unit restart without duplicate work; the worker
  honors stop signals promptly mid-job.
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
Tauric Research. The multi-agent analysis graph (`tradingagents/agents/`,
`tradingagents/graph/`) is theirs; IIC-FORGE adds the sensing, orchestration,
secretary, delivery, and operations layers around it.

### Citation

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138},
}
```

## License

See [LICENSE](LICENSE). The upstream TradingAgents framework retains its own
license terms.
