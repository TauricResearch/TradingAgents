# IIC-FORGE-03 — Program-Level Integration Design (F1–F6)

| Field | Value |
|---|---|
| **Track** | IIC-FORGE |
| **Document** | 03 |
| **Scope** | Program-level integration design covering F1–F6 at one level deeper than the roadmap |
| **Base engine** | TauricResearch/TradingAgents v0.2.5 (forked, F0 customizations complete) |
| **Owner** | Ziwei |
| **Date** | 2026-05-25 |
| **Status** | Ready for review |
| **Supersedes** | IIC-FORGE-01 ADR-F4 (state/persistence) |
| **Amends** | IIC-FORGE-02 §A.9e (mandatory derivatives) |
| **Relates to** | IIC-FORGE-01 (roadmap), IIC-FORGE-02 (F0 implementation, complete) |
| **Companion plans (future)** | IIC-FORGE-04 (F1 implementation spec), IIC-FORGE-05 (F2 implementation spec), … |

## Quick links

- §1 Executive summary
- §2 Anchoring decisions
- §3 Overall architecture
- §4 Secretary internals
- §5 Personas
- §6 State schema
- §7 Per-phase plan and exit gates
- §8 Risks and open questions
- §9 Out of scope
- §10 ADR amendments
- Appendix A — Cost guard policy
- Appendix B — Reuse from prior IIC work

---

## 1 · Executive summary

This document sharpens IIC-FORGE-01 (roadmap) one level deeper by integrating phases F1 through F6 into one coherent architecture. It is a **program-level** design, not a per-phase implementation spec. Per-phase specs (IIC-FORGE-04 onward) follow when each phase is up next.

The design is anchored on three decisions made during the brainstorming session that produced this doc:

1. **All three operational modes are first-class** — morning brief on a watchlist, event-triggered alerts, and on-demand deep-dive. The secretary writes three brief formats; the orchestrator handles three trigger types; delivery supports three cadences.
2. **The secretary is a stateful orchestrator from F1** — not a passive post-processor. It owns run intent, suppression, watchlist TTLs, and brief composition. Consequence: persistence (SQLite) arrives at F1, not F3.
3. **Personas are rich config overlays** — system-prompt fragment + LLM tier + analyst include/exclude + risk-debate weights. Three starter personas: macro, value, momentum.

Three changes to the existing plan follow directly:

- **ADR-F4 is rewritten.** SQLite + filesystem hybrid + `sqlite-vec` arrives in F1. Schemas for F3/F4/F5 tables are defined at F1 to avoid migration churn (§6).
- **IIC-FORGE-02 §A.9e is reverted.** Derivatives becomes an optional analyst; personas opt-in. The line in `tradingagents/graph/trading_graph.py` that forces `"derivatives"` into `selected_analysts` is removed (§5).
- **F4 shrinks.** The orchestrator becomes a thin queue + worker behind the secretary, since the secretary already owns scheduling and run intent. F4 also codes cost guards and throttles but ships them `enabled=False` (Appendix A).

The end-state is unchanged in spirit: a 24/7 local-first multi-agent investment decision support system. What changes is the **integration shape** — what F1 must contain to make F2–F6 ship cleanly without re-architecture.

## 2 · Anchoring decisions

### D1 — All three operational modes are first-class

The system must support, equally well:

- **Morning brief on a watchlist** — scheduled digest covering ~10–30 tickers. Single delivery moment per day.
- **Event-triggered alerts** — terse Telegram-style alerts when triage detects a significant event for a watchlist instrument.
- **On-demand deep-dive** — user picks a ticker or theme, gets a multi-persona brief with risk debate.

Implication: the secretary writes three brief formats; F4 handles three trigger types; F5 supports three delivery cadences. Cost grows accordingly — Appendix A explains why this is acceptable for now.

### D2 — Stateful secretary from F1

The secretary maintains state across runs: what it briefed, what to suppress, watchlist TTLs, scheduled follow-ups. It is the system's coordinator, not a passive synthesis step.

Implications:
- Persistence (SQLite) arrives at F1, not F3 (ADR-F4 rewritten).
- F4 becomes thinner — queue + worker only.
- Schema design at F1 is contract-bearing for F2/F3/F5/F6 (§6).

### D3 — Rich-overlay personas

Each persona is a YAML config with: system-prompt fragment, deep/quick LLM choice + `reasoning_effort`, `analysts.include/exclude`, and `risk_debate.weights`. Macro, value, momentum are the three starter personas. Personas are meaningfully different — not three voices saying similar things.

