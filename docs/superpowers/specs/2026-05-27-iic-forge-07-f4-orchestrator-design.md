# IIC-FORGE-07 — F4 Autonomous Trigger Loop — Design

| Field | Value |
|---|---|
| **Track** | IIC-FORGE |
| **Document** | 07 |
| **Scope** | Per-phase design for F4 (Autonomous trigger loop). One level deeper than [the program-level spec §7-F4](2026-05-25-iic-forge-program-design.md). |
| **Base engine** | TauricResearch/TradingAgents v0.2.5 (F1, F2, F3 shipped) |
| **Owner** | Ziwei |
| **Date** | 2026-05-27 |
| **Status** | Ready for implementation planning |
| **Supersedes** | — |
| **Amends** | — (operates within F1 schema + F3 sensing output; adds five `ALTER TABLE … ADD COLUMN` statements only) |
| **Relates to** | [IIC-FORGE-03 program design](2026-05-25-iic-forge-program-design.md) §3 architecture, §6 state schema, §7-F4 exit gate, Appendix A; [IIC-FORGE-04 F1 plan](../plans/2026-05-25-iic-forge-04-f1-decision-core.md); [IIC-FORGE-06 F3 design](2026-05-26-iic-forge-06-f3-sensing-triage-design.md) |
| **Companion plan (next)** | `docs/superpowers/plans/2026-05-27-iic-forge-07-f4-orchestrator.md` (output of `superpowers:writing-plans`) |

## Quick links

- §1 Executive summary
- §2 Anchoring decisions
- §3 Architecture
- §4 Data model
- §5 Promoter service internals
- §6 Worker service + `compose_event_alert`
- §7 Configuration, files, tests
- §8 Cost guards and backpressure (all `enabled=False`)
- §9 Exit-gate evaluator and evidence approach
- §10 Risks
- §11 Out of scope
- §12 Open questions deferred to implementation

---

## 1 · Executive summary

F4 ships the **autonomous trigger loop** that turns the F3 sensing+triage pipeline into closed-loop event-driven decision support. A long-lived **promoter** service watches the `events` table for triaged, watchlist-relevant, high-salience events and inserts `queue_jobs` rows. A long-lived **worker** service leases those jobs and invokes the secretary's `compose_event_alert(event_id)` entry point — a method that was stubbed at F1 as `NotImplementedError("lands in F4")` and is now implemented end-to-end. The result is a brief in `briefs/<brief_id>.md` and a `briefs` row whose new `trigger_event_id` column links back to the source event.

Six shape choices vs. the program-spec sketch:

1. **Queue substrate is SQLite, not Redis.** The `queue_jobs` table already exists in the F1 schema; reusing it keeps the queue and its telemetry in one store (no second durability path for what is essentially one job type at low rate). Redis stays first-class for F3 sensing/triage; F4 does not touch it.
2. **Triage → secretary handoff is a separate promoter service, not inline in F3 triage.** A `iic-promoter.service` polls the `events` table every 10 seconds. F3 stays decoupled from F4 and remains a pure sensing+triage pipeline.
3. **Trigger rule is watchlist-bound and threshold-bound.** A promotion fires when `event.salience ≥ 0.7 AND event_ticker.confidence ≥ 0.8 AND ticker ∈ watchlist`. Mirrors F3's watchlist auto-promote thresholds. Auto-promoted-new-ticker events fire on the same pass because the ticker is on the watchlist after auto-promote (§4).
4. **Per-ticker 60-min cooldown via the existing `suppression` table.** The promoter writes a `suppression` row with `key='event_alert:{ticker}'` and `until_ts=now()+60min` in the same transaction as the enqueue. Catches the three-stories-same-hour case; misses the rare second-materially-different-story-within-window case (acceptable for V1).
5. **Worker runs one job at a time by default; three personas in parallel inside the job.** Reuses the F1 `forge deepdive` ThreadPoolExecutor pattern. `max_concurrent_jobs` is a config knob defaulting to `1`. Keeps queue order honest and LLM rate-limit pressure manageable.
6. **All four cost/backpressure guards coded, all ship `enabled=False`.** Per memory `cost-guards-disabled-by-default` and program-spec Appendix A: queue-depth backpressure, daily rate cap, daily budget ceiling, per-run token budget (the last reused from F1's `CostGuard`). Measurement is always on; enforcement is one config flag flip away.

The exit gate is twofold: a **synthetic-event smoke test** runs in CI on every commit (boots promoter+worker as threads, injects a known-salient event, asserts brief ≤60 s); a **live observation window** (6–12 h with F3 adapters on the user's normal watchlist) characterizes the SLA on organically-arrived events with a tiered pass rule (§9). The artifact at `docs/superpowers/artifacts/2026-MM-DD-f4-exit-gate-report.md` carries both signals plus a restart audit.

## 2 · Anchoring decisions

Settled during brainstorming. Each one rules out alternatives that would have changed the design materially.

### D1 — Queue: SQLite `queue_jobs` table with polling worker

The alternatives considered were Redis stream + consumer group (consistent with F3 triage) and the `rq` library on top of Redis. The case against Redis that won was operational: F4's queue is the system's **telemetry seam** — `queue_jobs` rows carry SLA timestamps and cost rollups that the F5 dashboard and the exit-gate evaluator both read. Keeping the queue in the same store as the telemetry it produces avoids a second durability path for what is essentially one job type at low rate (≤ 5 jobs/day expected at exit-gate volume). Redis remains first-class for F3 sensing/triage; F4 does not touch it.

Trade-offs:
- Latency floor is the worker's 2 s poll interval. Easily inside the 15-min SLA.
- A single SQLite writer (worker) on the queue keeps R5 (single-writer contention) comfortable — the promoter writes 1 row per qualified event (≤ 5/day expected), and the worker writes 2 columns per job lifecycle.

### D2 — Handoff: separate promoter service polling `events`

The alternatives were enqueueing inline at the end of F3's `process_one` (tight coupling) and an XADD-to-Redis-stream handoff (a third Redis stream). The case for a separate promoter that won was decoupling: F3 stays a pure sensing+triage pipeline, fully decoupled from F4's notion of "what is a brief-worthy event." Changing the trigger rule in F4 never modifies F3 code. The cost is one more long-lived process; mitigated by the promoter being trivial (one query + one tx per qualifying event).

Idempotency is structural via the candidate query's `LEFT JOIN queue_jobs ON trigger_event_id` — a re-poll after crash never double-enqueues (§4).

### D3 — Trigger rule: watchlist-only, high-salience

The alternatives considered were "any high-salience event ≥ 0.85 regardless of watchlist" (catches market-wide stories but spams) and "looser threshold of 0.6" (more recall, harder to keep noise down without smart suppression). The winning case: F3's auto-promote already uses `salience ≥ 0.7 AND ticker.confidence ≥ 0.8` to mutate the watchlist. Reusing those thresholds for the event-alert trigger means the same evidence that earns a ticker a watchlist slot also earns it an alert — single mental model for the operator, two effects.

Auto-promoted-new-ticker events fire on the same pass because the ticker is on the watchlist after F3's promotion commits, and the promoter polls *after* both commits land.

### D4 — Suppression: per-ticker 60-min cooldown via existing `suppression` table

The alternatives were per-`(ticker, topic-bucket)` (more recall, requires a `topic` field in the salience response and risks topic-classification drift) and per-`(ticker, semantic-cluster)` via cosine to last-fired event embedding (most precise but adds DB lookups per candidate). Per-ticker 60-min is simplest, handles the common case (three stories same hour about AAPL earnings), and misses only the rare second-materially-different-story-within-window. That second story still appears in tomorrow's morning brief, so the loss is bounded.

The `suppression` table already exists in F1 (`key`, `until_ts`, `reason`, `created_by`) — no schema change. The enqueue + suppression upsert ride in one SQLite transaction.

### D5 — Personas per job: all three, same shape as deep-dive

The alternatives were one persona routed by event type (cheapest, loses cross-persona disagreement) and tiered "high-salience → 3, medium → 1" (no empirical basis yet). The winning case: the secretary's value proposition is consensus / divergence / recommendation; collapsing to a single persona for "terse" alerts destroys that. The cost (~3× per alert) is acceptable in the cost-guards-disabled regime; the daily-budget telemetry from the soak will inform whether to keep this or fall back later.

Inside the job, the three personas run in parallel via the same ThreadPoolExecutor pattern as F1's `forge deepdive`. No new concurrency primitives.

### D6 — Worker: single process, configurable `max_concurrent_jobs` (default 1)

The alternatives were one-job-at-a-time hardcoded and a systemd template unit running N worker processes. The winning case: a config knob is one extra line and preserves the option of lifting concurrency once API rate headroom is known empirically. Default `1` keeps queue order honest and avoids cross-job LLM rate-limit contention during the gate run.

Multi-process workers via systemd template are an escape hatch documented in the runbook, not a default.

### D7 — On-demand deep-dive: stays synchronous, does NOT route through the queue

The alternative was unifying `forge deepdive` through the queue for consistent telemetry. The case against: deep-dive's blocking UX with progress output is a deliberate F1 affordance for exploratory ticker work; routing it through the queue adds poll latency and complicates Ctrl-C semantics. Telemetry parity is a non-goal — the user knows what they ran when they ran it manually. The queue stays focused on autonomous, event-triggered work.

Cost guards still apply to manual runs via F1's existing per-run `CostGuard`; what does *not* apply is the queue-layer daily budget. The user can ctrl-C; that's enough.

### D8 — Exit gate: synthetic-event smoke + live F3-sourced observation

The alternatives were synthetic-only (deterministic and fast but doesn't catch real-world adapter shape issues) and live-only (slow, brittle, hours-to-days). The winning case: synthetic gives CI signal on every commit and proves the wiring; live gives the operator confidence that real envelopes from real adapters survive the pipeline end-to-end and meet the 15-min SLA. Both signals land in one artifact.

The live window is 6–12 h on the user's normal watchlist — long enough that 0–5 organic event_alert jobs are realistic, short enough not to require a multi-day commitment.

## 3 · Architecture

```
                                    ┌────────────────────────────────┐
F3 triage  ──── writes ──────►      │  events / event_ticker / wl    │
                                    └──────────────┬─────────────────┘
                                                   │ poll (every 10s)
                                                   ▼
                                ┌──────────────────────────────────┐
                                │  iic-promoter.service            │
                                │  • selects new events meeting    │
                                │    trigger rule + not in cooldown│
                                │  • inserts queue_jobs(           │
                                │      job_type='event_alert',     │
                                │      payload={event_id, ticker}, │
                                │      trigger_event_id=event_id)  │
                                │  • upserts suppression(ticker,   │
                                │      until_ts=now+60min)         │
                                └──────────────┬───────────────────┘
                                               │ (one SQLite tx)
                                               ▼
                                ┌──────────────────────────────────┐
                                │  queue_jobs (SQLite, F1 table)   │
                                │  state: queued → running → done  │
                                └──────────────┬───────────────────┘
                                               │ poll (every 2s)
                                               ▼
                                ┌──────────────────────────────────┐
                                │  iic-worker.service              │
                                │  • leases 1 job (atomic UPDATE   │
                                │    ... RETURNING)                │
                                │  • dispatches by job_type        │
                                │  • for 'event_alert':            │
                                │      Secretary.compose_event_    │
                                │       alert(event_id)            │
                                │      → 3 personas in parallel    │
                                │      → 1 brief row + brief MD    │
                                │  • cost guards (enabled=False)   │
                                │  • backpressure (enabled=False)  │
                                │  • writes job timing + cost      │
                                │    rollup to queue_jobs row      │
                                └──────────────────────────────────┘
```

Two new long-lived processes, both `systemd` units following the F3 adapter conventions:

- **`iic-promoter.service`** — polls `events` every 10 s, applies the trigger rule, enqueues + upserts suppression. Defensive retry-internal: never raises out of the loop except on configuration errors (matching F3's discipline; the exit-gate evaluator fails the gate on any `NRestarts > 0`).
- **`iic-worker.service`** — polls `queue_jobs` every 2 s, leases one job at a time via atomic `UPDATE … RETURNING`. Dispatches by `job_type`; for `event_alert`, calls `Secretary.compose_event_alert(event_id)` which fans out 3 personas via the F1 ThreadPoolExecutor.

### Three load-bearing constraints

1. **One-way data flow.** Promoter only reads from F3's tables and writes to `queue_jobs` + `suppression`. Worker only reads from `queue_jobs` and writes to `runs` / `briefs` / `costs`. No reverse coupling.
2. **At-least-once with structural idempotency.** Promoter crashes between enqueue and suppression-insert do not double-fire because the candidate query's `LEFT JOIN queue_jobs ON trigger_event_id` filters out anything already enqueued. The single SQLite transaction is correctness's primary mechanism; the LEFT JOIN is a belt-and-braces invariant.
3. **No new tables.** F4 reuses `queue_jobs` (defined in F1), `suppression` (defined in F1), `briefs` (defined in F1), `runs` (defined in F1), `costs` (defined in F1). Only five `ALTER TABLE … ADD COLUMN` statements (§4).

### SLA accounting

The worker writes `started_ts` and `finished_ts` to the `queue_jobs` row. The brief row gets a new `trigger_event_id` column linking back to the source event. End-to-end latency for the SLA is:

```
latency = briefs.generated_ts − events.ingested_ts
        = (queue wait) + (worker dispatch) + (3-persona run) + (synthesis) + (render+write)
```

Target: `p95 ≤ 15 min` over the live observation window. Budget breakdown: ≤ 3 min queue wait, ≤ 10 min run, ≤ 2 min synthesis+render. The exit-gate evaluator computes percentiles directly from `briefs` and `events` rows.

## 4 · Data model

**Tables added by F4: zero.** `queue_jobs`, `suppression`, `briefs`, `costs`, `runs` all exist from F1.

**Column additions (append-only on existing tables):**

```sql
-- queue_jobs: add telemetry columns for SLA + cost rollup + idempotency
ALTER TABLE queue_jobs ADD COLUMN trigger_event_id  TEXT REFERENCES events(event_id);
ALTER TABLE queue_jobs ADD COLUMN run_ids           TEXT;      -- JSON array of runs.run_id this job produced
ALTER TABLE queue_jobs ADD COLUMN brief_id          TEXT REFERENCES briefs(brief_id);
ALTER TABLE queue_jobs ADD COLUMN cost_usd          REAL;      -- sum across run_ids; written on completion
ALTER TABLE queue_jobs ADD COLUMN error             TEXT;      -- exception message if state='error'

-- briefs: link the brief to the triggering event (event_alert mode only; NULL for deep_dive)
ALTER TABLE briefs ADD COLUMN trigger_event_id      TEXT REFERENCES events(event_id);

-- runs: link the run to the job that launched it (NULL for ad-hoc forge deepdive runs)
ALTER TABLE runs ADD COLUMN queue_job_id            INTEGER REFERENCES queue_jobs(job_id);
```

All `ALTER TABLE … ADD COLUMN` — SQLite-native, no rewrite, no migration risk. Matches the program spec's post-F1 append-only rule.

**Idempotent application.** Existing F0–F3 connections must remain usable. `ALTER TABLE … ADD COLUMN` is *not* idempotent in sqlite — re-running raises `OperationalError: duplicate column name`. F3 only used `CREATE TABLE IF NOT EXISTS`, so this is a new pattern for the project: each `ALTER TABLE` runs inside `try/except sqlite3.OperationalError` that swallows the duplicate-column error and re-raises everything else. A single boundary test (`test_schema_init_idempotent.py`) verifies that running the schema init twice on the same DB is a no-op.

**Index addition (one):**

```sql
CREATE INDEX IF NOT EXISTS idx_queue_jobs_trigger_event
    ON queue_jobs(trigger_event_id);
```

Used by the promoter's `LEFT JOIN queue_jobs` idempotency check; without it the join is a sequential scan that grows with queue history.

### Suppression usage (no schema change needed)

The existing `suppression` table (`key TEXT PK, until_ts TEXT, reason TEXT, created_by TEXT`) is used as follows:

| Column | Value |
|---|---|
| `key` | `f"event_alert:{ticker}"` |
| `until_ts` | `now() + 60 min` |
| `reason` | `f"alert_cooldown event_id={event_id}"` |
| `created_by` | `"promoter"` |

Cooldown duration is configurable (`alert_cooldown_min`, default `60`).

### Promoter candidate query

```sql
SELECT e.event_id, et.ticker, e.salience
FROM events e
JOIN event_ticker et   ON et.event_id = e.event_id
JOIN watchlist  w      ON w.ticker     = et.ticker
LEFT JOIN suppression s ON s.key = 'event_alert:' || et.ticker
                       AND s.until_ts > datetime('now')
LEFT JOIN queue_jobs q ON q.trigger_event_id = e.event_id
WHERE e.status = 'triaged'
  AND e.salience >= ?
  AND et.confidence >= ?
  AND s.key IS NULL          -- not currently suppressed
  AND q.job_id IS NULL       -- not already enqueued (idempotency)
ORDER BY e.ingested_ts ASC
LIMIT ?;
```

Thresholds come from config (`alert_salience_threshold`, `alert_ticker_confidence_threshold`); limit comes from `promoter_batch_size` (default `50`). The `LEFT JOIN queue_jobs … q.job_id IS NULL` is the structural idempotency guard.

### Cost rollup

Each persona run already writes a `costs` row keyed by `run_id` (F1). On job completion, the worker computes:

```sql
SELECT SUM(usd_estimate) FROM costs WHERE run_id IN (<run_ids>);
```

and writes it to `queue_jobs.cost_usd`. No new cost-tracking machinery; just an aggregate at job-completion time. The same number drives the daily-budget guard (§8).

## 5 · Promoter service internals

`iic-promoter.service` is a small long-lived Python process at `tradingagents/orchestrator/promoter.py`. One synchronous loop, no asyncio needed (single SQLite consumer, low rate).

```python
def run():
    cfg = load_orchestrator_config()
    conn = open_db_wal()
    while True:
        try:
            candidates = fetch_candidates(
                conn,
                salience_threshold=cfg.alert_salience_threshold,
                ticker_conf_threshold=cfg.alert_ticker_confidence_threshold,
                limit=cfg.promoter_batch_size,
            )
            for ev in candidates:
                with conn:                                 # one tx per event
                    insert_queue_job(
                        conn,
                        job_type="event_alert",
                        payload=json.dumps({"event_id": ev.event_id, "ticker": ev.ticker}),
                        trigger_event_id=ev.event_id,
                    )
                    upsert_suppression(
                        conn,
                        key=f"event_alert:{ev.ticker}",
                        until_ts=now_utc() + timedelta(minutes=cfg.alert_cooldown_min),
                        reason=f"alert_cooldown event_id={ev.event_id}",
                        created_by="promoter",
                    )
                log.info("enqueued event_alert", extra={"event_id": ev.event_id, "ticker": ev.ticker})
        except sqlite3.OperationalError:
            log.warning("db busy, backing off"); time.sleep(2)
        except Exception:
            log.exception("promoter loop failure")        # defensive — never exit
            time.sleep(5)
        time.sleep(cfg.promoter_poll_interval_s)          # default 10
```

### Three load-bearing properties

1. **Single SQLite transaction per event.** The enqueue + suppression upsert are atomic. A crash between events is safe (the next loop iteration re-evaluates from scratch via the LEFT JOIN guard).
2. **Defensive retry-internal.** Bare `try/except Exception` around the loop body, log + sleep + continue. Same discipline as F3 adapters (R-F3-1). The `systemctl show iic-promoter --property=NRestarts` value must remain `0` during the exit-gate window.
3. **No watchlist coupling.** The promoter does not know what a watchlist is; it joins against the `watchlist` table. F3's auto-promote and the user CLI both flow through the same table, so the promoter is automatically up-to-date.

### Operability

- `forge orchestrator promoter` CLI subcommand for dev/debugging — same module entry as `python -m tradingagents.orchestrator.promoter`. The systemd unit uses the `-m` form per the F3 adapter convention.

## 6 · Worker service + `compose_event_alert`

`iic-worker.service` lives at `tradingagents/orchestrator/worker.py`. A single Python process; concurrency is bounded by an asyncio `Semaphore(max_concurrent_jobs)` (default `1`).

### Leasing loop

```python
def lease_one(conn) -> Optional[Row]:
    """Atomic claim. RETURNING is sqlite >= 3.35; we have it (Ubuntu 22.04+, sqlite-vec
    transitive requirement is 3.41+)."""
    with conn:                                    # implicit BEGIN IMMEDIATE
        row = conn.execute("""
            UPDATE queue_jobs
               SET state = 'running',
                   started_ts = datetime('now')
             WHERE job_id = (
                 SELECT job_id FROM queue_jobs
                  WHERE state = 'queued'
                  ORDER BY job_id
                  LIMIT 1
             )
         RETURNING job_id, job_type, payload, trigger_event_id
        """).fetchone()
    return row

async def run():
    sem = asyncio.Semaphore(cfg.max_concurrent_jobs)
    while True:
        async with sem:                           # cap inflight
            job = lease_one(conn)
            if job is None:
                await asyncio.sleep(cfg.worker_poll_interval_s)   # default 2
                continue
            try:
                dispatch(conn, job)
            except Exception as exc:
                mark_error(conn, job.job_id, exc)
            else:
                mark_done(conn, job.job_id)
```

`mark_done` writes `finished_ts`, `run_ids` (JSON), `brief_id`, and `cost_usd` (SQL aggregate over `costs`). `mark_error` writes `finished_ts`, `error` (exception text), and sets `state='error'`.

### Per-job wall-clock cap (R-F4-2 mitigation)

The worker wraps `dispatch(conn, job)` in a hard timeout (default `worker_job_timeout_min: 20`). On expiry, the in-flight LangGraph run is cancelled, the exception is propagated to `mark_error`, and the slot frees. A stale-lease sweep on worker startup handles unclean restarts:

```sql
UPDATE queue_jobs
   SET state = 'error',
       finished_ts = datetime('now'),
       error = 'stale_lease_swept_on_boot'
 WHERE state = 'running'
   AND started_ts < datetime('now', '-1 hour');
```

### Dispatch table

```python
DISPATCH = {
    "event_alert":     dispatch_event_alert,
    # Future: 'morning_digest' (F5), 'deep_dive_async' (if ever routed here)
}
```

One job_type today; the dispatch shape is the seam F5/F6 will extend.

### `Secretary.compose_event_alert(event_id)` — implementation

Replaces the `NotImplementedError` stub. The logic mirrors `compose_deep_dive` but is event-scoped, not ticker-prompted:

```python
def compose_event_alert(self, *, event_id: str, ticker: str, job_id: int) -> str:
    """`ticker` is passed in from the promoter's job payload — the specific
    watchlist ticker that fired the rule. The events table is multi-ticker
    (one event can have multiple event_ticker rows); the promoter resolves
    which ticker the alert is *for* at enqueue time, not at brief time."""
    ev = store.get_event(self._conn, event_id)
    raw = json.loads(Path(ev["raw_path"]).read_text())
    trade_date = datetime.fromisoformat(ev["ingested_ts"]).date().isoformat()

    # Run 3 personas in parallel (same ThreadPoolExecutor pattern as `forge deepdive`)
    persona_runs = self._run_personas_parallel(
        ticker=ticker,
        trade_date=trade_date,
        event_context=raw["text"],               # the event becomes prompt context
        queue_job_id=job_id,                     # written to runs.queue_job_id
    )

    # Synthesis: reuse synthesize_brief() — consensus/divergence/recommendation
    synthesis = synthesize_brief(llm=self._llm, ticker=ticker, persona_runs=persona_runs)

    # Render terse alert template (NEW jinja: event_alert.j2)
    markdown = render_event_alert(
        ticker=ticker,
        event=ev,
        synthesis=synthesis,
        persona_runs=persona_runs,
    )

    brief_id = uuid.uuid4().hex
    (self._data_dir / f"briefs/{brief_id}.md").write_text(markdown, encoding="utf-8")
    store.insert_brief(
        self._conn,
        brief_id=brief_id, mode="event_alert", scope=ticker,
        generated_ts=now_utc_iso(), content_path=f"briefs/{brief_id}.md",
        run_ids=[r["run_id"] for r in persona_runs],
        parent_brief_id=None,
        trigger_event_id=event_id,           # NEW column from §4
    )
    return brief_id
```

### Two implementation notes

1. **Event context injection.** The TradingAgents graph already accepts a `trade_date` and ticker; we don't have an "event context" parameter. The cleanest seam is to extend the persona's `system_prompt_fragment` at run-time with a one-shot prefix like *"Context: the following news item just arrived: {event.text}"*. No graph signature changes; it's a string concat inside `_run_personas_parallel`. The boundary test asserts the prefix reaches each persona's pm_synthesis. The injected prefix is also written to `data/runs/<run_id>/event_context.md` (alongside the existing per-analyst markdown files) for audit.
2. **Terse template.** New `event_alert.j2` next to `deep_dive.j2`. Format per program spec §4: terse, one ticker, the event, the decision shift, action items, links to full reports. ~200–400 words target.

### `_run_personas_parallel` (extracted helper)

F1's `forge deepdive` already runs 3 personas in parallel; F4 extracts that into `Secretary._run_personas_parallel` so both `compose_deep_dive` and `compose_event_alert` share the same code path. The extraction is mechanical — copy-out, parameterize on `event_context` (None for deep_dive). No behavior change for F1's deep_dive.

### Operability

- `forge orchestrator worker` CLI subcommand for dev/debugging.
- `forge orchestrator status` shows queue depth, last-N job costs, recent failures (read-only over `queue_jobs`). Quick triage tool; precursor to the F5 Streamlit dashboard.
- systemd unit `iic-worker.service` runs the `-m` entry point with `MemoryMax=4G`, `CPUQuota=200%` (room for 3 parallel personas).

## 7 · Configuration, files, tests

### New configuration keys (`tradingagents/default_config.py`)

```python
# F4 orchestrator
"orchestrator_enabled":                False,    # master switch for promoter + worker boot
"promoter_poll_interval_s":            10,
"promoter_batch_size":                 50,
"alert_cooldown_min":                  60,
"alert_salience_threshold":            0.7,
"alert_ticker_confidence_threshold":   0.8,
"worker_poll_interval_s":              2,
"worker_job_timeout_min":              20,
"max_concurrent_jobs":                 1,

# Cost guards — all ship enabled=False per Appendix A
"trigger_backpressure_enabled":        False,
"trigger_backpressure_max_pending":    20,
"trigger_daily_rate_enabled":          False,
"trigger_daily_rate_max_jobs":         200,
"daily_budget_enabled":                False,
"daily_budget_usd":                    10.0,
# cost_guard_enabled already exists from F1, still False
```

All env-overridable via the existing `TRADINGAGENTS_*` pattern.

### File layout (created in this plan)

| Path | Responsibility |
|---|---|
| `tradingagents/orchestrator/__init__.py` | Package marker |
| `tradingagents/orchestrator/promoter.py` | Polling loop + candidate query + enqueue+suppression tx; `__main__` entry |
| `tradingagents/orchestrator/worker.py` | Leasing loop + dispatch table + cost-guard hooks; `__main__` entry |
| `tradingagents/orchestrator/queue_store.py` | `lease_one`, `mark_done`, `mark_error`, `insert_queue_job` over `queue_jobs` |
| `tradingagents/orchestrator/guards.py` | `QueueBackpressure`, `QueueRateGuard`, `DailyBudgetGuard` — all ship `enabled=False` |
| `tradingagents/orchestrator/dispatch.py` | `DISPATCH` map; `dispatch_event_alert(conn, job)` |
| `tradingagents/secretary/templates/event_alert.j2` | Terse alert template (NEW) |
| `cli/forge.py` *(modified)* | `forge orchestrator promoter \| worker \| status` subcommands |
| `ops/systemd/iic-promoter.service` | systemd unit; `MemoryMax=256M`, `CPUQuota=25%`, `Restart=on-failure` |
| `ops/systemd/iic-worker.service` | systemd unit; `MemoryMax=4G`, `CPUQuota=200%`, `Restart=on-failure` |
| `ops/runbooks/f4-exit-gate.md` | Pre-flight + run procedure for the gate |
| `scripts/f4_exit_gate.py` | Reads `queue_jobs` + `briefs` + `events` for the window; SLA percentiles + per-job table |

### Files modified

| Path | Change |
|---|---|
| `tradingagents/persistence/schema.sql` | 5 `ALTER TABLE ... ADD COLUMN` statements + 1 `CREATE INDEX IF NOT EXISTS` from §4. Each ALTER is wrapped in `try/except sqlite3.OperationalError` to swallow `duplicate column name` errors — `ADD COLUMN` is not idempotent in sqlite (F3 only used `CREATE TABLE IF NOT EXISTS`, so this is a new idempotency pattern for the project) |
| `tradingagents/persistence/db.py` | Init code runs the new ALTERs at connection time |
| `tradingagents/persistence/store.py` | `insert_brief` gains `trigger_event_id` kwarg; new helpers `insert_queue_job`, `lease_one`, `mark_*`, `upsert_suppression`, `get_event` |
| `tradingagents/secretary/service.py` | `compose_event_alert` implementation replaces the stub; `_run_personas_parallel` extracted (shared with `compose_deep_dive`) |
| `tradingagents/default_config.py` | Adds the keys listed in §7 |

### Boundary tests (P7 discipline)

Five tests in `tests/orchestrator/`:

1. **`test_promoter_query.py`** — seed events + watchlist + suppression; assert the candidate query returns exactly the rows we expect (incl. idempotency via `LEFT JOIN queue_jobs`).
2. **`test_promoter_loop.py`** — one synthetic salient event in DB; one tick of the promoter loop produces one `queue_jobs` row + one `suppression` row, both in the same tx (verified via crash-injection: monkeypatch raises between the two writes → assert *no* partial state).
3. **`test_worker_lease.py`** — two workers racing on one job; only one wins the lease (atomic `UPDATE … RETURNING`).
4. **`test_event_alert_integration.py`** *(integration marker)* — insert a triaged event with `text=...`; run worker once with mocked LLMs that return canned persona responses; assert: 3 `runs` rows with the `queue_job_id` FK populated, 1 `briefs` row with `trigger_event_id` set, `event_alert.j2`-formatted markdown on disk.
5. **`test_guards_disabled.py`** — set every cost guard `enabled=True`, exceed each threshold, assert correct rejection. Then default config (all off), exceed thresholds, assert *no* gating + measurement is still logged.

### Smoke test (`tests/smoke/test_f4_exit_gate.py`)

The synthetic-event smoke from D8. Boots promoter + worker as threads, directly inserts a synthetic `events` row (bypassing F3 triage in CI), waits up to 60 s, asserts a brief exists for the event and `briefs.generated_ts - events.ingested_ts < 60 s` (CI-tight; the real 15-min SLA is the live observation). LLM is mocked in CI.

## 8 · Cost guards and backpressure (all `enabled=False`)

Per memory `cost-guards-disabled-by-default` and program-spec Appendix A: every guard is coded and toggleable, but ships `enabled=False`. Measurement is always on; enforcement is one config flag flip away.

### Inventory

| Guard | Layer | Scope | Default threshold | Config keys |
|---|---|---|---|---|
| **Queue backpressure** | Promoter | Pending queue depth | 20 | `trigger_backpressure_enabled`, `trigger_backpressure_max_pending` |
| **Daily rate cap** | Promoter | Jobs enqueued / 24 h | 200 | `trigger_daily_rate_enabled`, `trigger_daily_rate_max_jobs` |
| **Daily budget ceiling** | Worker | Sum of `cost_usd` / 24 h | $10 | `daily_budget_enabled`, `daily_budget_usd` |
| **Per-run token budget** | Inside graph | Tokens per single run | (existing F1 default) | `cost_guard_enabled` (F1) |

### Promoter-side guards (`tradingagents/orchestrator/guards.py`)

```python
class QueueBackpressure:
    def __init__(self, *, enabled: bool, max_pending: int):
        self.enabled = enabled
        self.max_pending = max_pending

    def gate(self, conn) -> bool:
        if not self.enabled:
            # measurement-only: log current depth, never gate
            depth = conn.execute(
                "SELECT count(*) FROM queue_jobs WHERE state IN ('queued','running')"
            ).fetchone()[0]
            log.debug("queue_depth=%d (guard disabled)", depth)
            return True
        pending = conn.execute(
            "SELECT count(*) FROM queue_jobs WHERE state IN ('queued','running')"
        ).fetchone()[0]
        if pending >= self.max_pending:
            log.warning("queue backpressure: pending=%d >= max=%d, skipping cycle", pending, self.max_pending)
            return False
        return True


class QueueRateGuard:
    """Same shape: counts queue_jobs enqueued in last 24h; gates if over max_jobs_per_day."""
```

### Worker-side guard (per-job daily budget)

Before dispatch, the worker reads:

```sql
SELECT COALESCE(SUM(cost_usd), 0)
FROM queue_jobs
WHERE date(finished_ts) = date('now')
  AND state = 'done';
```

If over `daily_budget_usd` and `daily_budget_enabled`, the worker marks the job `state='error'` with reason `daily_budget_exceeded` and continues. When `enabled=False`, the running total is logged every job (per the always-on-measurement policy) and the job dispatches.

### Per-run token budget (reused from F1)

Already applies inside the LangGraph callback (`CostGuard`); F4 just passes `cost_guard_enabled` through the persona run config. No new code.

## 9 · Exit-gate evaluator and evidence approach

### Gate criteria

Per program-spec §7-F4: *"A triage-detected event end-to-end produces a brief with no human in the loop, within ≤15 minutes of ingest. Per-job telemetry visible in SQLite."*

F4 demonstrates this two ways simultaneously:

1. **Synthetic-event smoke (CI signal).** `tests/smoke/test_f4_exit_gate.py` runs on every commit. Boots promoter+worker as threads, inserts a synthetic salient `events` row, asserts a brief lands within 60 s and `queue_jobs.cost_usd` is populated. Deterministic; proves wiring.
2. **Live observation window (6–12 h on the dev machine).** Full F3 stack runs against the user's normal watchlist. Operator captures start_ts and end_ts; the evaluator script aggregates everything in between.

### `scripts/f4_exit_gate.py`

Produces the artifact at `docs/superpowers/artifacts/2026-MM-DD-f4-exit-gate-report.md` containing:

- **Window summary.** Total events, total promotions (queue_jobs created), total briefs, total cost.
- **Per-brief table.** `event_id`, `ticker`, `salience`, `ingested_ts`, `brief_ts`, `latency_min`, `cost_usd`, `status`.
- **SLA percentiles.** p50, p95, p99 of latency over the window. **Pass criterion: p95 ≤ 15 min** (or N/A if fewer than 3 event-alert briefs in the window — see below).
- **Restart audit.** `systemctl show iic-promoter iic-worker --property=NRestarts` must be 0 over the window.
- **Synthetic-smoke result.** Pass/fail of `tests/smoke/test_f4_exit_gate.py` on the same commit.
- **Operator sign-off line.**

### Live-window evidence threshold

The realistic event-alert volume during a 6–12 h soak on a normal watchlist is 0–5 jobs. The pass rule:

- If ≥ 3 event-alert briefs landed in the window: `p95 ≤ 15 min` is the gate.
- If 1–2 briefs landed: `max latency ≤ 15 min` is the gate, and the operator confirms in the artifact that the window was "normal" (no extended quiet period).
- If 0 briefs landed: the live observation is **not** a pass signal; re-run during a more active window (or rely on the synthetic smoke + an operator-injected real event from a recent OSINT story).

### Cost outlook for the gate

- Synthetic-event smoke: ~$0 (mocked LLM in CI).
- Live observation (12 h): 0–5 event_alert jobs at ~$1–3 each (3 personas × deep_think_llm) ≈ $0–15.
- **Total expected F4 gate spend: under $20**, well inside the cost-guards-disabled regime.

### Pre-flight checklist (excerpt — full version in `ops/runbooks/f4-exit-gate.md`)

1. F3 services up and healthy (`systemctl is-active iic-sense-* iic-triage`).
2. Watchlist populated with at least the user's standing tickers (`forge watchlist list`).
3. `tickers` reference table seeded.
4. `iic-promoter.service` and `iic-worker.service` enabled and started.
5. All cost-guard flags confirmed `enabled=False` (the gate is observing the natural profile).
6. Live observation start_ts recorded.
7. Synthetic-smoke `pytest tests/smoke/test_f4_exit_gate.py` passing on the same commit.

## 10 · Risks (F4 additions to the program register)

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-F4-1 | Promoter double-fires on a single event (crash between enqueue and suppression insert) | Med | Single SQLite tx wraps both writes; even without that, the `LEFT JOIN queue_jobs ON trigger_event_id` idempotency check makes the second poll a no-op |
| R-F4-2 | Worker hangs mid-job (LLM upstream timeout, network) → job stuck in `state='running'` forever | Med | Worker enforces a per-job wall-clock cap (`worker_job_timeout_min`, default 20 min); on expiry, marks `state='error'`, frees the slot. Stale-job sweep on worker startup (`UPDATE queue_jobs SET state='error' WHERE state='running' AND started_ts < now-1h`) handles unclean restarts |
| R-F4-3 | Storm of correlated events (e.g., market-wide selloff) blows past the per-ticker 60-min cooldown across many tickers → cost spike | Med | Daily-rate guard + daily-budget guard exist and ship `enabled=False`; F5 dashboard will surface the running totals; user flips them on after the soak. Backpressure is the fallback safety net |
| R-F4-4 | Watchlist auto-promote (F3) → immediate event-alert (F4): same event causes both the promotion *and* the alert; alert fires before the promotion commits | Low | F3's triage `process_one` writes watchlist + event atomically; F4 promoter polls *after* both commits land. SQLite WAL-mode reads are serializable for this query shape |
| R-F4-5 | Personas hallucinate "the news" from the event-context-as-prompt-prefix — graph reasons about a story it didn't actually receive verbatim | Med | Boundary test asserts each persona's pm_synthesis references the event text. The injected prefix is written to `data/runs/<run_id>/event_context.md` (alongside the other artifacts) for audit. F5 brief output will include a source link / source text footer the user can cross-check |
| R-F4-6 | The 15-min SLA degrades under load (3 personas × multiple LLM calls each can take >15 min on a slow API day) | Med | `max_concurrent_jobs=1` keeps queue order honest. SLA budget: ≤ 3 min queue wait + ≤ 10 min run + ≤ 2 min synthesis+render. If runs routinely exceed 10 min, fall back to `quick_think_llm` for the synthesis call (already cheap) and consider parallelism config |
| R-F4-7 | Two workers running by mistake (operator started a dev `forge orchestrator worker` while the systemd unit was up) → both lease different jobs but contend on the same persona LLM keys | Low | Atomic lease prevents lease races. LLM concurrency is the only contention; minor at our volumes. Runbook documents one-worker-at-a-time |
| R-F4-8 | `RETURNING` clause requires sqlite >= 3.35 | Low | We already depend on sqlite-vec which requires 3.41+; transitive guarantee. Add an explicit version check at orchestrator startup |
| R-F4-9 | Live observation window happens during quiet news period → 0 organic event_alert briefs → no live SLA signal | Low–Med | Synthetic-smoke is the deterministic pass signal; the live window is a confirmation. Re-run the window during an active period if 0 briefs land (per §9) |

## 11 · Out of scope

Deliberately deferred from F4:

- **Morning digest scheduler.** Cron lives in F5 per program spec §7. Worker's `DISPATCH` map will gain `morning_digest` then.
- **Delivery.** F5 owns Telegram / email / CLI delivery. F4 writes the brief; the brief sits in `briefs/` and the `briefs` row until F5 ships.
- **Brief actions (`brief_actions` table).** F5 wires post-delivery prompts and refinements; F4 doesn't touch the table.
- **Backtest auto-triggering.** Program spec §10 ADR-NEW-3 is explicit: backtests fire only on user prompt acceptance. F4 promoter does not enqueue backtest jobs.
- **Streamlit dashboard.** F5. `forge orchestrator status` is the F4-era stand-in.
- **Multi-machine workers.** Local-first; SQLite-backed queue is single-machine by design.
- **Job priority / preemption.** All event_alert jobs are FIFO. Priority queueing slots in as a `queue_jobs.priority` column when needed; not now.
- **Cost-guard enforcement.** Measurement only per Appendix A. The user flips flags after observing the natural profile.
- **F0 OSINT Telegram channel list expansion.** Inherited from F3 as-is.

## 12 · Open questions deferred to implementation

1. **Per-job wall-clock cap default value.** 20 min is a starting guess; real measurements from F1's deep-dive runs would inform a tighter bound. Confirm at implementation against fresh deep-dive timings.
2. **Synthesis LLM tier in event_alert.** `deep_think_llm` for parity with deep-dive, or fall back to `quick_think_llm` to protect the 15-min SLA? Default to `deep_think_llm`; the daily-budget telemetry post-soak will tell us if it's affordable.
3. **What happens when a brief is *not* produced** (e.g., all 3 personas error)? Mark job `state='error'` with the per-persona errors aggregated. Don't fabricate a brief. F5 dashboard will surface these; alerting on them is post-soak work.
4. **Stale-lease sweep frequency.** On worker boot only, or also via a `systemd .timer` like F3's watchlist sweep? Probably on-boot is enough at our volumes; revisit if errors accumulate.
5. **Multi-ticker events.** An event can have multiple `event_ticker` rows. Today's promoter enqueues one job per qualifying ticker — that means the same event could fire 3 separate alerts if 3 watchlist tickers match. Acceptable for V1 (rare; suppression cooldown is per-ticker anyway), but confirm during implementation whether to dedupe by event_id at promotion time.
6. **`primary_ticker` selection.** When an event has multiple qualifying tickers, which one is the "primary" for the brief? Currently the highest-confidence ticker from `event_ticker`; revisit if the brief format ever needs multi-ticker prominence.

---

*End of IIC-FORGE-07. The companion implementation plan (IIC-FORGE-07-plan) follows from `superpowers:writing-plans`.*