Implications:
- IIC-FORGE-02 §A.9e (mandatory derivatives) is reverted — momentum and value personas may legitimately drop derivatives.
- Memory partitions per-persona for decision-maker components; shared `outcome_log` (§5).

## 3 · Overall architecture

```
SENSE (F3)               TRIAGE (F3)             ORCHESTRATOR (F4)
RSS, OSINT,    ──────►   Intelligence Analyst ─► Queue + worker +
filings,                 (salience, event→        cost guard
Polygon news             instrument, watchlist    (enabled=False)
streams)                 update)                          │
                                                          ▼
                                              ┌──────────────────────┐
                                              │  SECRETARY (F1)      │  ← stateful service
                                              │  - picks runs        │
   on-demand CLI ─────────────────────────►   │  - launches per      │
   morning scheduler ─────────────────────►   │    persona × ticker  │
                                              │  - reads results     │
                                              │  - dedup / suppress  │
                                              │  - writes briefs     │
                                              └──────────┬───────────┘
                                                         ▼
                                              TradingAgents engine
                                              (per-run LangGraph)
                                              × N personas in parallel
                                                         │
                                                         ▼
                                              ┌──────────────────────┐
                                              │ STATE (SQLite, F1)   │  ← central seam
                                              │ runs, briefs, events,│
                                              │ watchlist, supp.     │
                                              └──────────┬───────────┘
                                                         ▼
              DELIVERY (F5)   ──────────  Telegram / Email / CLI
              BACKTEST (F2)   ──────────  reads runs + briefs from STATE
              LIVEMAP (F6)    ──────────  reads events + briefs from STATE
```

### Three load-bearing changes vs. IIC-FORGE-01

1. **State arrives at F1.** A stateful secretary needs persistent storage on day one. SQLite + schemas land in F1; F3 only adds new tables (events, watchlist) to the existing store (ADR-F4 rewritten, §10).
2. **Secretary is the central coordinator.** F4's orchestrator becomes a thin queue + worker the secretary submits work to. The secretary owns "what to run, when, against which persona, at what priority."
3. **Persistence is the integration seam.** Backtest (F2), delivery (F5), and LiveMap (F6) all read from the same SQLite + filesystem store. Schema design at F1 is contract-bearing.

## 4 · Secretary internals

### Responsibilities

1. **Decide what to run** — given a trigger (event / schedule / on-demand), pick `ticker × persona × priority`, check suppression.
2. **Launch runs** — direct invocation in F1; queue submission in F4.
3. **Track state** — runs, briefings sent, suppression windows, watchlist TTLs.
4. **Read results** — pull normalized persona reports from STATE.
5. **Compose briefs** — multi-persona reports → one synthesized brief in the mode's format.
6. **Hand off to delivery** — write `briefs` row, signal F5 channel.
7. **Handle post-delivery actions** — after each brief is delivered, two follow-up paths are available: (a) **structured action prompts** (V1: "run backtest on these strategies") — launched only on affirmative reply; (b) **free-text refinement requests** on the same channel — classified into parameter overrides (persona weights, horizon, analyst selection, risk tilt) and applied by launching new persona runs that produce a refined brief threaded to the original via `briefs.parent_brief_id`. No response or empty input → no action. Drill-down and scenario / what-if are out of scope for V1.

### Architecture: hybrid — graph node + service

A LangGraph node alone cannot aggregate across persona runs (the graph runs per ticker × persona). The secretary is split into two pieces:

- **Inside each graph run: a "Run Recorder" final node.** Sits after the Portfolio Manager. Normalizes the run's outputs (final decision, per-analyst reports, risk-debate transcript, costs, persona id) into SQLite + filesystem. Makes every graph run idempotently produce a persisted record. Boundary smoke test asserts this fires for every run.
- **Outside the graph: a long-lived Secretary service.** A Python module that owns the DB and has three entry points:
  - `compose_morning_digest(watchlist, ts) -> brief_id`
  - `compose_event_alert(event_id) -> brief_id`
  - `compose_deep_dive(ticker, personas) -> brief_id`

Each method writes one `briefs` row and enqueues a delivery job for F5.

### Brief composition — preserve disagreement

Persona disagreement is **signal, not noise**. The secretary's synthesis prompt produces three structured sections:

1. **Consensus** — what all personas agreed on (the strongest signal).
2. **Divergence** — explicit list: "macro says X, momentum says Y, here is why."
3. **Recommendation** — buy / hold / sell + confidence, OR an explicit "low-confidence call" if disagreement is material.

Three Jinja templates (one per mode) render this:

- **Morning digest** — multi-ticker, multi-persona, table-of-contents + per-ticker section with consensus / divergence / recommendation.
- **Event alert** — terse, one ticker, the event, the decision shift, action items, links to full reports.
- **Deep-dive** — single ticker, all persona reports side-by-side, then synthesis section.

### What the secretary does NOT do (kept simple in F1)

| Concern | Where it lives |
|---|---|
| Per-run token budget enforcement | F4 queue layer (coded, `enabled=False`) |
| Trigger-loop backpressure | F4 queue layer (coded, `enabled=False`) |
| Quiet hours / digest modes | F5 delivery layer |
| Scheduling beyond cron | F5 |
| Post-delivery prompt rendering | F5 delivery layer (secretary owns the response/decision, not the UI) |

## 5 · Personas

### Schema (one YAML per persona)

```yaml
# tradingagents/personas/macro.yaml
id: macro
name: Macro
description: Top-down view. Rates, policy, geopolitics, credit cycles drive everything.
system_prompt_fragment: |
  You think top-down. Stretch your time horizon — quarters, not days.
  Micro fundamentals are secondary signal.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [market, news, fundamentals]
  exclude: [social, derivatives]
risk_debate:
  weights:            # multipliers applied at PM synthesis
    aggressive: 0.5
    conservative: 1.5
    neutral: 1.0
memory_scope: hybrid    # decision-makers isolated; outcome_log shared (§6)
```

### Starter personas (V1)

| Persona | Analysts | Risk lean | Horizon |
|---|---|---|---|
| **macro** | market + news + fundamentals | conservative-heavy | quarters |
| **value** | fundamentals + news | conservative-heavy | quarters / years |
| **momentum** | market + social + derivatives | aggressive-heavy | days / weeks |

### Mandatory-derivatives amendment

IIC-FORGE-02 §A.9e made `derivatives` mandatory regardless of `selected_analysts`. This is **reverted**. Specifically, the lines added in `tradingagents/graph/trading_graph.py:78` are removed:

```python
# REMOVE these lines:
if "derivatives" not in selected_analysts:
    selected_analysts = list(selected_analysts) + ["derivatives"]
```

Rationale: with personas in play, `analysts.include/exclude` from the persona YAML is authoritative. A momentum persona has no business reading options chains; a macro persona doesn't either. Derivatives becomes selectable, like the other analysts. The default `selected_analysts` list (when no persona is active) still includes derivatives — that's a CLI/config default, not an enforcement rule.

### Output combination across personas

The secretary preserves disagreement (§4). Per-mode rendering:

- **Deep-dive** — full per-persona content + synthesis section.
- **Morning digest** — per-ticker section summarizes personas + a brief consensus / divergence note.
- **Event alert** — secretary's recommendation with a one-liner about which personas drove it.

### Memory scope: hybrid

TradingAgents' reflection memory is per-component (`bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`). The hybrid scheme:

- **Per-persona partitions** for the decision-maker components (bull / bear / trader / research manager / risk manager) — keyed by `(persona_id, component)`. Each persona's reflection accumulates separately.
- **Shared `outcome_log`** — every run writes one outcome row when its decision can be scored (reflection loop, §7 F2). Any persona's reflection can query `outcome_log` via `sqlite-vec` similarity. This is the cross-pollination channel — personas learn from each other's *outcomes* but not from each other's *reasoning*.

A thin Python wrapper enforces the `(persona_id, component)` key so cross-persona memory leakage is structurally impossible. Boundary test asserts this.

## 6 · State schema (SQLite + filesystem)

### Storage choice rationale (revised ADR-F4)

ADR-F4 originally deferred a DB to F3. Now: SQLite + filesystem hybrid + `sqlite-vec` arrives in F1. Alternatives considered:

| Option considered | Why not |
|---|---|
| SQLite only (TEXT columns for reports) | Bloats DB with multi-KB rows; weak vs. `grep`; awkward for future blobs |
| Postgres + JSONB + pgvector | Heavier ops, contradicts P5 (local-first, low ops); kept as a contingency only |
| DuckDB embedded | Strong for analytical scans (F2), weak for the small-OLTP shape of the secretary's frequent queries; kept as an F2 escape hatch via Parquet exports |
| Specialized vector store (Chroma / Qdrant) + SQLite | Two services to operate; `sqlite-vec` is sufficient for F1–F3 |

**Chosen:** SQLite (structured + small text) + filesystem (markdown reports + future blobs) + `sqlite-vec` (embeddings).

Upgrade triggers (documented, not pre-emptive):
- RAG over historical briefs strains `sqlite-vec` → add Qdrant.
- F3 event volume >10K/day strains SQLite → DuckDB or Timescale.
- Multi-machine / cloud deployment ever → Postgres + S3-equivalent.

### Filesystem layout

```
data/
├── runs/<run_id>/
│   ├── meta.json                       # persona, ticker, ts, decision summary
│   ├── analysts/
│   │   ├── market.md
│   │   ├── news.md
│   │   ├── sentiment.md
│   │   ├── fundamentals.md
│   │   └── derivatives.md              # only if persona included it
│   ├── risk_debate.md
│   ├── trader_plan.md
│   └── pm_synthesis.md
├── briefs/<brief_id>.md
├── events/<event_id>.json              # F3 onward
└── vectors/                            # sqlite-vec lives in DB; this is for cached blobs only
```

Long-form markdown lives on disk because: grep-friendly, rsync-friendly, matches TradingAgents' existing `full_states_log_*.json` and decision-log markdown habit. SQLite stores paths + small excerpts + indexed metadata.

### SQLite tables (core relationships)

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   runs       │ ◄──┐    │   briefs     │         │   events     │
│ run_id PK    │    │    │ brief_id PK  │         │ event_id PK  │
│ ticker       │    └────┤ mode         │         │ source       │
│ persona_id   │         │ scope (ticker│◄─trig.──┤ ingested_ts  │
│ started_ts   │         │   or list)   │         │ salience     │
│ ended_ts     │         │ generated_ts │         │ raw_path     │
│ status       │         │ content_path │         │ deduped_of   │
│ decision     │         │ run_ids JSON │         │ status       │
│ confidence   │         │ delivery_ids │         └──────┬───────┘
│ trigger_id   │────────►│  JSON        │                │
│ artifact_dir │         └──────────────┘                ▼
└──────┬───────┘                                  ┌──────────────┐
       │                                          │event_ticker  │
       ▼                                          │ event_id FK  │
┌──────────────┐                                  │ ticker       │
│   costs      │                                  │ confidence   │
│ run_id FK    │                                  └──────────────┘
│ provider     │
│ model        │         ┌──────────────┐         ┌──────────────┐
│ in_tokens    │         │   watchlist  │         │ suppression  │
│ out_tokens   │         │ ticker PK    │         │ key PK       │
│ usd_estimate │         │ added_ts     │         │ until_ts     │
└──────────────┘         │ last_briefed │         │ reason       │
                         │ ttl_until    │         │ created_by   │
┌──────────────┐         │ tags JSON    │         └──────────────┘
│   memories   │         └──────────────┘
│ persona_id   │ ◄── isolated by (persona_id, component)
│ component    │
│ situation_md │         ┌──────────────┐
│ outcome      │         │ outcome_log  │ ◄── shared across personas
│ vec_id       │         │ run_id FK    │
└──────────────┘         │ ticker       │
                         │ decision     │
┌──────────────┐         │ outcome_md   │
│ vec_index    │         │ pnl_proxy    │
│ (sqlite-vec) │         │ vec_id       │
│ vec_id PK    │ ◄───────┤ tags JSON    │
│ embedding    │         └──────────────┘
└──────────────┘
```

Load-bearing details:

- **`runs.artifact_dir`** points to `data/runs/<run_id>/`. The DB never stores reports >100 KB inline.
- **`briefs.scope`** is either a single ticker (event / deep-dive) or a JSON list (morning digest).
- **`runs.trigger_id`** is nullable — populated for event-triggered runs only.
- **`memories`** is partitioned by `(persona_id, component)` — the wrapper class enforces this.
- **`outcome_log`** is the shared cross-persona pool — every run that can be scored writes one row.
- **`vec_index`** is one `sqlite-vec` virtual table; `vec_id` is a foreign key from `memories` or `outcome_log`. Single embedding store, multiple consumers.
- **`costs`** rows ship from day one — measurement is on even when guards are off (Appendix A).
- **`brief_actions`** is a per-brief opt-in queue for follow-up work the user can accept after reading the brief. V1 action types: `run_backtest`, `refine_brief`. Future types (e.g. `schedule_followup`, `deep_dive_related_ticker`) slot in by `action_type` without schema changes. State lifecycle: `pending → accepted | declined | expired`. Columns: `brief_id` FK, `action_type`, `action_params` JSON (free-text instruction for `refine_brief`; window / strategies for `run_backtest`), `state`, `expires_at`, `responded_at`, `result_backtest_id` (FK, set when `run_backtest` completes), `result_brief_id` (FK to a child `briefs` row, set when `refine_brief` completes). The secretary observes state changes and dispatches accepted actions; a sweep marks lapsed rows `expired` with no work done.
- **`briefs.parent_brief_id`** (nullable FK to `briefs.brief_id`) threads refined briefs to the brief they refine. Refinements of refinements work without schema change — the thread just grows.

### Phase-in plan for tables

| Phase | Tables added |
|---|---|
| F1 | runs, briefs, costs, suppression, memories, outcome_log, vec_index, brief_actions |
| F2 | backtests, backtest_runs (no migration of core tables) |
| F3 | events, event_ticker, watchlist (schemas already defined above) |
| F4 | queue_jobs (or Redis-backed; see §7) |
| F5 | deliveries (channel, status, sent_ts) — links to briefs.delivery_ids |
| F6 | reads-only, no new tables |

Migrations after F1 are **append-only** — new tables only, no column reshapes on existing tables.

## 7 · Per-phase plan and exit gates

### F0 — Forge the fork (complete, with one amendment)

**Status:** Complete and manually validated.

**Amendment from this design (§5):** `tradingagents/graph/trading_graph.py:78` no longer forces derivatives into `selected_analysts`. Derivatives becomes optional. This is a one-line revert; ship as part of F1.

### F1 — Decision core + persistence

**Deliverables:**
- Secretary service (Python module, owns DB).
- Persona overlay system (`tradingagents/personas/*.yaml`, three starter personas).
- Run Recorder final node in the graph.
- Full SQLite schema (all tables from §6, even those F3+ fill).
- `sqlite-vec` installed and integrated.
- Hybrid memory wrapper enforcing per-persona partitions.
- Three brief templates (morning / event / deep-dive) as Jinja files.
- CLI `deepdive <ticker>` command — launches three persona runs in parallel.
- Per-analyst markdown to `data/runs/<run_id>/`.
- Boundary smoke tests: Run Recorder fires for every persona; memory wrapper rejects cross-persona reads.

**Exit gate:** On-demand CLI `deepdive AAPL` launches three persona runs in parallel, writes per-analyst markdown to `data/runs/<run_id>/`, records `runs` + `briefs` rows in SQLite, and produces a consensus / divergence / recommendation synthesis brief. Smoke tests pass.

### F2 — Validation: backtest + benchmark

**Deliverables:**
- Backtest harness that reads `runs` + `outcome_log` from F1's store.
- **Two invocation modes** (both implemented in F2; F5 exercises the second):
  - *Watchlist mode* — manually invoked or scheduled; covers a watchlist × date range. This is the F2 exit-gate path.
  - *Brief-scoped mode* — invoked with a `brief_id`; replays only that brief's strategies over a recent window. Used by F5 when the user accepts a post-delivery backtest prompt. **Backtests are never auto-triggered** from sense / triage / secretary internal logic — only an accepted prompt fires this path.
- Replays decisions over historical date ranges.
- Compares each persona to buy-and-hold and to other personas.
- Extends TradingAgents' reflection loop to write `outcome_log` rows (persona-aware).
- Adds `backtests`, `backtest_runs` tables. `backtests` has a nullable `triggered_by_brief_id` FK to `briefs` so brief-scoped backtests are traceable back to the prompt that launched them.
- Reproducible report artifact.

**Exit gate:** Reproducible backtest report for a 5-ticker × 30-day window, with per-persona Sharpe / total return / win rate vs. buy-and-hold. Same report regenerates byte-equal on rerun (modulo timestamps).

### F3 — Always-on sensing + triage

**Deliverables:**
- Continuous ingestion service (Polygon news, Telegram, X, RSS, GDELT, macro feeds).
- Redis as the buffer per ADR-F2 (existing dependency).
- Intelligence Analyst service: dedupe, salience scoring, event→ticker mapping, watchlist TTL refresh.
- Writes to `events`, `event_ticker`, `watchlist` — **schemas already defined in F1**, no migration.
- Sensing service runs as a background process (systemd unit).

**Exit gate:** 24-hour continuous run produces ≥100 events, ≥80% deduped successfully (manual spot-check on a sample), watchlist auto-updates when an event maps to a new ticker.

### F4 — Autonomous trigger loop (thinner than original roadmap)

**Deliverables:**
- Queue: Redis-backed RQ, or a simple `queue_jobs` SQLite table with a polling worker.
- Worker that pulls jobs and invokes the secretary's run methods.
- Triage → secretary handoff: salient events submit `compose_event_alert(event_id)` jobs.
- **Cost guards coded but `enabled=False`** (Appendix A).
- **Backpressure throttles coded but `enabled=False`** (Appendix A).
- Per-job token / cost telemetry recorded.

**Exit gate:** A triage-detected event end-to-end produces a brief with no human in the loop, within ≤15 minutes of ingest. Per-job telemetry visible in SQLite.

### F5 — Delivery + operations

**Deliverables:**
- Delivery channels:
  - **Telegram bot** for event alerts (separate route from F0's OSINT input bot, or the same bot with route discrimination — decide at implementation).
  - **Email (SMTP)** + **CLI tail** for morning digest.
  - **CLI** for deep-dive output.
- Cron-style scheduler for morning brief (configurable time).
- Quiet hours + digest modes (terse / full).
- **Post-delivery action prompts and refinement.** Each delivered brief carries two follow-up affordances:
  - **Structured prompt:** "run backtest on these strategies?" (yes / no / no-response → no action).
  - **Free-text refinement input:** the user can send a free-text comment tied to the brief (e.g. "more aggressive", "drop value persona", "look at last 6 months"). The secretary classifies intent (V1: refinement only — drill-down and scenarios deferred), extracts parameter overrides (persona weights, horizon, analyst selection, risk tilt) via a cheap `quick_think_llm` call, launches new persona runs with the overrides, and delivers a refined brief threaded via `briefs.parent_brief_id`.

  Implementation per channel:
  - *Telegram bot* — inline buttons `[Run Backtest] [Dismiss]` for the structured prompt, **plus** free-text replies threaded via `reply_to_message_id`. Each reply creates a `brief_actions` row with `action_type="refine_brief"` and the reply text in `action_params.instruction`.
  - *CLI deep-dive* — interactive `y/N` for backtest, followed by `Anything to refine? (free text, or Enter to finish)`; loops until empty input. Each non-empty response creates a `refine_brief` row.
  - *Email morning digest* — per-ticker link to a local Streamlit endpoint exposing the backtest button and a refinement text box.
- Response routing: F5 writes `brief_actions` rows; the secretary observes state changes and dispatches by `action_type` — backtests via F2's brief-scoped mode, refinements via re-running persona graphs with parsed overrides. `expires_at` defaults to 24h for both; lapsed rows are marked `expired` by a sweep job.
- **Backtests and refinements are never auto-triggered** — only an accepted prompt or a sent free-text reply fires them. No response within `expires_at` → no action, no nag.
- Streamlit dashboard over SQLite showing: run counts, token spend, brief volume, queue depth, recent decisions, pending and recently-actioned `brief_actions`.
- Runbook: start / stop services, log locations, how to enable cost guards.
- 72-hour unattended soak.

**Exit gate:** 72-hour soak completes. All three brief modes fire at least once. Telemetry shows token / cost trends. No crashes. Cost guards remain off — the soak proves the *natural* cost profile that future thresholds will be calibrated against. Additionally: at least one post-delivery backtest prompt is accepted and produces a brief-scoped backtest end-to-end; at least one prompt is left to expire and triggers nothing; **at least one free-text refinement is submitted and produces a threaded refined brief** (validates the intent classifier + override extraction path end-to-end).

### F6 — Geospatial LiveMap

**Deliverables:**
- Streamlit (V1) or FastAPI + deck.gl (V2 if needed) web view.
- Renders `events` + geocoded briefs on a flat map with hex-clustering.
- Read-only — no decision logic.
- No reuse of D-series secretary code (explicit user direction); D9 geo-event schema may be referenced for tagging.

**Exit gate:** Live map reflects the running system's events and decisions in near-real time. Geo-tagged events appear on the map within minutes of ingest.

### Three changes vs. IIC-FORGE-01 §6 worth flagging

1. **SQLite + schemas pulled forward to F1** — direct consequence of stateful secretary. ADR-F4 rewritten (§10).
2. **F4 is much smaller than originally scoped** — secretary absorbed scheduling. F4 = queue + worker + wire-up.
3. **F5 picks up the observability dashboard** that the roadmap implied but didn't define. Streamlit over SQLite is the cheapest viable option.

## 8 · Risks and open questions

### Risk register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Vibe-coding gap (carry-over) | High | Boundary smoke test per phase per principle P7 |
| R2 | **F1 schema churn** (new) | High | Schemas designed upfront in §6. Post-F1 changes are append-only — new tables, never column reshapes |
| R3 | **Synthesis prompt averages disagreement away** (new) | High | Explicit `divergence` section in the secretary prompt; eval test asserts known-disagreement inputs survive synthesis |
| R4 | **No cost guards during F1–F5** (new) | High | Hard kill switch via systemd `MemoryMax` / `CPUQuota`; measurement on so anomalies are visible in the Streamlit dashboard within hours, not weeks |
| R5 | **SQLite single-writer contention** (new) | Low-Med | WAL mode + short transactions + single secretary process owning `runs` writes; other tables are read-mostly |
| R6 | **Hybrid memory key bugs** (new) | Med | Thin wrapper class enforces `(persona_id, component)`; boundary test asserts no cross-persona leakage |
| R7 | **Reflection-loop coupling to `outcome_log`** (new) | Med | Additive — keep existing reflection signatures; add `persona_id` as optional param defaulting to None |
| R8 | OSINT fragility (carry-over) | Med | `DataVendorError` fallback chain already in place from F0 |
| R9 | Futu OpenD ops burden (carry-over) | Med | Optional in fallback chain; never blocks a run |
| R10 | Over-trusting framework alpha (carry-over) | Med | F2 backtest is first-class; outputs are decision-support, not signals |
| R11 | **Solo-builder bandwidth — F1 grew** (revised) | Med | Keep F2 minimal (one persona vs. buy-and-hold), defer multi-persona backtest comparison if F2 stretches |

### Open questions — decide at implementation time, not now

1. **Persona count for V1** — three (macro / value / momentum) is the starter; sub-personas can come later.
2. **Morning-digest watchlist cap** — default = all watchlist; threshold / cap decided when F3 watchlist volume is observable.
3. **Reflection trigger cadence** — TradingAgents' existing trigger needs confirming before F2 (after each run? after N? manual?).
4. **Telegram bot — input + output same bot?** — F0 uses Telegram for OSINT input; F5 wants Telegram for brief output. Same bot with two routes is fine; reconfirm at F5.
5. **Watchlist source of truth in F3** — pure triage-driven, or also user-curated? Hybrid likely, decide at F3 start.
6. **F2 evaluation universe** — which 5 tickers × 30 days for the backtest exit gate? Owner's call at F2.

## 9 · Out of scope

The following are deliberately not part of IIC-FORGE F1–F6:

- **Trade execution** — IIC is decision-support only; no order placement, ever.
- **Multi-user / auth** — personal use, single user (P5).
- **Cloud deployment** — local-first; cloud is a contingency only.
- **Domain fine-tuning** — was in the D-series plan; not in IIC-FORGE.
- **Real-time streaming market data** — polling + Redis buffer is sufficient.
- **LiveMap advanced features** — F6 ships read-only; no time-scrubbing, no scenario simulation.
- **Vector-RAG over historical briefs** — `sqlite-vec` is wired for memory similarity now; full RAG-over-history is a post-F6 consideration.
- **Chat capabilities beyond refinement** — V1 brief-tied chat is refinement only. Drill-down (answers from existing reports without re-running) and scenario / what-if (hypothetical state injection) are deferred; both slot in later as new `action_type` values without schema changes.
- **Reuse of D-series secretary code** — secretary is built fresh (explicit user direction during the brainstorming session).

## 10 · ADR amendments

### ADR-F4 (revised) — State and persistence

**Context.** TradingAgents logs to files and a markdown decision log. The stateful secretary design (D2) requires queryable persistence from F1.

**Decision.** SQLite + filesystem hybrid + `sqlite-vec` from F1. Long-form markdown lives on disk (`data/runs/<run_id>/`), referenced by path in SQLite. Embeddings via `sqlite-vec` virtual table. All F3/F4/F5 table schemas defined upfront at F1.

**Supersedes:** IIC-FORGE-01 ADR-F4 ("defer DB to F3").

**Consequences.**
- F1 ships with a full schema; F2/F3/F5 add tables but never reshape existing ones.
- Backups: one SQLite file + one filesystem tree, both rsync-friendly.
- Upgrade triggers documented (not pre-emptive): Qdrant for RAG-over-history; DuckDB or Timescale for high event volume; Postgres + S3 if cloud-deployed.

### ADR-NEW-1 — Stateful secretary

**Context.** The IIC supports three operational modes equally. A passive post-processor cannot decide what to run, when, or whether to suppress.

**Decision.** The secretary is a long-lived stateful Python service that owns the DB and has three entry points (`compose_morning_digest`, `compose_event_alert`, `compose_deep_dive`). Each graph run includes a Run Recorder final node that normalizes its outputs into the secretary's store.

**Consequences.**
- F4's orchestrator becomes thinner (queue + worker, no scheduler).
- F1 grows to include persistence + secretary; mitigated by keeping F2 minimal.
- Boundary smoke tests assert the Run Recorder fires for every persona run (the P7 antidote to the vibe-coding gap).

### ADR-NEW-2 — Hybrid memory partitioning

**Context.** Personas need meaningfully different decision-making but should learn from each other's outcomes.

**Decision.** Per-persona partitions for decision-maker memories (bull / bear / trader / research manager / risk manager), keyed by `(persona_id, component)`. One shared `outcome_log` table for run outcomes — every persona can query it via `sqlite-vec` similarity.

**Consequences.**
- A thin Python wrapper enforces the `(persona_id, component)` key — cross-persona memory reads are structurally impossible (boundary test asserts this).
- Reflection signatures gain an optional `persona_id` parameter defaulting to None (preserves existing single-team behavior for legacy runs).

### ADR-NEW-3 — Post-delivery actions and brief threading

**Context.** Briefs are one-shot artifacts. Users will reasonably want two kinds of follow-up: (a) deterministic next steps (run a backtest of these strategies) and (b) free-text refinement of the brief itself (more aggressive, shorter horizon, drop a persona). Auto-triggering follow-ups is wasteful; offering none loses obvious user value.

**Decision.** Each brief carries two follow-up affordances on its delivery channel:
- **Structured prompt** — "run backtest on these strategies?" (yes / no / expire). V1's only structured action.
- **Free-text refinement** — a per-channel reply path. The secretary classifies intent (V1: refinement only), extracts parameter overrides via a cheap `quick_think_llm` call, and launches new persona runs producing a refined brief tied to the original via `briefs.parent_brief_id`.

The secretary launches any action only on user input. No response within `expires_at` (default 24h) → no action, ever.

**Consequences.**
- F2 harness ships two invocation modes (watchlist, brief-scoped) — both coded in F2; brief-scoped exercised by F5.
- F5 owns per-channel prompt rendering **and** free-text reply capture (Telegram inline buttons + reply threading, CLI interactive prompt + refinement input, email link to a Streamlit endpoint with both controls).
- New `brief_actions` table defined in F1 schema; populated only when F5 ships. V1 action types: `run_backtest`, `refine_brief`.
- `briefs.parent_brief_id` (nullable FK) threads refined briefs; refinements of refinements work without schema change.
- Backtests *and* refinements are never auto-triggered from sense / triage / secretary internal logic — only an accepted prompt or a sent free-text reply fires them. This also protects against runaway cost during the no-cost-guards window (Appendix A).
- Out of scope for V1: drill-down (answers from existing reports without re-running) and scenario / what-if (hypothetical state injection). Both slot in later as new `action_type` values / intent classes without schema changes.

### IIC-FORGE-02 §A.9e — Amended (mandatory derivatives reverted)

**Original (F0):** Forces `derivatives` into `selected_analysts` if missing.

**Amendment:** Removed. Personas' `analysts.include/exclude` is authoritative. CLI default list still includes derivatives, but this is a default, not an enforcement rule.

**Where:** One-line revert in `tradingagents/graph/trading_graph.py:78`. Ship as part of F1.

---

## Appendix A · Cost guard policy (F0–F5)

Cost-control and rate-limiting features (per-run token budgets, daily spend ceilings, queue throttles, OSINT rate limits, F4 backpressure) are **implemented but ship with `enabled=False` defaults** throughout F0–F5 development.

**Why:** Validate the system works end-to-end and observe natural cost / rate patterns from real runs before deciding where thresholds belong. Premature limits would interfere with exploration and might suppress legitimate work before the system is even working. The owner can flip flags on once empirical data exists from the F5 dashboard.

**How:**
- Write the enforcement code so the function exists and can be toggled on later.
- Add a config flag (e.g. `cost_guard_enabled: false`).
- Default OFF.
- Still log the underlying measurements (token counts, request rates, queue depth, cost-per-run) — measurement is **always on**.
- Note in code comments that the guard is intentionally off in development.

This flips IIC-FORGE-01 §8 ("Cost and rate control") for F0–F5: measurement yes, enforcement no.

## Appendix B · Reuse from prior IIC work

What this design reuses from IIC-FORGE-01 §10 and prior IIC tracks:

- **Boundary-contract discipline** — the operating model for all FORGE work, applied to the Run Recorder, memory wrapper, and per-phase smoke tests.
- **Source geographic-balance work** — informs the F3 ingestion source list.
- **LiveMap geo-event schema (D9)** — referenced for F6 geo tagging only; no other D-series code is reused.

What this design deliberately drops from prior IIC work:

- **D-series secretary agent design** — secretary is built fresh per explicit user direction.
- **D-series full-stack dashboard / back-end** — F5 uses a Streamlit dashboard over SQLite instead.

---

*End of IIC-FORGE-03. Per-phase implementation specs (IIC-FORGE-04+) follow as each phase is up next.*
