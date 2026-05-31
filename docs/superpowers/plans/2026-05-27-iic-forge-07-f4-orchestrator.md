# IIC-FORGE-07 — F4 Autonomous Trigger Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship F4 of the IIC-FORGE program — an autonomous trigger loop that turns F3's triaged events into event-alert briefs end-to-end. A long-lived promoter polls the `events` table for watchlist-relevant high-salience events and enqueues `queue_jobs` rows; a long-lived worker leases jobs and invokes `Secretary.compose_event_alert(event_id, ticker)` (replacing the F1 `NotImplementedError` stub). Briefs land in `briefs/<brief_id>.md` with the new `trigger_event_id` column linking back to the source event.

**Architecture:** Two new systemd services — `iic-promoter.service` (polls `events` every 10s, applies trigger rule `salience ≥ 0.7 AND confidence ≥ 0.8 AND ticker ∈ watchlist`, enqueues + upserts `suppression` cooldown in one transaction) and `iic-worker.service` (polls `queue_jobs` every 2s, leases one job at a time via atomic `UPDATE … RETURNING`, dispatches by `job_type`). For `event_alert` job_type, the worker calls `Secretary.compose_event_alert(event_id, ticker, job_id)` which runs three personas in parallel via the F1 `ThreadPoolExecutor` pattern, synthesizes a brief with consensus/divergence/recommendation, renders the terse `event_alert.j2` template, and writes the brief. All four cost/backpressure guards (queue backpressure, daily rate, daily budget, per-run token) ship `enabled=False` per Appendix A — measurement always on.

**Tech Stack:** Python 3.10+, existing SQLite store (`queue_jobs`, `suppression`, `briefs`, `runs`, `costs` tables already in F1 schema), existing `Secretary` + `synthesize_brief` (F1), existing `_run_one_persona` pattern (F1's `cli/deepdive.py`), existing systemd-unit conventions (F3). **No new runtime deps.** **New test deps:** `freezegun>=1.4` (deterministic time control for cooldown tests).

**Prerequisites:**
- F1 + F2 + F3 complete on `main` (commits up to `91c9426` shipped). The plan currently lives on `feat/iic-forge-06-f3`; merge F3 to `main` and branch off as `feat/iic-forge-07-f4` before starting.
- Approved spec: [docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md](../specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md).
- DeepSeek API key configured in `.env` (used by personas during `compose_event_alert`).
- Working tree on a feature branch (`feat/iic-forge-07-f4`).

**Pre-flight (one-time):**

```bash
cd /home/ziwei-huang/TradingAgents/TradingAgents
git status                                                  # working tree clean, on feat/iic-forge-07-f4
python -c "import sys; print(sys.version_info >= (3, 10))"  # True
python -c "import sqlite3; print(sqlite3.sqlite_version)"   # >= 3.41 (sqlite-vec transitive)
pytest --version                                            # >= 7.0
```

If `sqlite3.sqlite_version < 3.35` the `RETURNING` clause will fail — abort and upgrade sqlite before proceeding.

---

## File Structure (locked in before tasks start)

**Created in this plan:**

| Path | Responsibility |
|---|---|
| `tradingagents/orchestrator/__init__.py` | Package marker |
| `tradingagents/orchestrator/queue_store.py` | Low-level SQL helpers — `insert_queue_job`, `lease_one`, `mark_done`, `mark_error`, `sweep_stale_leases`, `daily_cost_total`, `pending_count`, `daily_enqueue_count` |
| `tradingagents/orchestrator/guards.py` | `QueueBackpressure`, `QueueRateGuard`, `DailyBudgetGuard` — all ship `enabled=False` |
| `tradingagents/orchestrator/candidates.py` | `fetch_candidates(conn, …)` — the promoter's SELECT-LEFT-JOIN-LEFT-JOIN query |
| `tradingagents/orchestrator/promoter.py` | Promoter loop + `__main__` systemd entry |
| `tradingagents/orchestrator/dispatch.py` | `DISPATCH` map + `dispatch_event_alert(conn, job, secretary)` |
| `tradingagents/orchestrator/worker.py` | Worker loop, leasing, dispatch routing, cost-guard hooks + `__main__` systemd entry |
| `tradingagents/secretary/persona_runner.py` | Shared persona-fan-out helper extracted from `cli/deepdive.py` |
| `tradingagents/secretary/templates/event_alert.j2` | Terse event-alert brief template |
| `ops/systemd/iic-promoter.service` | systemd unit for the promoter |
| `ops/systemd/iic-worker.service` | systemd unit for the worker |
| `ops/runbooks/f4-exit-gate.md` | Pre-flight + run procedure for the F4 exit gate |
| `scripts/f4_exit_gate.py` | Reads `queue_jobs` + `briefs` + `events` + `systemctl` for a window; renders SLA percentiles + per-job table |
| `tests/orchestrator/__init__.py` | empty |
| `tests/orchestrator/test_queue_store.py` | Insert / lease / mark_done / mark_error round-trips |
| `tests/orchestrator/test_lease_atomicity.py` | Two workers racing on one job — only one wins |
| `tests/orchestrator/test_guards.py` | All three guards: disabled=passthrough+log; enabled=correct gating |
| `tests/orchestrator/test_candidates.py` | Candidate query: threshold, suppression, idempotency LEFT-JOIN |
| `tests/orchestrator/test_promoter_loop.py` | One tick → one queue_jobs + one suppression row, both in same tx (crash-injection) |
| `tests/orchestrator/test_event_context_injection.py` | Config `event_context` → initial state `event_context_text` → audit MD under `data/runs/<run_id>/event_context.md` |
| `tests/orchestrator/test_persona_runner.py` | `run_personas_parallel` returns list of run_ids matching personas count |
| `tests/orchestrator/test_event_alert_template.py` | Renders given a synthesis + persona_runs + event payload |
| `tests/orchestrator/test_compose_event_alert.py` | Integration with mocked LLM: 3 runs + 1 brief + trigger_event_id wiring |
| `tests/orchestrator/test_worker_dispatch.py` | Dispatch routes event_alert; unknown job_type → mark_error |
| `tests/orchestrator/test_worker_loop.py` | Worker drains the queue and stops cleanly on shutdown signal |
| `tests/orchestrator/test_stale_lease_sweep.py` | Boot-time sweep marks stale `running` jobs as `error` |
| `tests/orchestrator/test_schema_init_idempotent.py` | Schema init twice = no-op (the ALTER idempotency) |
| `tests/cli/test_forge_orchestrator.py` | `forge orchestrator promoter|worker|status` smoke |
| `tests/smoke/test_f4_exit_gate.py` | Boots promoter+worker as threads, injects synthetic event, asserts brief ≤ 60s |
| `tests/test_default_config_f4.py` | F4 keys present with documented defaults |

**Modified in this plan:**

| Path | Change |
|---|---|
| `tradingagents/persistence/schema.sql` | Append 5 `ALTER TABLE … ADD COLUMN` statements + `CREATE INDEX IF NOT EXISTS idx_queue_jobs_trigger_event` |
| `tradingagents/persistence/db.py` | Wrap the schema-script `executescript` with per-statement application that swallows `duplicate column name` errors |
| `tradingagents/persistence/store.py` | `insert_brief` gains `trigger_event_id` kwarg; new `get_event`, `upsert_suppression`, `get_brief` helpers |
| `tradingagents/secretary/service.py` | `compose_event_alert` real implementation replacing the `NotImplementedError`; `compose_deep_dive` delegates persona fan-out to the new `persona_runner.run_personas_parallel` (no behavior change) |
| `tradingagents/secretary/synthesis.py` | `synthesize_brief` gains optional `event_context: str | None = None` kwarg threaded into the prompt; default behavior unchanged |
| `cli/deepdive.py` | `_run_one_persona` accepts optional `event_context` and `queue_job_id`; persona-fan-out loop moves to `persona_runner.run_personas_parallel` |
| `cli/forge.py` | Add `forge orchestrator promoter|worker|status` sub-app |
| `tradingagents/default_config.py` | Add F4 keys + `TRADINGAGENTS_ORCHESTRATOR_ENABLED` env override |
| `tradingagents/graph/cost_callback.py` | (No change; reused as-is.) |
| `tradingagents/graph/run_recorder.py` | `RunRecorder.__init__` accepts optional `queue_job_id`; `start()` threads it into `store.insert_run` |
| `tradingagents/graph/trading_graph.py` | Reads `config["queue_job_id"]` and `config["event_context"]` from the overlay; passes the former to `RunRecorder`, the latter into the initial graph state as `event_context_text` |

---

## Cross-cutting conventions

- **Tests:** pytest with markers `unit` (default, fast, isolated), `integration` (real API / external service), `smoke` (quick end-to-end).
- **Commits:** one per task. Format: `feat(<scope>): <subject>` matching repo style.
- **Cost guards:** every guard ships `enabled: bool = False` default. Measurement always on. (See [saved memory](../../../.claude/projects/-home-ziwei-huang-TradingAgents/memory/cost-guards-disabled-by-default.md).)
- **Imports:** absolute, rooted at `tradingagents.` and `cli.`.
- **Schema:** append-only. Only `ALTER TABLE … ADD COLUMN` and `CREATE INDEX IF NOT EXISTS`. Existing F1/F2/F3 columns are untouched.
- **Time:** All timestamps are `datetime.now(timezone.utc).isoformat()` strings; SQL comparisons use `datetime('now')`.
- **No new runtime deps.** `freezegun` is `dev`-only (used in suppression-cooldown tests).
- **DB connection in tests:** always use `connect(str(tmp_path / "iic.db"))` to keep state isolated; the schema init is idempotent.

---

## Task 1: F4 default_config keys

**Files:**
- Modify: `tradingagents/default_config.py`
- Test: `tests/test_default_config_f4.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_default_config_f4.py`:

```python
import pytest


@pytest.mark.unit
def test_default_config_has_f4_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    # Orchestrator master switch + cadences
    assert C["orchestrator_enabled"] is False
    assert C["promoter_poll_interval_s"] == 10
    assert C["promoter_batch_size"] == 50
    assert C["alert_cooldown_min"] == 60
    assert C["alert_salience_threshold"] == 0.7
    assert C["alert_ticker_confidence_threshold"] == 0.8
    assert C["worker_poll_interval_s"] == 2
    assert C["worker_job_timeout_min"] == 20
    assert C["max_concurrent_jobs"] == 1
    # Cost guards — all off
    assert C["trigger_backpressure_enabled"] is False
    assert C["trigger_backpressure_max_pending"] == 20
    assert C["trigger_daily_rate_enabled"] is False
    assert C["trigger_daily_rate_max_jobs"] == 200
    assert C["daily_budget_enabled"] is False
    assert C["daily_budget_usd"] == 10.0


@pytest.mark.unit
def test_env_override_orchestrator_enabled(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_ORCHESTRATOR_ENABLED", "1")
    # Re-import to re-evaluate env overrides (DEFAULT_CONFIG is built at import).
    import importlib
    import tradingagents.default_config as m
    importlib.reload(m)
    assert m.DEFAULT_CONFIG["orchestrator_enabled"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_default_config_f4.py -v
```

Expected: FAIL — keys missing.

- [ ] **Step 3: Add the keys**

In `tradingagents/default_config.py`:

1. Extend `_ENV_OVERRIDES` (around line 23) — add ONE new row:

```python
    "TRADINGAGENTS_ORCHESTRATOR_ENABLED": "orchestrator_enabled",
```

2. Insert the F4 block in the `DEFAULT_CONFIG` dict, immediately after the F3 block (right after `"sensing_adapters_enabled": { … },`):

```python
    # IIC-FORGE F4 — autonomous trigger loop (orchestrator)
    "orchestrator_enabled": False,
    "promoter_poll_interval_s": 10,
    "promoter_batch_size": 50,
    "alert_cooldown_min": 60,
    "alert_salience_threshold": 0.7,
    "alert_ticker_confidence_threshold": 0.8,
    "worker_poll_interval_s": 2,
    "worker_job_timeout_min": 20,
    "max_concurrent_jobs": 1,
    # Cost guards (program-spec Appendix A: enabled=False during F0–F5)
    "trigger_backpressure_enabled": False,
    "trigger_backpressure_max_pending": 20,
    "trigger_daily_rate_enabled": False,
    "trigger_daily_rate_max_jobs": 200,
    "daily_budget_enabled": False,
    "daily_budget_usd": 10.0,
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_default_config_f4.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tests/test_default_config_f4.py
git commit -m "config: add F4 orchestrator defaults (all guards enabled=False)"
```

---

## Task 2: Schema additions — 5 ALTER + 1 INDEX, idempotent

**Files:**
- Modify: `tradingagents/persistence/schema.sql`
- Modify: `tradingagents/persistence/db.py`
- Test: `tests/orchestrator/test_schema_init_idempotent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/__init__.py` (empty) and `tests/orchestrator/test_schema_init_idempotent.py`:

```python
import pytest
from tradingagents.persistence.db import connect


@pytest.mark.unit
def test_queue_jobs_has_f4_columns(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = {c[1] for c in conn.execute("PRAGMA table_info(queue_jobs)")}
    assert {"trigger_event_id", "run_ids", "brief_id", "cost_usd", "error"} <= cols


@pytest.mark.unit
def test_briefs_has_trigger_event_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = {c[1] for c in conn.execute("PRAGMA table_info(briefs)")}
    assert "trigger_event_id" in cols


@pytest.mark.unit
def test_runs_has_queue_job_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = {c[1] for c in conn.execute("PRAGMA table_info(runs)")}
    assert "queue_job_id" in cols


@pytest.mark.unit
def test_idx_queue_jobs_trigger_event_present(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    idx_names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )}
    assert "idx_queue_jobs_trigger_event" in idx_names


@pytest.mark.unit
def test_schema_init_is_idempotent(tmp_path):
    """Running connect() twice on the same DB must not raise."""
    db = str(tmp_path / "iic.db")
    conn1 = connect(db)
    conn1.close()
    # Second open re-runs schema.sql; ALTER TABLE ADD COLUMN must be swallowed.
    conn2 = connect(db)
    cols = {c[1] for c in conn2.execute("PRAGMA table_info(queue_jobs)")}
    assert "trigger_event_id" in cols
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_schema_init_idempotent.py -v
```

Expected: FAIL — F4 columns absent, and the second `connect()` may also fail with `duplicate column name` on subsequent runs.

- [ ] **Step 3: Append the F4 schema block**

Append to `tradingagents/persistence/schema.sql` (at the very end):

```sql
-- ============================================================
-- F4 orchestrator append-only columns (added by IIC-FORGE-07)
-- ============================================================
-- NOTE: ALTER TABLE ADD COLUMN is NOT idempotent in SQLite. The db.py
-- migration layer wraps these statements to swallow "duplicate column
-- name" errors, allowing connect() to be called repeatedly. Do NOT add
-- IF NOT EXISTS — sqlite does not support it on ALTER TABLE.

ALTER TABLE queue_jobs ADD COLUMN trigger_event_id  TEXT REFERENCES events(event_id);
ALTER TABLE queue_jobs ADD COLUMN run_ids           TEXT;       -- JSON array
ALTER TABLE queue_jobs ADD COLUMN brief_id          TEXT REFERENCES briefs(brief_id);
ALTER TABLE queue_jobs ADD COLUMN cost_usd          REAL;
ALTER TABLE queue_jobs ADD COLUMN error             TEXT;

ALTER TABLE briefs     ADD COLUMN trigger_event_id  TEXT REFERENCES events(event_id);

ALTER TABLE runs       ADD COLUMN queue_job_id      INTEGER REFERENCES queue_jobs(job_id);

CREATE INDEX IF NOT EXISTS idx_queue_jobs_trigger_event
    ON queue_jobs(trigger_event_id);
CREATE INDEX IF NOT EXISTS idx_queue_jobs_state_enqueued
    ON queue_jobs(state, enqueued_ts);
```

- [ ] **Step 4: Make schema application tolerate `ALTER` duplicates**

In `tradingagents/persistence/db.py`, replace the line `conn.executescript(f.read())` (around line 49) with a per-statement applier that swallows the `duplicate column name` error:

```python
    # Schema. CREATE TABLE/INDEX IF NOT EXISTS are idempotent; ALTER TABLE
    # ADD COLUMN is NOT — sqlite raises "duplicate column name" on a re-run.
    # We split on `;` and apply each statement, suppressing only that error.
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        script = f.read()
    for stmt in _split_sql_statements(script):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column name" in msg:
                continue   # ALTER TABLE re-run — column already present
            raise
```

And add this helper near the top of `db.py` (after the imports, before `_SCHEMA_PATH`):

```python
def _split_sql_statements(script: str) -> list[str]:
    """Naive splitter: SQLite has no `;` inside our schema strings or comments
    that would confuse a split. PRAGMAs and CREATE/ALTER each end with `;`."""
    out: list[str] = []
    buf: list[str] = []
    for line in script.splitlines():
        stripped = line.split("--", 1)[0]   # strip line comments before checking
        buf.append(line)
        if ";" in stripped:
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_schema_init_idempotent.py tests/persistence/ -v
```

Expected: all PASS. The existing persistence tests should still pass — the per-statement applier is equivalent to `executescript` for our schema.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/persistence/schema.sql tradingagents/persistence/db.py tests/orchestrator/__init__.py tests/orchestrator/test_schema_init_idempotent.py
git commit -m "schema(f4): 5 ALTER ADD COLUMN + queue_jobs indexes; per-statement idempotent applier"
```

---

## Task 3: Store helpers — `insert_brief(trigger_event_id=)`, `get_event`, `upsert_suppression`, `get_brief`

**Files:**
- Modify: `tradingagents/persistence/store.py`
- Test: `tests/persistence/test_store_f4.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/persistence/test_store_f4.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.unit
def test_insert_brief_threads_trigger_event_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts=_now(), salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts=_now(), content_path="briefs/b1.md",
        run_ids=["r1"], parent_brief_id=None, trigger_event_id="ev1",
    )
    row = conn.execute(
        "SELECT trigger_event_id FROM briefs WHERE brief_id='b1'"
    ).fetchone()
    assert row["trigger_event_id"] == "ev1"


@pytest.mark.unit
def test_insert_brief_default_trigger_event_id_none(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b2", mode="deep_dive", scope="AAPL",
        generated_ts=_now(), content_path="briefs/b2.md",
        run_ids=["r1"], parent_brief_id=None,
    )
    row = conn.execute(
        "SELECT trigger_event_id FROM briefs WHERE brief_id='b2'"
    ).fetchone()
    assert row["trigger_event_id"] is None


@pytest.mark.unit
def test_get_event_returns_dict_with_text_path(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.8,
                       raw_path="data/events/ev1.json",
                       status="triaged", deduped_of=None)
    ev = store.get_event(conn, event_id="ev1")
    assert ev["event_id"] == "ev1"
    assert ev["raw_path"] == "data/events/ev1.json"
    assert ev["salience"] == pytest.approx(0.8)


@pytest.mark.unit
def test_get_event_missing_returns_none(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    assert store.get_event(conn, event_id="missing") is None


@pytest.mark.unit
def test_upsert_suppression_inserts_then_updates(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    until = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    store.upsert_suppression(
        conn, key="event_alert:AAPL", until_ts=until,
        reason="alert_cooldown event_id=ev1", created_by="promoter",
    )
    row = conn.execute(
        "SELECT * FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()
    assert row["until_ts"] == until

    # second call extends the cooldown
    new_until = (datetime.now(timezone.utc) + timedelta(minutes=120)).isoformat()
    store.upsert_suppression(
        conn, key="event_alert:AAPL", until_ts=new_until,
        reason="alert_cooldown event_id=ev2", created_by="promoter",
    )
    row2 = conn.execute(
        "SELECT * FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()
    assert row2["until_ts"] == new_until
    assert row2["reason"] == "alert_cooldown event_id=ev2"


@pytest.mark.unit
def test_get_brief_round_trip(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts=_now(), content_path="briefs/b1.md",
        run_ids=["r1", "r2"], parent_brief_id=None,
        trigger_event_id="ev1",
    )
    b = store.get_brief(conn, brief_id="b1")
    assert b["mode"] == "event_alert"
    assert b["trigger_event_id"] == "ev1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persistence/test_store_f4.py -v
```

Expected: FAIL — helpers / kwarg don't exist yet.

- [ ] **Step 3: Extend `store.py`**

In `tradingagents/persistence/store.py`:

1. Replace `insert_brief` with a version that accepts `trigger_event_id`:

```python
def insert_brief(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    mode: str,
    scope: str,
    generated_ts: str,
    content_path: str,
    run_ids: Iterable[str],
    parent_brief_id: Optional[str] = None,
    trigger_event_id: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO briefs (brief_id, mode, scope, generated_ts, content_path, "
        "run_ids, parent_brief_id, trigger_event_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (brief_id, mode, scope, generated_ts, content_path,
         json.dumps(list(run_ids)), parent_brief_id, trigger_event_id),
    )
    conn.commit()
```

2. Append these helpers at the end of the file (after the F3 helpers block):

```python
# --------------------------------------------------------------------
# F4 helpers — events lookup / suppression / briefs lookup
# --------------------------------------------------------------------

def get_event(
    conn: sqlite3.Connection, *, event_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()


def upsert_suppression(
    conn: sqlite3.Connection,
    *,
    key: str,
    until_ts: str,
    reason: Optional[str],
    created_by: str,
) -> None:
    conn.execute(
        "INSERT INTO suppression (key, until_ts, reason, created_by) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET "
        "until_ts = excluded.until_ts, "
        "reason = excluded.reason, "
        "created_by = excluded.created_by",
        (key, until_ts, reason, created_by),
    )
    conn.commit()


def get_brief(
    conn: sqlite3.Connection, *, brief_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/persistence/test_store_f4.py tests/persistence/ -v
```

Expected: PASS (6 new tests + all existing persistence tests).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/store.py tests/persistence/test_store_f4.py
git commit -m "persist(f4): insert_brief(trigger_event_id=) + get_event / upsert_suppression / get_brief"
```

---

## Task 4: Queue-store helpers — insert / lease / mark_done / mark_error / sweep / aggregates

**Files:**
- Create: `tradingagents/orchestrator/__init__.py`
- Create: `tradingagents/orchestrator/queue_store.py`
- Test: `tests/orchestrator/test_queue_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tradingagents/orchestrator/__init__.py` (empty).

Create `tests/orchestrator/test_queue_store.py`:

```python
import json
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.insert_event(c, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    return c


@pytest.mark.unit
def test_insert_queue_job_returns_id(conn):
    from tradingagents.orchestrator.queue_store import insert_queue_job
    job_id = insert_queue_job(
        conn, job_type="event_alert",
        payload=json.dumps({"event_id": "ev1", "ticker": "AAPL"}),
        trigger_event_id="ev1",
    )
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id = ?", (job_id,)).fetchone()
    assert row["state"] == "queued"
    assert row["trigger_event_id"] == "ev1"


@pytest.mark.unit
def test_lease_one_returns_none_on_empty(conn):
    from tradingagents.orchestrator.queue_store import lease_one
    assert lease_one(conn) is None


@pytest.mark.unit
def test_lease_one_flips_state(conn):
    from tradingagents.orchestrator.queue_store import insert_queue_job, lease_one
    job_id = insert_queue_job(conn, job_type="event_alert",
                              payload="{}", trigger_event_id="ev1")
    leased = lease_one(conn)
    assert leased["job_id"] == job_id
    assert leased["state"] == "running"
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job_id,)).fetchone()
    assert row["state"] == "running"
    assert row["started_ts"] is not None


@pytest.mark.unit
def test_mark_done_records_outputs(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, mark_done,
    )
    insert_queue_job(conn, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    job = lease_one(conn)
    mark_done(conn, job_id=job["job_id"], run_ids=["r1", "r2"],
              brief_id="b1", cost_usd=0.45)
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["state"] == "done"
    assert row["brief_id"] == "b1"
    assert row["cost_usd"] == pytest.approx(0.45)
    assert json.loads(row["run_ids"]) == ["r1", "r2"]
    assert row["finished_ts"] is not None


@pytest.mark.unit
def test_mark_error_records_exception_message(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, mark_error,
    )
    insert_queue_job(conn, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    job = lease_one(conn)
    mark_error(conn, job_id=job["job_id"], error_msg="LLM upstream timeout")
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["state"] == "error"
    assert row["error"] == "LLM upstream timeout"


@pytest.mark.unit
def test_pending_count(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, pending_count,
    )
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    assert pending_count(conn) == 2
    lease_one(conn)
    assert pending_count(conn) == 2  # leased ('running') still counts as pending


@pytest.mark.unit
def test_daily_enqueue_count(conn):
    from tradingagents.orchestrator.queue_store import insert_queue_job, daily_enqueue_count
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    assert daily_enqueue_count(conn) == 2


@pytest.mark.unit
def test_daily_cost_total_sums_done_jobs(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, mark_done, daily_cost_total,
    )
    for _ in range(3):
        insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
        job = lease_one(conn)
        mark_done(conn, job_id=job["job_id"], run_ids=[], brief_id=None, cost_usd=1.25)
    assert daily_cost_total(conn) == pytest.approx(3.75)


@pytest.mark.unit
def test_sweep_stale_leases_marks_old_running_as_error(conn):
    from tradingagents.orchestrator.queue_store import (
        insert_queue_job, lease_one, sweep_stale_leases,
    )
    insert_queue_job(conn, job_type="event_alert", payload="{}", trigger_event_id="ev1")
    job = lease_one(conn)
    # Manually backdate started_ts to 2h ago.
    conn.execute(
        "UPDATE queue_jobs SET started_ts = datetime('now', '-2 hour') "
        "WHERE job_id = ?", (job["job_id"],),
    )
    conn.commit()
    n = sweep_stale_leases(conn, max_age_seconds=3600)
    assert n == 1
    row = conn.execute("SELECT * FROM queue_jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["state"] == "error"
    assert "stale_lease" in row["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_queue_store.py -v
```

Expected: ImportError on `queue_store`.

- [ ] **Step 3: Implement `queue_store.py`**

Create `tradingagents/orchestrator/queue_store.py`:

```python
"""Low-level SQL helpers over the queue_jobs table.

Each function takes an open sqlite3.Connection and commits before returning,
EXCEPT lease_one which relies on the implicit BEGIN IMMEDIATE inside
``with conn:`` for atomicity (and commits at the end of the with-block).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_queue_job(
    conn: sqlite3.Connection,
    *,
    job_type: str,
    payload: str,                      # already-serialized JSON string
    trigger_event_id: Optional[str],
) -> int:
    cur = conn.execute(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts, "
        "trigger_event_id) VALUES (?, ?, 'queued', ?, ?)",
        (job_type, payload, _now_iso(), trigger_event_id),
    )
    conn.commit()
    return cur.lastrowid


def lease_one(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Atomically claim the oldest queued job. Returns the updated row or None.

    Uses ``UPDATE … RETURNING`` (sqlite >= 3.35). The implicit BEGIN IMMEDIATE
    from ``with conn:`` ensures two concurrent leasers cannot both win the
    same job — the second sees the row already updated and returns nothing.
    """
    with conn:
        row = conn.execute(
            """
            UPDATE queue_jobs
               SET state = 'running',
                   started_ts = ?
             WHERE job_id = (
                 SELECT job_id FROM queue_jobs
                  WHERE state = 'queued'
                  ORDER BY job_id
                  LIMIT 1
             )
         RETURNING job_id, job_type, payload, trigger_event_id, state, started_ts
            """,
            (_now_iso(),),
        ).fetchone()
    return row


def mark_done(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    run_ids: Iterable[str],
    brief_id: Optional[str],
    cost_usd: Optional[float],
) -> None:
    conn.execute(
        "UPDATE queue_jobs SET state = 'done', finished_ts = ?, "
        "run_ids = ?, brief_id = ?, cost_usd = ? WHERE job_id = ?",
        (_now_iso(), json.dumps(list(run_ids)), brief_id, cost_usd, job_id),
    )
    conn.commit()


def mark_error(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    error_msg: str,
) -> None:
    conn.execute(
        "UPDATE queue_jobs SET state = 'error', finished_ts = ?, error = ? "
        "WHERE job_id = ?",
        (_now_iso(), error_msg, job_id),
    )
    conn.commit()


def pending_count(conn: sqlite3.Connection) -> int:
    """Jobs currently queued OR running (anything not yet terminal)."""
    return conn.execute(
        "SELECT COUNT(*) FROM queue_jobs WHERE state IN ('queued', 'running')"
    ).fetchone()[0]


def daily_enqueue_count(conn: sqlite3.Connection) -> int:
    """Jobs enqueued in the last 24h (regardless of current state)."""
    return conn.execute(
        "SELECT COUNT(*) FROM queue_jobs "
        "WHERE enqueued_ts > datetime('now', '-1 day')"
    ).fetchone()[0]


def daily_cost_total(conn: sqlite3.Connection) -> float:
    """Sum of cost_usd for jobs finished today (UTC date)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM queue_jobs "
        "WHERE state = 'done' AND date(finished_ts) = date('now')"
    ).fetchone()
    return float(row[0])


def sweep_stale_leases(
    conn: sqlite3.Connection, *, max_age_seconds: int = 3600
) -> int:
    """Mark any 'running' job older than max_age_seconds as 'error'.

    Used by the worker at boot to clean up unclean shutdowns.
    Returns the number of rows swept.
    """
    n = conn.execute(
        "UPDATE queue_jobs SET state = 'error', finished_ts = ?, "
        "error = 'stale_lease_swept_on_boot' "
        "WHERE state = 'running' AND started_ts < datetime('now', ?)",
        (_now_iso(), f"-{max_age_seconds} seconds"),
    ).rowcount
    conn.commit()
    return n
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_queue_store.py -v
```

Expected: all 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/__init__.py tradingagents/orchestrator/queue_store.py tests/orchestrator/test_queue_store.py
git commit -m "orchestrator(queue_store): insert/lease/mark/sweep + aggregates over queue_jobs"
```

---

## Task 5: Lease atomicity — race two leasers, only one wins

**Files:**
- Test: `tests/orchestrator/test_lease_atomicity.py`

This task adds the boundary contract test. No production code changes.

- [ ] **Step 1: Write the test**

Create `tests/orchestrator/test_lease_atomicity.py`:

```python
import threading
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator.queue_store import insert_queue_job, lease_one


@pytest.mark.unit
def test_two_leasers_race_only_one_wins(tmp_path):
    """Two threads call lease_one on the same DB; exactly one returns the job."""
    db_path = str(tmp_path / "iic.db")
    # Seed one event and one job.
    boot = connect(db_path)
    store.insert_event(boot, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    insert_queue_job(boot, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    boot.close()

    results: list = []
    barrier = threading.Barrier(2)

    def worker():
        c = connect(db_path)
        barrier.wait()
        r = lease_one(c)
        results.append(r)
        c.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1, f"expected 1 winner, got {results}"
    assert len(losers) == 1
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/orchestrator/test_lease_atomicity.py -v
```

Expected: PASS. The `UPDATE … RETURNING` inside `with conn:` (which begins a write tx) guarantees atomicity. If this test ever fails, the lease implementation is broken — investigate sqlite version (`PRAGMA compile_options` / `sqlite_version()`).

- [ ] **Step 3: Commit**

```bash
git add tests/orchestrator/test_lease_atomicity.py
git commit -m "test(orchestrator): boundary check — lease_one is atomic across racing threads"
```

---

## Task 6: Cost guards — QueueBackpressure / QueueRateGuard / DailyBudgetGuard

**Files:**
- Create: `tradingagents/orchestrator/guards.py`
- Test: `tests/orchestrator/test_guards.py`

All three guards ship `enabled=False`. Per Appendix A, measurement is always on (each guard logs the current measurement even when disabled).

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_guards.py`:

```python
import logging
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store as qs


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.insert_event(c, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    return c


# --------------------- QueueBackpressure ---------------------

@pytest.mark.unit
def test_backpressure_disabled_always_passes(conn, caplog):
    from tradingagents.orchestrator.guards import QueueBackpressure
    g = QueueBackpressure(enabled=False, max_pending=1)
    for _ in range(3):
        qs.insert_queue_job(conn, job_type="event_alert",
                            payload="{}", trigger_event_id="ev1")
    caplog.set_level(logging.DEBUG, logger="tradingagents.orchestrator.guards")
    assert g.gate(conn) is True
    # measurement-on policy: depth must appear in logs
    assert any("queue_depth=3" in r.message for r in caplog.records)


@pytest.mark.unit
def test_backpressure_enabled_gates_above_threshold(conn):
    from tradingagents.orchestrator.guards import QueueBackpressure
    g = QueueBackpressure(enabled=True, max_pending=2)
    for _ in range(2):
        qs.insert_queue_job(conn, job_type="event_alert",
                            payload="{}", trigger_event_id="ev1")
    assert g.gate(conn) is False   # 2 >= max=2 → gate closed


@pytest.mark.unit
def test_backpressure_enabled_passes_below_threshold(conn):
    from tradingagents.orchestrator.guards import QueueBackpressure
    g = QueueBackpressure(enabled=True, max_pending=5)
    qs.insert_queue_job(conn, job_type="event_alert",
                        payload="{}", trigger_event_id="ev1")
    assert g.gate(conn) is True


# --------------------- QueueRateGuard ---------------------

@pytest.mark.unit
def test_rate_disabled_passes_always(conn):
    from tradingagents.orchestrator.guards import QueueRateGuard
    g = QueueRateGuard(enabled=False, max_per_day=1)
    qs.insert_queue_job(conn, job_type="event_alert",
                        payload="{}", trigger_event_id="ev1")
    qs.insert_queue_job(conn, job_type="event_alert",
                        payload="{}", trigger_event_id="ev1")
    assert g.gate(conn) is True


@pytest.mark.unit
def test_rate_enabled_blocks_when_over_limit(conn):
    from tradingagents.orchestrator.guards import QueueRateGuard
    g = QueueRateGuard(enabled=True, max_per_day=2)
    for _ in range(2):
        qs.insert_queue_job(conn, job_type="event_alert",
                            payload="{}", trigger_event_id="ev1")
    assert g.gate(conn) is False


# --------------------- DailyBudgetGuard ---------------------

@pytest.mark.unit
def test_budget_disabled_never_blocks(conn):
    from tradingagents.orchestrator.guards import DailyBudgetGuard
    g = DailyBudgetGuard(enabled=False, daily_usd=1.00)
    qs.insert_queue_job(conn, job_type="event_alert",
                        payload="{}", trigger_event_id="ev1")
    job = qs.lease_one(conn)
    qs.mark_done(conn, job_id=job["job_id"], run_ids=[], brief_id=None, cost_usd=10.0)
    assert g.gate(conn) is True


@pytest.mark.unit
def test_budget_enabled_blocks_after_threshold(conn):
    from tradingagents.orchestrator.guards import DailyBudgetGuard
    g = DailyBudgetGuard(enabled=True, daily_usd=5.00)
    # Accumulate $5 of completed work
    for _ in range(5):
        qs.insert_queue_job(conn, job_type="event_alert",
                            payload="{}", trigger_event_id="ev1")
        job = qs.lease_one(conn)
        qs.mark_done(conn, job_id=job["job_id"], run_ids=[],
                     brief_id=None, cost_usd=1.0)
    assert g.gate(conn) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_guards.py -v
```

Expected: ImportError on `guards`.

- [ ] **Step 3: Implement `guards.py`**

Create `tradingagents/orchestrator/guards.py`:

```python
"""Cost / rate / backpressure guards for the F4 orchestrator.

Per IIC-FORGE program design Appendix A:
- Every guard is coded and toggleable.
- All ship with ``enabled=False`` during F0–F5.
- Measurement is always on, even when enforcement is disabled.

Flip ``enabled=True`` (via config flag or env override) after observing
the natural cost/rate profile from the F5 dashboard.
"""

from __future__ import annotations

import logging
import sqlite3

from tradingagents.orchestrator import queue_store


log = logging.getLogger(__name__)


class QueueBackpressure:
    """Promoter-side. Blocks new enqueues when (queued+running) >= max_pending."""

    def __init__(self, *, enabled: bool, max_pending: int) -> None:
        self.enabled = enabled
        self.max_pending = max_pending

    def gate(self, conn: sqlite3.Connection) -> bool:
        depth = queue_store.pending_count(conn)
        if not self.enabled:
            # measurement-only — never gate, always log
            log.debug("queue_depth=%d (backpressure guard disabled)", depth)
            return True
        if depth >= self.max_pending:
            log.warning(
                "queue backpressure: depth=%d >= max=%d, skipping cycle",
                depth, self.max_pending,
            )
            return False
        return True


class QueueRateGuard:
    """Promoter-side. Blocks new enqueues when daily-enqueue count >= max_per_day."""

    def __init__(self, *, enabled: bool, max_per_day: int) -> None:
        self.enabled = enabled
        self.max_per_day = max_per_day

    def gate(self, conn: sqlite3.Connection) -> bool:
        n = queue_store.daily_enqueue_count(conn)
        if not self.enabled:
            log.debug("daily_enqueue=%d (rate guard disabled)", n)
            return True
        if n >= self.max_per_day:
            log.warning(
                "queue rate guard: %d enqueues today >= max=%d, skipping",
                n, self.max_per_day,
            )
            return False
        return True


class DailyBudgetGuard:
    """Worker-side. Blocks new dispatch when SUM(cost_usd) today >= daily_usd."""

    def __init__(self, *, enabled: bool, daily_usd: float) -> None:
        self.enabled = enabled
        self.daily_usd = daily_usd

    def gate(self, conn: sqlite3.Connection) -> bool:
        total = queue_store.daily_cost_total(conn)
        if not self.enabled:
            log.debug("daily_cost_usd=%.4f (budget guard disabled)", total)
            return True
        if total >= self.daily_usd:
            log.warning(
                "daily budget guard: $%.2f spent today >= $%.2f limit",
                total, self.daily_usd,
            )
            return False
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_guards.py -v
```

Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/guards.py tests/orchestrator/test_guards.py
git commit -m "orchestrator(guards): QueueBackpressure / QueueRateGuard / DailyBudgetGuard (all enabled=False)"
```

---

## Task 7: Candidate query — `fetch_candidates`

**Files:**
- Create: `tradingagents/orchestrator/candidates.py`
- Test: `tests/orchestrator/test_candidates.py`

The promoter's predicate. The LEFT-JOIN-queue_jobs idempotency guard prevents double-enqueueing across poll cycles.

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_candidates.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    # Watchlist contains AAPL
    store.upsert_watchlist(c, ticker="AAPL", ttl_until=None, tags=["user"])
    return c


def _seed_event(conn, *, ev_id, ticker, salience, confidence, status="triaged"):
    store.insert_event(conn, event_id=ev_id, source="rss",
                       ingested_ts=_now(), salience=salience, raw_path=None,
                       status=status, deduped_of=None)
    store.insert_event_ticker(conn, event_id=ev_id, ticker=ticker,
                              confidence=confidence)


@pytest.mark.unit
def test_high_salience_watchlist_event_is_candidate(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "ev1"
    assert rows[0]["ticker"] == "AAPL"


@pytest.mark.unit
def test_low_salience_event_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.5, confidence=0.9)
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50)
    assert rows == []


@pytest.mark.unit
def test_low_confidence_ticker_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.6)
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_off_watchlist_ticker_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="TSLA", salience=0.9, confidence=0.9)
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_duplicate_status_event_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9,
                confidence=0.9, status="duplicate")
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_suppressed_ticker_is_skipped(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    until = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    store.upsert_suppression(conn, key="event_alert:AAPL", until_ts=until,
                              reason="cooldown", created_by="test")
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_expired_suppression_does_not_skip(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store.upsert_suppression(conn, key="event_alert:AAPL", until_ts=past,
                              reason="cooldown", created_by="test")
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50)
    assert len(rows) == 1


@pytest.mark.unit
def test_already_enqueued_event_is_skipped(conn):
    """Idempotency guard: an event already referenced by queue_jobs.trigger_event_id
    is never returned again."""
    from tradingagents.orchestrator.candidates import fetch_candidates
    from tradingagents.orchestrator.queue_store import insert_queue_job
    _seed_event(conn, ev_id="ev1", ticker="AAPL", salience=0.9, confidence=0.9)
    insert_queue_job(conn, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    assert fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=50) == []


@pytest.mark.unit
def test_limit_respected_and_ordered_by_ingested_ts(conn):
    from tradingagents.orchestrator.candidates import fetch_candidates
    # Insert 3 events with slightly increasing timestamps via direct INSERT
    # (the helper uses now() which has 1-microsecond resolution but rapid loops
    # can collide); use explicit timestamps to be deterministic.
    base = datetime.now(timezone.utc)
    for i in range(3):
        ts = (base + timedelta(seconds=i)).isoformat()
        conn.execute(
            "INSERT INTO events (event_id, source, ingested_ts, salience, "
            "raw_path, deduped_of, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"ev{i}", "rss", ts, 0.9, None, None, "triaged"),
        )
        store.insert_event_ticker(conn, event_id=f"ev{i}", ticker="AAPL",
                                   confidence=0.9)
    conn.commit()
    rows = fetch_candidates(conn, salience_threshold=0.7,
                            ticker_conf_threshold=0.8, limit=2)
    assert [r["event_id"] for r in rows] == ["ev0", "ev1"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_candidates.py -v
```

Expected: ImportError on `candidates`.

- [ ] **Step 3: Implement `candidates.py`**

Create `tradingagents/orchestrator/candidates.py`:

```python
"""Promoter candidate query — selects triaged events worth firing as alerts.

Predicate: event.status='triaged' AND event.salience >= S AND
           event_ticker.confidence >= C AND ticker ∈ watchlist AND
           not currently suppressed AND not already enqueued.

Ordered oldest-first so the oldest qualifying event fires first.
"""

from __future__ import annotations

import sqlite3
from typing import List


_QUERY = """
SELECT e.event_id, et.ticker, e.salience, et.confidence, e.ingested_ts
FROM events e
JOIN event_ticker et   ON et.event_id = e.event_id
JOIN watchlist  w      ON w.ticker     = et.ticker
LEFT JOIN suppression s ON s.key = 'event_alert:' || et.ticker
                       AND s.until_ts > datetime('now')
LEFT JOIN queue_jobs q ON q.trigger_event_id = e.event_id
WHERE e.status = 'triaged'
  AND e.salience >= ?
  AND et.confidence >= ?
  AND s.key IS NULL
  AND q.job_id IS NULL
ORDER BY e.ingested_ts ASC
LIMIT ?
"""


def fetch_candidates(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    limit: int,
) -> List[sqlite3.Row]:
    return list(
        conn.execute(
            _QUERY,
            (salience_threshold, ticker_conf_threshold, limit),
        )
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_candidates.py -v
```

Expected: all 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/candidates.py tests/orchestrator/test_candidates.py
git commit -m "orchestrator(candidates): fetch_candidates with idempotency LEFT JOIN guard"
```

---

## Task 8: Promoter loop — `run_once` + `main` + crash-safety

**Files:**
- Create: `tradingagents/orchestrator/promoter.py`
- Test: `tests/orchestrator/test_promoter_loop.py`
- Modify: `pyproject.toml` — add `freezegun` to dev extras

`run_once` is the unit-testable seam: one call performs one poll cycle and returns the count of enqueued jobs. `main` is the systemd entry — a `while True` loop wrapping `run_once` with defensive retry.

- [ ] **Step 1: Add `freezegun` to dev extras**

In `pyproject.toml`, extend the `dev` extra:

```toml
dev = [
    "fakeredis>=2.20",
    "freezegun>=1.4",       # F4: deterministic time control for cooldown tests
]
```

Then:

```bash
pip install -e ".[dev]"
python -c "import freezegun; print('freezegun OK')"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/orchestrator/test_promoter_loop.py`:

```python
import json
import sqlite3
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(c, ticker="AAPL", ttl_until=None, tags=["user"])
    return c


def _seed_event(conn, *, ev_id="ev1", ticker="AAPL", salience=0.9, conf=0.9):
    store.insert_event(conn, event_id=ev_id, source="rss",
                       ingested_ts=_now(), salience=salience, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id=ev_id, ticker=ticker,
                              confidence=conf)


@pytest.mark.unit
def test_run_once_enqueues_and_suppresses(conn):
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    n = run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                 batch_size=10, cooldown_min=60)
    assert n == 1
    job = conn.execute("SELECT * FROM queue_jobs").fetchone()
    assert job["job_type"] == "event_alert"
    assert job["trigger_event_id"] == "ev1"
    payload = json.loads(job["payload"])
    assert payload == {"event_id": "ev1", "ticker": "AAPL"}
    sup = conn.execute(
        "SELECT * FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()
    assert sup is not None


@pytest.mark.unit
def test_run_once_is_idempotent(conn):
    """Second tick (no new events) enqueues nothing."""
    from tradingagents.orchestrator.promoter import run_once
    _seed_event(conn)
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60) == 1
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60) == 0


@pytest.mark.unit
def test_partial_failure_does_not_leave_orphan_suppression(conn, monkeypatch):
    """If upsert_suppression raises mid-tx, the queue_jobs row must roll back."""
    from tradingagents.orchestrator import promoter as p
    _seed_event(conn)
    orig = p.store.upsert_suppression

    def boom(*a, **kw):
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(p.store, "upsert_suppression", boom)
    with pytest.raises(RuntimeError):
        p.run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                   batch_size=10, cooldown_min=60)
    # Both writes must be absent — the with-block rolled the tx back.
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM suppression WHERE key='event_alert:AAPL'"
    ).fetchone()[0] == 0


@pytest.mark.unit
def test_backpressure_disabled_does_not_block(conn):
    from tradingagents.orchestrator.promoter import run_once
    from tradingagents.orchestrator.guards import QueueBackpressure
    _seed_event(conn)
    g = QueueBackpressure(enabled=False, max_pending=0)  # would block if enabled
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60,
                    backpressure=g) == 1


@pytest.mark.unit
def test_backpressure_enabled_blocks(conn):
    from tradingagents.orchestrator.promoter import run_once
    from tradingagents.orchestrator.guards import QueueBackpressure
    _seed_event(conn)
    g = QueueBackpressure(enabled=True, max_pending=0)
    assert run_once(conn, salience_threshold=0.7, ticker_conf_threshold=0.8,
                    batch_size=10, cooldown_min=60,
                    backpressure=g) == 0
    assert conn.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0] == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_promoter_loop.py -v
```

Expected: ImportError on `promoter`.

- [ ] **Step 4: Implement `promoter.py`**

Create `tradingagents/orchestrator/promoter.py`:

```python
"""F4 promoter — polls events for trigger candidates and enqueues jobs.

Runs as `iic-promoter.service`. Defensive retry-internal: never raises out
of the main loop except on truly unrecoverable errors.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from tradingagents.persistence import store
from tradingagents.persistence.db import connect
from tradingagents.orchestrator import queue_store
from tradingagents.orchestrator.candidates import fetch_candidates
from tradingagents.orchestrator.guards import QueueBackpressure, QueueRateGuard


log = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def run_once(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    batch_size: int,
    cooldown_min: int,
    backpressure: Optional[QueueBackpressure] = None,
    rate_guard: Optional[QueueRateGuard] = None,
) -> int:
    """Perform one poll cycle. Returns the count of jobs enqueued."""
    if backpressure is not None and not backpressure.gate(conn):
        return 0
    if rate_guard is not None and not rate_guard.gate(conn):
        return 0

    candidates = fetch_candidates(
        conn,
        salience_threshold=salience_threshold,
        ticker_conf_threshold=ticker_conf_threshold,
        limit=batch_size,
    )
    if not candidates:
        return 0

    enqueued = 0
    for ev in candidates:
        until_ts = (_now_utc() + timedelta(minutes=cooldown_min)).isoformat()
        try:
            with conn:    # one atomic tx per event
                conn.execute(
                    "INSERT INTO queue_jobs (job_type, payload, state, "
                    "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', ?, ?)",
                    (
                        "event_alert",
                        json.dumps({"event_id": ev["event_id"],
                                    "ticker": ev["ticker"]}),
                        _now_utc().isoformat(),
                        ev["event_id"],
                    ),
                )
                store.upsert_suppression(
                    conn,
                    key=f"event_alert:{ev['ticker']}",
                    until_ts=until_ts,
                    reason=f"alert_cooldown event_id={ev['event_id']}",
                    created_by="promoter",
                )
            enqueued += 1
            log.info("enqueued event_alert event_id=%s ticker=%s",
                     ev["event_id"], ev["ticker"])
        except sqlite3.OperationalError:
            log.exception("db error enqueueing event_id=%s; backing off",
                          ev["event_id"])
            time.sleep(2)
    return enqueued


def main(config: Optional[dict] = None) -> None:
    """systemd entry point. Defensive: never exits except on KeyboardInterrupt."""
    from tradingagents.default_config import DEFAULT_CONFIG
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    conn = connect(cfg["iic_db_path"])
    backpressure = QueueBackpressure(
        enabled=cfg["trigger_backpressure_enabled"],
        max_pending=cfg["trigger_backpressure_max_pending"],
    )
    rate_guard = QueueRateGuard(
        enabled=cfg["trigger_daily_rate_enabled"],
        max_per_day=cfg["trigger_daily_rate_max_jobs"],
    )

    log.info("promoter starting: poll=%ss cooldown=%sm guards: bp=%s rate=%s",
             cfg["promoter_poll_interval_s"], cfg["alert_cooldown_min"],
             backpressure.enabled, rate_guard.enabled)

    while True:
        try:
            run_once(
                conn,
                salience_threshold=cfg["alert_salience_threshold"],
                ticker_conf_threshold=cfg["alert_ticker_confidence_threshold"],
                batch_size=cfg["promoter_batch_size"],
                cooldown_min=cfg["alert_cooldown_min"],
                backpressure=backpressure,
                rate_guard=rate_guard,
            )
        except KeyboardInterrupt:
            log.info("promoter shutting down on KeyboardInterrupt")
            raise
        except Exception:
            log.exception("promoter loop failure; sleeping 5s and continuing")
            time.sleep(5)
        time.sleep(cfg["promoter_poll_interval_s"])


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_promoter_loop.py -v
```

Expected: all 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tradingagents/orchestrator/promoter.py tests/orchestrator/test_promoter_loop.py
git commit -m "orchestrator(promoter): run_once + main; atomic enqueue+suppression; defensive retry"
```

---

## Task 9: Thread `queue_job_id` through RunRecorder + `runs` row

**Files:**
- Modify: `tradingagents/persistence/store.py` — `insert_run(queue_job_id=)`
- Modify: `tradingagents/graph/run_recorder.py` — `RunRecorder.__init__(queue_job_id=)`
- Modify: `tradingagents/graph/trading_graph.py` — pass `config["queue_job_id"]` into RunRecorder
- Test: `tests/persistence/test_insert_run_queue_job.py`

- [ ] **Step 1: Write the failing test**

Create `tests/persistence/test_insert_run_queue_job.py`:

```python
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_insert_run_with_queue_job_id(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    # Seed a queue_jobs row first so the FK resolves.
    cur = conn.execute(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts) "
        "VALUES ('event_alert', '{}', 'running', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    job_id = cur.lastrowid
    conn.commit()

    store.insert_run(
        conn,
        run_id="r1", ticker="AAPL", persona_id="macro",
        started_ts=datetime.now(timezone.utc).isoformat(),
        artifact_dir="runs/r1",
        trigger_id=None,
        queue_job_id=job_id,
    )
    row = conn.execute("SELECT * FROM runs WHERE run_id='r1'").fetchone()
    assert row["queue_job_id"] == job_id


@pytest.mark.unit
def test_insert_run_queue_job_id_defaults_none(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r1", ticker="AAPL", persona_id=None,
        started_ts=datetime.now(timezone.utc).isoformat(),
        artifact_dir="runs/r1",
    )
    row = conn.execute("SELECT * FROM runs WHERE run_id='r1'").fetchone()
    assert row["queue_job_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/persistence/test_insert_run_queue_job.py -v
```

Expected: FAIL — `queue_job_id` not accepted.

- [ ] **Step 3: Extend `store.insert_run`**

In `tradingagents/persistence/store.py`, replace `insert_run`:

```python
def insert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    persona_id: Optional[str],
    started_ts: str,
    artifact_dir: str,
    trigger_id: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> None:
    conn.execute(
        "INSERT INTO runs (run_id, ticker, persona_id, started_ts, status, "
        "trigger_id, artifact_dir, queue_job_id) VALUES (?, ?, ?, ?, 'running', ?, ?, ?)",
        (run_id, ticker, persona_id, started_ts, trigger_id, artifact_dir,
         queue_job_id),
    )
    conn.commit()
```

- [ ] **Step 4: Extend `RunRecorder`**

In `tradingagents/graph/run_recorder.py`, modify `RunRecorder.__init__` and `start`:

```python
class RunRecorder:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        data_dir: str,
        run_id: str,
        persona_id: Optional[str],
        cost_callback: Any,
        queue_job_id: Optional[int] = None,
    ) -> None:
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._run_id = run_id
        self._persona_id = persona_id
        self._cost_callback = cost_callback
        self._queue_job_id = queue_job_id
        self._artifact_dir_rel = f"runs/{run_id}"

    def start(self, ticker: str, *, started_ts: str) -> None:
        store.insert_run(
            self._conn,
            run_id=self._run_id,
            ticker=ticker,
            persona_id=self._persona_id,
            started_ts=started_ts,
            artifact_dir=self._artifact_dir_rel,
            queue_job_id=self._queue_job_id,
        )
```

- [ ] **Step 5: Read `config["queue_job_id"]` in TradingAgentsGraph**

In `tradingagents/graph/trading_graph.py`, find the `RunRecorder(` construction (around line 123) and add `queue_job_id` from config:

```python
        self.run_recorder = RunRecorder(
            conn=...,                # existing args unchanged
            data_dir=...,
            run_id=self.run_id,
            persona_id=self.config.get("persona_id"),
            cost_callback=...,
            queue_job_id=self.config.get("queue_job_id"),  # NEW — F4
        )
```

(Preserve the existing argument lines as-is; only add the new kwarg.)

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/persistence/test_insert_run_queue_job.py tests/persistence/ tests/smoke/test_f1_exit_gate.py -v
```

Expected: new tests PASS; existing F1 smoke still PASSES (it doesn't set `queue_job_id`, which defaults to None).

- [ ] **Step 7: Commit**

```bash
git add tradingagents/persistence/store.py tradingagents/graph/run_recorder.py tradingagents/graph/trading_graph.py tests/persistence/test_insert_run_queue_job.py
git commit -m "graph(run_recorder): thread queue_job_id from config → runs row"
```

---

## Task 10: Persona-runner extraction — `tradingagents/secretary/persona_runner.py`

**Files:**
- Create: `tradingagents/secretary/persona_runner.py`
- Modify: `cli/deepdive.py` — delegate to `persona_runner.run_personas_parallel`
- Test: `tests/orchestrator/test_persona_runner.py`

The fan-out pattern in `cli/deepdive.py` is reused by `compose_event_alert`. Extract it into a shared module so both call sites use the same code path.

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_persona_runner.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_run_personas_parallel_returns_one_run_id_per_persona(monkeypatch):
    from tradingagents.secretary.persona_runner import run_personas_parallel
    from tradingagents.personas.loader import Persona, LLMSettings, AnalystSettings, RiskDebateSettings

    def make_p(pid):
        return Persona(
            id=pid, name=pid, description="",
            system_prompt_fragment="frag",
            llm=LLMSettings(deep_think_llm="dt", quick_think_llm="qt"),
            analysts=AnalystSettings(include=["market"], exclude=[]),
            risk_debate=RiskDebateSettings(),
        )
    personas = [make_p("macro"), make_p("value"), make_p("momentum")]

    fake_run_ids = iter(["r1", "r2", "r3"])

    def fake_run_one(persona, ticker, trade_date, config,
                     event_context=None, queue_job_id=None):
        return next(fake_run_ids)

    monkeypatch.setattr(
        "tradingagents.secretary.persona_runner._run_one_persona",
        fake_run_one,
    )
    run_ids = run_personas_parallel(
        personas=personas, ticker="AAPL", trade_date="2026-05-27",
        config={"deep_think_llm": "x"}, parallel=True,
    )
    assert sorted(run_ids) == ["r1", "r2", "r3"]


@pytest.mark.unit
def test_run_personas_parallel_threads_event_context_and_job_id(monkeypatch):
    from tradingagents.secretary.persona_runner import run_personas_parallel
    from tradingagents.personas.loader import Persona, LLMSettings, AnalystSettings, RiskDebateSettings

    captured = []

    def fake_run_one(persona, ticker, trade_date, config,
                     event_context=None, queue_job_id=None):
        captured.append((persona.id, event_context, queue_job_id))
        return f"r-{persona.id}"

    monkeypatch.setattr(
        "tradingagents.secretary.persona_runner._run_one_persona",
        fake_run_one,
    )
    p = Persona(
        id="macro", name="m", description="",
        system_prompt_fragment="frag",
        llm=LLMSettings(deep_think_llm="dt", quick_think_llm="qt"),
        analysts=AnalystSettings(include=["market"], exclude=[]),
        risk_debate=RiskDebateSettings(),
    )
    run_personas_parallel(
        personas=[p], ticker="AAPL", trade_date="2026-05-27",
        config={}, parallel=False,
        event_context="Apple beats earnings.", queue_job_id=42,
    )
    assert captured == [("macro", "Apple beats earnings.", 42)]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_persona_runner.py -v
```

Expected: ImportError on `persona_runner`.

- [ ] **Step 3: Create `persona_runner.py`**

Create `tradingagents/secretary/persona_runner.py`:

```python
"""Shared persona-fan-out helper.

Both ``cli.deepdive.run_deepdive`` and
``Secretary.compose_event_alert`` use this to launch N persona-overlaid
TradingAgentsGraph runs in parallel and collect their run_ids.

Lifted out of cli/deepdive.py so the worker path doesn't need a CLI
dependency to run personas.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from tradingagents.personas.loader import Persona


def _run_one_persona(
    persona: Persona,
    ticker: str,
    trade_date: str,
    config: dict,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> str:
    """Construct a TradingAgentsGraph with the persona overlay, propagate,
    return the run_id.

    ``event_context`` is threaded into the per-run config as ``event_context``;
    the graph reads it from config and injects it into the initial state
    (see Task 11).

    ``queue_job_id`` is threaded into the per-run config as ``queue_job_id``;
    the graph's RunRecorder writes it into the ``runs.queue_job_id`` column
    (see Task 9).
    """
    overlay = dict(config)
    overlay["persona_id"] = persona.id
    overlay["deep_think_llm"] = persona.llm.deep_think_llm
    overlay["quick_think_llm"] = persona.llm.quick_think_llm
    if persona.llm.deepseek_reasoning_effort is not None:
        overlay["deepseek_reasoning_effort"] = persona.llm.deepseek_reasoning_effort
    if event_context is not None:
        overlay["event_context"] = event_context
    if queue_job_id is not None:
        overlay["queue_job_id"] = queue_job_id

    selected = list(persona.analysts.include)

    # Import here to keep this module light when only the helper is needed.
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(config=overlay, selected_analysts=selected)
    graph.propagate(ticker, trade_date)
    return graph.run_id


def run_personas_parallel(
    *,
    personas: List[Persona],
    ticker: str,
    trade_date: str,
    config: dict,
    parallel: bool = True,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> List[str]:
    """Run each persona, return run_ids in completion order.

    With ``parallel=True`` (default), uses a ThreadPoolExecutor sized to the
    persona count. With ``parallel=False``, runs sequentially (used by tests
    and for deterministic debugging).
    """
    if not personas:
        raise RuntimeError("run_personas_parallel: empty personas list")

    if parallel:
        with ThreadPoolExecutor(max_workers=len(personas)) as ex:
            futures = [
                ex.submit(
                    _run_one_persona, p, ticker, trade_date, config,
                    event_context, queue_job_id,
                )
                for p in personas
            ]
            return [f.result() for f in futures]
    return [
        _run_one_persona(
            p, ticker, trade_date, config, event_context, queue_job_id,
        )
        for p in personas
    ]
```

- [ ] **Step 4: Delegate from `cli/deepdive.py`**

In `cli/deepdive.py`, REMOVE the local `_run_one_persona` function (lines 27–50) and replace the body of `run_deepdive` with a call to the new helper:

```python
from tradingagents.secretary.persona_runner import run_personas_parallel


def run_deepdive(
    *,
    ticker: str,
    trade_date: str,
    parallel: bool = True,
    config_overrides: dict | None = None,
) -> str:
    """Programmatic entry point — returns the brief_id."""
    config = dict(DEFAULT_CONFIG)
    if config_overrides:
        config.update(config_overrides)
    personas: List[Persona] = load_all_personas(_personas_dir())
    if not personas:
        raise RuntimeError(f"No personas found in {_personas_dir()}")

    run_ids = run_personas_parallel(
        personas=personas, ticker=ticker, trade_date=trade_date,
        config=config, parallel=parallel,
    )

    sec = _build_secretary(config)
    return sec.compose_deep_dive(ticker=ticker, run_ids=run_ids,
                                  trade_date=trade_date)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_persona_runner.py tests/smoke/test_f1_exit_gate.py -v
```

Expected: new persona-runner tests PASS; the F1 smoke (which exercises `cli/deepdive.py`) still PASSES.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/secretary/persona_runner.py cli/deepdive.py tests/orchestrator/test_persona_runner.py
git commit -m "secretary(persona_runner): extract run_personas_parallel; cli/deepdive delegates"
```

---

## Task 11: Event-context injection — config → graph state → audit MD

**Files:**
- Modify: `tradingagents/graph/trading_graph.py` — read `config["event_context"]` and write it into the initial state as `event_context_text`
- Modify: `tradingagents/graph/run_recorder.py` — when `event_context_text` is present in state, write it to `data/runs/<run_id>/event_context.md` for audit
- Test: `tests/orchestrator/test_event_context_injection.py`

This task is intentionally scoped to **wire `event_context` through the config → state seam and write the audit MD**. It does NOT try to thread it into per-analyst LLM prompts in this plan — the personas are reasoning about the ticker for `trade_date` (the news analyst already fetches recent news from that day), and the event prominently appears in the rendered brief (Task 12 + Task 13). If empirical brief quality is poor because the personas don't see the specific event verbatim during reasoning, file a follow-up to thread `event_context_text` into the per-analyst prompts as a separate scope.

The user-visible behavior we MUST guarantee in F4:
1. `data/runs/<run_id>/event_context.md` exists when the run was launched with `event_context` in config (audit).
2. The brief markdown contains the event text (covered by Task 12's template + Task 13's integration test).

- [ ] **Step 1: Locate the initial-state construction site**

```bash
grep -n "company_of_interest\b" tradingagents/graph/trading_graph.py | head -10
grep -n "def propagate" tradingagents/graph/trading_graph.py
```

`propagate(ticker, trade_date)` builds the initial state dict and invokes the graph. The state assembly is the seam — confirm the line number, then in Step 3 add `event_context_text` to that dict.

- [ ] **Step 2: Write the failing tests**

Create `tests/orchestrator/test_event_context_injection.py`:

```python
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect


@pytest.mark.unit
def test_run_recorder_writes_event_context_md_when_present(tmp_path):
    """When state.event_context_text is non-empty, RunRecorder.record writes
    it to data/runs/<run_id>/event_context.md."""
    from tradingagents.graph.run_recorder import RunRecorder

    conn = connect(str(tmp_path / "iic.db"))
    cost_cb = MagicMock()
    cost_cb.totals_by_model.return_value = {}

    rec = RunRecorder(
        conn=conn, data_dir=str(tmp_path / "data"),
        run_id="r1", persona_id="macro",
        cost_callback=cost_cb, queue_job_id=None,
    )
    rec.start("AAPL", started_ts=datetime.now(timezone.utc).isoformat())
    rec.record({
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-27",
        "final_trade_decision": "BUY",
        "event_context_text": "Apple beats Q3 earnings by 12%.",
    })
    ctx = Path(tmp_path / "data" / "runs" / "r1" / "event_context.md")
    assert ctx.exists()
    assert ctx.read_text() == "Apple beats Q3 earnings by 12%."


@pytest.mark.unit
def test_run_recorder_skips_event_context_md_when_absent(tmp_path):
    from tradingagents.graph.run_recorder import RunRecorder

    conn = connect(str(tmp_path / "iic.db"))
    cost_cb = MagicMock()
    cost_cb.totals_by_model.return_value = {}

    rec = RunRecorder(
        conn=conn, data_dir=str(tmp_path / "data"),
        run_id="r2", persona_id="macro",
        cost_callback=cost_cb, queue_job_id=None,
    )
    rec.start("AAPL", started_ts=datetime.now(timezone.utc).isoformat())
    rec.record({
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-27",
        "final_trade_decision": "BUY",
    })
    assert not (tmp_path / "data" / "runs" / "r2" / "event_context.md").exists()


@pytest.mark.unit
def test_trading_graph_threads_event_context_into_state(monkeypatch):
    """TradingAgentsGraph.propagate must seed state['event_context_text']
    from self.config['event_context'] before invoking the graph."""
    captured: dict = {}

    # Monkeypatch the compiled graph invoke so we can capture the initial state
    # without paying for a real graph run.
    from tradingagents.graph import trading_graph as tg_mod

    class FakeCompiled:
        def invoke(self, state, config=None):
            captured.update(state)
            return state

    def fake_setup_graph(self, selected_analysts, run_recorder_node=None):
        return FakeCompiled()

    monkeypatch.setattr(
        tg_mod.GraphSetup if hasattr(tg_mod, "GraphSetup") else object,
        "setup_graph", fake_setup_graph, raising=False,
    )

    cfg = {
        "llm_provider": "deepseek",
        "deep_think_llm": "deepseek-v4-pro",
        "quick_think_llm": "deepseek-v4-flash",
        "event_context": "Apple beats Q3 earnings by 12%.",
    }
    g = tg_mod.TradingAgentsGraph(config=cfg, selected_analysts=["market"])
    try:
        g.propagate("AAPL", "2026-05-27")
    except Exception:
        # Some downstream nodes will fail without a real LLM — that's fine,
        # we only need to confirm the initial state was seeded.
        pass

    assert captured.get("event_context_text") == "Apple beats Q3 earnings by 12%."
```

- [ ] **Step 3: Add `event_context_text` to the initial state**

In `tradingagents/graph/trading_graph.py`, find the dict literal inside `propagate()` that constructs the initial state (it will contain `"company_of_interest": ticker` and `"trade_date": trade_date`). Add one new key:

```python
            # Existing keys:
            "company_of_interest": ticker,
            "trade_date": trade_date,
            # ... other existing keys ...
            # F4: event-context injection (empty string when not in event_alert mode).
            "event_context_text": self.config.get("event_context", "") or "",
```

- [ ] **Step 4: Write `event_context.md` in `RunRecorder.record`**

In `tradingagents/graph/run_recorder.py`, in `RunRecorder.record`, after the per-analyst MD write loop and before the `meta.json` write:

```python
        event_ctx = state.get("event_context_text", "") or ""
        if event_ctx:
            (run_path / "event_context.md").write_text(event_ctx, encoding="utf-8")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_event_context_injection.py -v
pytest tests/smoke/test_f1_exit_gate.py -v
```

Expected: new tests PASS; F1 deep-dive smoke still PASSES (when `event_context` is absent, behavior is identical — empty string → no audit file).

- [ ] **Step 6: Commit**

```bash
git add tradingagents/graph/trading_graph.py tradingagents/graph/run_recorder.py tests/orchestrator/test_event_context_injection.py
git commit -m "graph(event_context): config → initial state seed + per-run audit MD"
```

---

## Task 12: `event_alert.j2` template + render helper

**Files:**
- Create: `tradingagents/secretary/templates/event_alert.j2`
- Modify: `tradingagents/secretary/service.py` — add `render_event_alert`
- Test: `tests/orchestrator/test_event_alert_template.py`

- [ ] **Step 1: Write the failing test**

Create `tests/orchestrator/test_event_alert_template.py`:

```python
import pytest


@pytest.mark.unit
def test_render_event_alert_includes_terse_structure():
    from tradingagents.secretary.service import render_event_alert
    md = render_event_alert(
        ticker="AAPL",
        event={
            "event_id": "ev1",
            "source": "polygon_news",
            "ingested_ts": "2026-05-27T12:34:56+00:00",
            "raw_text": "Apple beats Q3 earnings by 12%.",
        },
        synthesis={
            "consensus": "Strong upside surprise.",
            "divergence": "Macro flags rate-sensitivity.",
            "recommendation": "BUY (high confidence)",
        },
        persona_runs=[
            {"persona_id": "macro", "decision": "HOLD", "final_trade_decision": "..."},
            {"persona_id": "value", "decision": "BUY",  "final_trade_decision": "..."},
            {"persona_id": "momentum", "decision": "BUY", "final_trade_decision": "..."},
        ],
    )
    # Terse structure: header, event, consensus/divergence/recommendation, links
    assert "AAPL" in md
    assert "Apple beats Q3 earnings by 12%." in md
    assert "Consensus" in md and "Strong upside surprise." in md
    assert "Divergence" in md
    assert "Recommendation" in md
    assert "BUY (high confidence)" in md
    # Per-persona table or list
    assert "macro" in md and "value" in md and "momentum" in md


@pytest.mark.unit
def test_render_event_alert_word_count_is_terse():
    """Per spec §6: ~200–400 words target. Verify lower bound."""
    from tradingagents.secretary.service import render_event_alert
    md = render_event_alert(
        ticker="AAPL",
        event={"event_id": "ev1", "source": "rss",
               "ingested_ts": "2026-05-27T12:34:56+00:00",
               "raw_text": "Short event text."},
        synthesis={"consensus": "x", "divergence": "y", "recommendation": "BUY"},
        persona_runs=[{"persona_id": "macro", "decision": "BUY",
                       "final_trade_decision": "z"}],
    )
    # Template chrome alone is non-empty.
    assert len(md.split()) >= 20
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_event_alert_template.py -v
```

Expected: ImportError on `render_event_alert`.

- [ ] **Step 3: Create the template**

Create `tradingagents/secretary/templates/event_alert.j2`:

```jinja
# 🚨 Event Alert — {{ ticker }}

**Triggered:** {{ event.ingested_ts }} · **Source:** {{ event.source }}

## Trigger Event

{{ event.raw_text }}

---

## Consensus

{{ synthesis.consensus }}

## Divergence

{{ synthesis.divergence }}

## Recommendation

**{{ synthesis.recommendation }}**

---

## Per-persona reads

| Persona | Decision |
|---|---|
{%- for r in persona_runs %}
| `{{ r.persona_id }}` | `{{ r.decision }}` |
{%- endfor %}

---

*Event id: `{{ event.event_id }}`. See `data/runs/<run_id>/pm_synthesis.md` for each persona's full reasoning.*
```

- [ ] **Step 4: Add `render_event_alert` to `service.py`**

In `tradingagents/secretary/service.py`, alongside the existing `render_deep_dive`:

```python
def render_event_alert(
    *,
    ticker: str,
    event: Dict[str, Any],
    synthesis: Dict[str, str],
    persona_runs: List[Dict[str, Any]],
) -> str:
    return _env.get_template("event_alert.j2").render(
        ticker=ticker,
        event=event,
        synthesis=synthesis,
        persona_runs=persona_runs,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_event_alert_template.py -v
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/secretary/templates/event_alert.j2 tradingagents/secretary/service.py tests/orchestrator/test_event_alert_template.py
git commit -m "secretary(event_alert): terse template + render_event_alert helper"
```

---

## Task 13: `Secretary.compose_event_alert` — replace the F1 stub

**Files:**
- Modify: `tradingagents/secretary/service.py` — implement `compose_event_alert`
- Modify: `tradingagents/secretary/synthesis.py` — `synthesize_brief(..., event_context=None)` optional kwarg
- Test: `tests/orchestrator/test_compose_event_alert.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_compose_event_alert.py`:

```python
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.secretary.service import Secretary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def setup(tmp_path):
    """Seed events row, raw payload on disk, three completed runs, and a
    queue_jobs row."""
    db = str(tmp_path / "iic.db")
    data_dir = tmp_path / "data"
    (data_dir / "events").mkdir(parents=True, exist_ok=True)
    raw_path = data_dir / "events" / "ev1.json"
    raw_path.write_text(json.dumps({
        "text": "Apple beats Q3 earnings by 12%.",
        "source": "polygon_news",
    }))

    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts=_now(), salience=0.9,
                       raw_path=str(raw_path),
                       status="triaged", deduped_of=None)
    # Three mock completed runs
    for rid, pid, dec in [("r1", "macro", "HOLD"),
                          ("r2", "value", "BUY"),
                          ("r3", "momentum", "BUY")]:
        artifact_dir = f"runs/{rid}"
        (data_dir / artifact_dir).mkdir(parents=True)
        (data_dir / artifact_dir / "pm_synthesis.md").write_text(
            f"## {pid}\n\nDecision: **{dec}**\nReason: ...\n"
        )
        store.insert_run(conn, run_id=rid, ticker="AAPL",
                         persona_id=pid, started_ts=_now(),
                         artifact_dir=artifact_dir, queue_job_id=1)
        store.finalize_run(conn, run_id=rid, ended_ts=_now(),
                            status="complete", decision=dec, confidence=None)
    return conn, str(data_dir)


@pytest.mark.unit
def test_compose_event_alert_writes_brief(setup, monkeypatch):
    """Given pre-seeded runs, compose_event_alert produces a brief row,
    a markdown file, and a synthesis that includes the trigger event."""
    conn, data_dir = setup

    # Mock the persona-runner so this test doesn't actually invoke the graph.
    def fake_runner(*, personas, ticker, trade_date, config, parallel,
                    event_context, queue_job_id):
        return ["r1", "r2", "r3"]
    monkeypatch.setattr(
        "tradingagents.secretary.service.run_personas_parallel",
        fake_runner,
    )

    # Mock synthesize_brief to return a known structure.
    def fake_synth(*, llm, ticker, persona_runs, event_context=None):
        assert event_context == "Apple beats Q3 earnings by 12%."
        return {
            "consensus": "Beat is real.",
            "divergence": "Macro neutral; value+momentum BUY.",
            "recommendation": "BUY (high confidence)",
        }
    monkeypatch.setattr(
        "tradingagents.secretary.service.synthesize_brief",
        fake_synth,
    )

    sec = Secretary(conn=conn, data_dir=data_dir, llm=MagicMock())
    brief_id = sec.compose_event_alert(event_id="ev1", ticker="AAPL", job_id=1)

    # briefs row exists, trigger_event_id linked
    b = store.get_brief(conn, brief_id=brief_id)
    assert b["mode"] == "event_alert"
    assert b["trigger_event_id"] == "ev1"
    assert b["scope"] == "AAPL"

    # markdown file written; contains the trigger event text
    md_path = Path(data_dir) / "briefs" / f"{brief_id}.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "Apple beats Q3 earnings by 12%." in content
    assert "BUY (high confidence)" in content


@pytest.mark.unit
def test_compose_event_alert_returns_brief_id_string(setup, monkeypatch):
    conn, data_dir = setup
    monkeypatch.setattr(
        "tradingagents.secretary.service.run_personas_parallel",
        lambda **kw: ["r1", "r2", "r3"],
    )
    monkeypatch.setattr(
        "tradingagents.secretary.service.synthesize_brief",
        lambda **kw: {"consensus": "x", "divergence": "y", "recommendation": "z"},
    )
    sec = Secretary(conn=conn, data_dir=data_dir, llm=MagicMock())
    brief_id = sec.compose_event_alert(event_id="ev1", ticker="AAPL", job_id=1)
    assert isinstance(brief_id, str)
    assert len(brief_id) == 32   # uuid4 hex
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_compose_event_alert.py -v
```

Expected: FAIL — still hits `NotImplementedError`.

- [ ] **Step 3: Extend `synthesize_brief` with optional `event_context`**

In `tradingagents/secretary/synthesis.py`, find the `synthesize_brief` function and add the kwarg. The existing prompt-building logic is preserved; when `event_context` is non-empty, prepend a "Trigger event" header to the prompt:

```python
def synthesize_brief(
    *,
    llm,
    ticker: str,
    persona_runs: List[Dict[str, Any]],
    event_context: Optional[str] = None,
) -> Dict[str, str]:
    """Synthesize consensus/divergence/recommendation across persona runs.

    When ``event_context`` is provided (event_alert mode), it is prepended
    to the prompt as the trigger context. None / empty ≡ deep-dive mode."""
    prompt_parts: list[str] = []
    if event_context:
        prompt_parts.append(
            f"TRIGGER EVENT for {ticker}:\n\n{event_context}\n\n"
            f"Synthesize the three persona reports below into a terse "
            f"consensus / divergence / recommendation for this event.\n"
        )
    # ... existing prompt build continues here ...
    # ... existing LLM call + parse ...
```

(Preserve the existing function body; only add the kwarg + the leading conditional `if event_context:` block.)

- [ ] **Step 4: Implement `compose_event_alert`**

In `tradingagents/secretary/service.py`:

1. Add imports at the top (with the others):

```python
import json
from datetime import datetime, timezone

from tradingagents.personas.loader import load_all_personas
from tradingagents.secretary.persona_runner import run_personas_parallel
```

2. Replace the `compose_event_alert` stub:

```python
    # ----- Event alert (F4 scope) -----
    def compose_event_alert(
        self,
        *,
        event_id: str,
        ticker: str,
        job_id: int,
    ) -> str:
        """Produce an event-alert brief for a single triaged event.

        ``ticker`` is the watchlist ticker that fired the trigger rule (passed
        in from the promoter's job payload — events can have multiple
        event_ticker rows; the promoter resolves which one at enqueue time).
        """
        ev = store.get_event(self._conn, event_id=event_id)
        if ev is None:
            raise ValueError(f"compose_event_alert: event {event_id} not found")

        # Read the raw payload off disk — F3 wrote it to events/<event_id>.json.
        raw_text = ""
        if ev["raw_path"]:
            raw_path = Path(ev["raw_path"])
            if raw_path.exists():
                try:
                    raw = json.loads(raw_path.read_text(encoding="utf-8"))
                    raw_text = raw.get("text", "") or ""
                except Exception:
                    raw_text = raw_path.read_text(encoding="utf-8")[:4000]

        trade_date = datetime.fromisoformat(
            ev["ingested_ts"].replace("Z", "+00:00")
        ).date().isoformat()

        # Load personas + run them in parallel with event_context threaded in.
        personas_dir = (
            Path(__file__).resolve().parent.parent / "personas"
        )
        personas = load_all_personas(str(personas_dir))
        if not personas:
            raise RuntimeError("compose_event_alert: no personas configured")

        from tradingagents.default_config import DEFAULT_CONFIG
        config = dict(DEFAULT_CONFIG)
        config["iic_db_path"] = str(
            Path(self._data_dir).with_name("iic.db")
        ) if "iic_db_path" not in config else config["iic_db_path"]

        run_ids = run_personas_parallel(
            personas=personas,
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            parallel=True,
            event_context=raw_text,
            queue_job_id=job_id,
        )

        # Build persona_runs view for synthesis + rendering.
        persona_runs: List[Dict[str, Any]] = []
        for rid in run_ids:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (rid,)
            ).fetchone()
            if row is None:
                continue
            artifact_dir = Path(self._data_dir) / row["artifact_dir"]
            pm_path = artifact_dir / "pm_synthesis.md"
            body = pm_path.read_text(encoding="utf-8") if pm_path.exists() else ""
            persona_runs.append({
                "persona_id": row["persona_id"] or "default",
                "decision": row["decision"] or "?",
                "final_trade_decision": body,
                "run_id": rid,
            })

        synthesis = synthesize_brief(
            llm=self._llm,
            ticker=ticker,
            persona_runs=persona_runs,
            event_context=raw_text,
        )

        markdown = render_event_alert(
            ticker=ticker,
            event={
                "event_id": event_id,
                "source": ev["source"],
                "ingested_ts": ev["ingested_ts"],
                "raw_text": raw_text,
            },
            synthesis=synthesis,
            persona_runs=persona_runs,
        )

        brief_id = uuid.uuid4().hex
        rel_path = f"briefs/{brief_id}.md"
        (Path(self._data_dir) / "briefs").mkdir(parents=True, exist_ok=True)
        (Path(self._data_dir) / rel_path).write_text(markdown, encoding="utf-8")

        store.insert_brief(
            self._conn,
            brief_id=brief_id, mode="event_alert", scope=ticker,
            generated_ts=datetime.now(timezone.utc).isoformat(),
            content_path=rel_path,
            run_ids=[r["run_id"] for r in persona_runs],
            parent_brief_id=None,
            trigger_event_id=event_id,
        )
        return brief_id
```

3. Make sure `render_event_alert` from Task 12 is imported in the module's `from` block at the top of `service.py`:

```python
# (Already added in Task 12; verify present.)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_compose_event_alert.py tests/smoke/test_f1_exit_gate.py -v
```

Expected: new tests PASS; F1 deep-dive smoke still PASSES.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/secretary/service.py tradingagents/secretary/synthesis.py tests/orchestrator/test_compose_event_alert.py
git commit -m "secretary(event_alert): compose_event_alert implementation; synthesize_brief gains event_context kwarg"
```

---

## Task 14: Worker dispatch — `DISPATCH` map + `dispatch_event_alert`

**Files:**
- Create: `tradingagents/orchestrator/dispatch.py`
- Test: `tests/orchestrator/test_worker_dispatch.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_worker_dispatch.py`:

```python
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def setup(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    raw = tmp_path / "data" / "events" / "ev1.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps({"text": "trigger event text"}))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9,
                       raw_path=str(raw),
                       status="triaged", deduped_of=None)
    return conn, str(tmp_path / "data")


@pytest.mark.unit
def test_dispatch_event_alert_calls_secretary_with_payload(setup):
    from tradingagents.orchestrator.dispatch import dispatch_event_alert

    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.return_value = "b1"

    job = {
        "job_id": 1,
        "job_type": "event_alert",
        "payload": json.dumps({"event_id": "ev1", "ticker": "AAPL"}),
        "trigger_event_id": "ev1",
    }
    result = dispatch_event_alert(conn, job, secretary=sec)

    sec.compose_event_alert.assert_called_once_with(
        event_id="ev1", ticker="AAPL", job_id=1
    )
    assert result["brief_id"] == "b1"
    assert result["run_ids"] == []   # secretary call return → run_ids derived from DB
    # cost_usd defaults to 0.0 when no costs rows for the implicit runs


@pytest.mark.unit
def test_dispatch_event_alert_cost_rollup(setup, monkeypatch):
    from tradingagents.orchestrator.dispatch import dispatch_event_alert

    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.return_value = "b1"

    # Seed two run rows + two costs rows with known dollar values
    for rid in ("r1", "r2"):
        store.insert_run(conn, run_id=rid, ticker="AAPL", persona_id="macro",
                         started_ts=_now(), artifact_dir=f"runs/{rid}",
                         queue_job_id=1)
        store.finalize_run(conn, run_id=rid, ended_ts=_now(),
                            status="complete", decision="BUY", confidence=None)
        store.record_cost(conn, run_id=rid, provider="deepseek",
                          model="m", in_tokens=100, out_tokens=50,
                          usd_estimate=0.25)
    # Also seed a brief row with run_ids so dispatch can find them
    store.insert_brief(conn, brief_id="b1", mode="event_alert",
                       scope="AAPL", generated_ts=_now(),
                       content_path="briefs/b1.md",
                       run_ids=["r1", "r2"], parent_brief_id=None,
                       trigger_event_id="ev1")

    job = {
        "job_id": 1,
        "job_type": "event_alert",
        "payload": json.dumps({"event_id": "ev1", "ticker": "AAPL"}),
        "trigger_event_id": "ev1",
    }
    result = dispatch_event_alert(conn, job, secretary=sec)
    assert result["cost_usd"] == pytest.approx(0.50)
    assert sorted(result["run_ids"]) == ["r1", "r2"]


@pytest.mark.unit
def test_dispatch_unknown_job_type_raises(setup):
    from tradingagents.orchestrator.dispatch import dispatch

    conn, data_dir = setup
    sec = MagicMock()
    job = {"job_id": 1, "job_type": "morning_digest", "payload": "{}",
           "trigger_event_id": None}
    with pytest.raises(ValueError, match="unknown job_type"):
        dispatch(conn, job, secretary=sec)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_worker_dispatch.py -v
```

Expected: ImportError on `dispatch`.

- [ ] **Step 3: Implement `dispatch.py`**

Create `tradingagents/orchestrator/dispatch.py`:

```python
"""Job dispatcher — routes leased jobs to the right handler.

Today only ``event_alert`` is supported. The DISPATCH map is the seam
F5 (morning_digest) extends.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict


log = logging.getLogger(__name__)


def dispatch_event_alert(
    conn: sqlite3.Connection,
    job: Dict[str, Any],
    *,
    secretary,                           # tradingagents.secretary.service.Secretary
) -> Dict[str, Any]:
    """Run an event_alert job. Returns the rollup dict the worker writes
    into queue_jobs (brief_id, run_ids JSON, cost_usd)."""
    payload = json.loads(job["payload"])
    event_id = payload["event_id"]
    ticker = payload["ticker"]
    job_id = job["job_id"]

    brief_id = secretary.compose_event_alert(
        event_id=event_id, ticker=ticker, job_id=job_id,
    )

    # Pull run_ids back from the brief row (compose_event_alert wrote them).
    brief = conn.execute(
        "SELECT run_ids FROM briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    run_ids = json.loads(brief["run_ids"]) if brief and brief["run_ids"] else []

    # Cost rollup: sum usd_estimate across all runs in this job.
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        row = conn.execute(
            f"SELECT COALESCE(SUM(usd_estimate), 0) "
            f"FROM costs WHERE run_id IN ({placeholders})",
            tuple(run_ids),
        ).fetchone()
        cost_usd = float(row[0])
    else:
        cost_usd = 0.0

    return {"brief_id": brief_id, "run_ids": run_ids, "cost_usd": cost_usd}


DISPATCH = {
    "event_alert": dispatch_event_alert,
    # F5 will add: "morning_digest": dispatch_morning_digest
}


def dispatch(
    conn: sqlite3.Connection,
    job: Dict[str, Any],
    *,
    secretary,
) -> Dict[str, Any]:
    handler = DISPATCH.get(job["job_type"])
    if handler is None:
        raise ValueError(f"unknown job_type: {job['job_type']!r}")
    return handler(conn, job, secretary=secretary)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_worker_dispatch.py -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/dispatch.py tests/orchestrator/test_worker_dispatch.py
git commit -m "orchestrator(dispatch): DISPATCH map + dispatch_event_alert with cost rollup"
```

---

## Task 15: Worker loop — lease, dispatch, mark, sweep on boot

**Files:**
- Create: `tradingagents/orchestrator/worker.py`
- Test: `tests/orchestrator/test_worker_loop.py`
- Test: `tests/orchestrator/test_stale_lease_sweep.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_stale_lease_sweep.py`:

```python
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


@pytest.mark.unit
def test_worker_sweeps_stale_leases_on_boot(tmp_path):
    """A run-loop iteration that starts with a stale 'running' job marks
    it as 'error' and then proceeds normally."""
    from tradingagents.orchestrator.worker import boot_sweep
    db = str(tmp_path / "iic.db")
    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload="{}", trigger_event_id="ev1")
    job = queue_store.lease_one(conn)
    conn.execute(
        "UPDATE queue_jobs SET started_ts = datetime('now', '-2 hour') "
        "WHERE job_id = ?", (job["job_id"],),
    )
    conn.commit()

    n = boot_sweep(conn, max_age_seconds=3600)
    assert n == 1
    row = conn.execute("SELECT state FROM queue_jobs WHERE job_id=?",
                        (job["job_id"],)).fetchone()
    assert row["state"] == "error"
```

Create `tests/orchestrator/test_worker_loop.py`:

```python
import json
import threading
import time
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def setup(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    raw = tmp_path / "data" / "events" / "ev1.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps({"text": "ev text"}))
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9, raw_path=str(raw),
                       status="triaged", deduped_of=None)
    return conn, str(tmp_path / "data")


@pytest.mark.unit
def test_drain_one_processes_a_queued_job(setup):
    from tradingagents.orchestrator.worker import drain_one
    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.return_value = "b1"
    store.insert_brief(conn, brief_id="b1", mode="event_alert",
                       scope="AAPL", generated_ts=_now(),
                       content_path="briefs/b1.md",
                       run_ids=[], parent_brief_id=None,
                       trigger_event_id="ev1")
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload=json.dumps({"event_id": "ev1",
                                                       "ticker": "AAPL"}),
                                  trigger_event_id="ev1")
    result = drain_one(conn, secretary=sec)
    assert result is True
    row = conn.execute(
        "SELECT * FROM queue_jobs WHERE trigger_event_id='ev1'"
    ).fetchone()
    assert row["state"] == "done"
    assert row["brief_id"] == "b1"
    assert row["finished_ts"] is not None


@pytest.mark.unit
def test_drain_one_returns_false_when_queue_empty(setup):
    from tradingagents.orchestrator.worker import drain_one
    conn, data_dir = setup
    sec = MagicMock()
    assert drain_one(conn, secretary=sec) is False


@pytest.mark.unit
def test_drain_one_marks_error_on_failure(setup):
    from tradingagents.orchestrator.worker import drain_one
    conn, data_dir = setup
    sec = MagicMock()
    sec.compose_event_alert.side_effect = RuntimeError("LLM died")
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload=json.dumps({"event_id": "ev1",
                                                       "ticker": "AAPL"}),
                                  trigger_event_id="ev1")
    drain_one(conn, secretary=sec)
    row = conn.execute(
        "SELECT * FROM queue_jobs WHERE trigger_event_id='ev1'"
    ).fetchone()
    assert row["state"] == "error"
    assert "LLM died" in row["error"]


@pytest.mark.unit
def test_drain_one_skipped_when_budget_blocks(setup):
    """When DailyBudgetGuard.gate() returns False, the job is not leased."""
    from tradingagents.orchestrator.worker import drain_one
    from tradingagents.orchestrator.guards import DailyBudgetGuard
    conn, data_dir = setup
    sec = MagicMock()
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload=json.dumps({"event_id": "ev1",
                                                       "ticker": "AAPL"}),
                                  trigger_event_id="ev1")
    # Make a guard that always blocks
    blocker = DailyBudgetGuard(enabled=True, daily_usd=0.0)
    result = drain_one(conn, secretary=sec, budget_guard=blocker)
    assert result is False
    # Job is still 'queued' (not leased)
    row = conn.execute(
        "SELECT state FROM queue_jobs WHERE trigger_event_id='ev1'"
    ).fetchone()
    assert row["state"] == "queued"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_worker_loop.py tests/orchestrator/test_stale_lease_sweep.py -v
```

Expected: ImportError on `worker`.

- [ ] **Step 3: Implement `worker.py`**

Create `tradingagents/orchestrator/worker.py`:

```python
"""F4 worker — leases queued jobs and dispatches by job_type.

Runs as `iic-worker.service`. Single-process; concurrency capped by
``max_concurrent_jobs`` (default 1). Per-job wall-clock cap enforced
via concurrent.futures timeout.
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

from tradingagents.persistence.db import connect
from tradingagents.orchestrator import queue_store
from tradingagents.orchestrator.dispatch import dispatch
from tradingagents.orchestrator.guards import DailyBudgetGuard


log = logging.getLogger(__name__)


def boot_sweep(conn: sqlite3.Connection, *, max_age_seconds: int) -> int:
    """One-shot sweep on worker startup. See spec R-F4-2."""
    return queue_store.sweep_stale_leases(conn, max_age_seconds=max_age_seconds)


def _build_secretary(config: dict, conn: sqlite3.Connection):
    """Same construction shape as cli/deepdive._build_secretary."""
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.secretary.service import Secretary
    client = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    )
    llm = client.get_llm()
    return Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)


def _execute_with_timeout(secretary, job: dict, timeout_seconds: int) -> dict:
    """Run dispatch() with a wall-clock cap. Raises TimeoutError on expiry."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        # Each dispatch() opens its own connection to the DB so we don't
        # hold the leasing connection across the (potentially long) graph runs.
        # The dispatch_event_alert handler reuses ``conn`` for the lightweight
        # brief/cost rollup queries only.
        from tradingagents.default_config import DEFAULT_CONFIG
        worker_conn = connect(DEFAULT_CONFIG["iic_db_path"])
        try:
            fut = ex.submit(dispatch, worker_conn, job, secretary=secretary)
            return fut.result(timeout=timeout_seconds)
        finally:
            worker_conn.close()


def drain_one(
    conn: sqlite3.Connection,
    *,
    secretary,
    budget_guard: Optional[DailyBudgetGuard] = None,
    job_timeout_seconds: int = 1200,
) -> bool:
    """Lease + dispatch + mark exactly one job. Returns True if a job ran."""
    if budget_guard is not None and not budget_guard.gate(conn):
        return False

    job = queue_store.lease_one(conn)
    if job is None:
        return False

    try:
        result = _execute_with_timeout(
            secretary, dict(job), job_timeout_seconds,
        )
        queue_store.mark_done(
            conn,
            job_id=job["job_id"],
            run_ids=result["run_ids"],
            brief_id=result["brief_id"],
            cost_usd=result["cost_usd"],
        )
        log.info("job %d done (brief=%s cost=$%.4f)",
                 job["job_id"], result["brief_id"], result["cost_usd"])
    except FuturesTimeout:
        queue_store.mark_error(
            conn, job_id=job["job_id"],
            error_msg=f"timeout after {job_timeout_seconds}s",
        )
        log.exception("job %d timed out", job["job_id"])
    except Exception as exc:
        queue_store.mark_error(
            conn, job_id=job["job_id"], error_msg=str(exc),
        )
        log.exception("job %d failed", job["job_id"])
    return True


_shutdown = False


def _install_signal_handlers():
    def _handler(signum, frame):
        global _shutdown
        _shutdown = True
        log.info("received signal %s; shutting down after current job", signum)
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def main(config: Optional[dict] = None) -> None:
    from tradingagents.default_config import DEFAULT_CONFIG
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    conn = connect(cfg["iic_db_path"])
    swept = boot_sweep(conn, max_age_seconds=3600)
    if swept:
        log.warning("boot sweep marked %d stale lease(s) as error", swept)

    secretary = _build_secretary(cfg, conn)
    budget = DailyBudgetGuard(
        enabled=cfg["daily_budget_enabled"],
        daily_usd=cfg["daily_budget_usd"],
    )
    job_timeout = cfg["worker_job_timeout_min"] * 60

    _install_signal_handlers()
    log.info("worker started: poll=%ss timeout=%dm budget_enabled=%s",
             cfg["worker_poll_interval_s"], cfg["worker_job_timeout_min"],
             budget.enabled)

    while not _shutdown:
        try:
            ran = drain_one(
                conn, secretary=secretary,
                budget_guard=budget, job_timeout_seconds=job_timeout,
            )
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("worker loop failure; sleeping 5s and continuing")
            time.sleep(5)
            continue
        if not ran:
            time.sleep(cfg["worker_poll_interval_s"])

    log.info("worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_worker_loop.py tests/orchestrator/test_stale_lease_sweep.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/orchestrator/worker.py tests/orchestrator/test_worker_loop.py tests/orchestrator/test_stale_lease_sweep.py
git commit -m "orchestrator(worker): drain_one + main + boot stale-lease sweep + per-job timeout"
```

---

## Task 16: CLI — `forge orchestrator promoter|worker|status`

**Files:**
- Modify: `cli/forge.py` — add `orchestrator` sub-app
- Test: `tests/cli/test_forge_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cli/test_forge_orchestrator.py`:

```python
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from typer.testing import CliRunner

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


runner = CliRunner()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "iic.db")
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", p)
    return p


@pytest.mark.unit
def test_orchestrator_status_shows_counts(db):
    from cli.forge import app
    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload="{}", trigger_event_id="ev1")
    result = runner.invoke(app, ["orchestrator", "status"])
    assert result.exit_code == 0, result.output
    assert "queued" in result.output.lower()
    assert "1" in result.output    # pending count


@pytest.mark.unit
def test_orchestrator_promoter_command_exists():
    from cli.forge import app
    # `--help` is the cheapest way to assert wiring without launching the loop.
    result = runner.invoke(app, ["orchestrator", "promoter", "--help"])
    assert result.exit_code == 0
    assert "promoter" in result.output.lower()


@pytest.mark.unit
def test_orchestrator_worker_command_exists():
    from cli.forge import app
    result = runner.invoke(app, ["orchestrator", "worker", "--help"])
    assert result.exit_code == 0
    assert "worker" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_forge_orchestrator.py -v
```

Expected: FAIL — `orchestrator` sub-app missing.

- [ ] **Step 3: Extend `cli/forge.py`**

Append to `cli/forge.py`:

```python
# ---------------------------------------------------------------------
# orchestrator sub-app (F4)
# ---------------------------------------------------------------------

orch_app = typer.Typer(name="orchestrator", help="F4 promoter + worker controls")
app.add_typer(orch_app, name="orchestrator")


@orch_app.command("promoter")
def orchestrator_promoter() -> None:
    """Run the promoter loop in the foreground (systemd wraps this)."""
    import logging
    from tradingagents.orchestrator.promoter import main
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()


@orch_app.command("worker")
def orchestrator_worker() -> None:
    """Run the worker loop in the foreground (systemd wraps this)."""
    import logging
    from tradingagents.orchestrator.worker import main
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()


@orch_app.command("status")
def orchestrator_status() -> None:
    """Quick view of queue depth + recent jobs + today's spend."""
    from tradingagents.orchestrator import queue_store
    conn = _conn()
    pending = queue_store.pending_count(conn)
    today_enqueued = queue_store.daily_enqueue_count(conn)
    today_cost = queue_store.daily_cost_total(conn)

    console.print(f"pending (queued+running): [bold]{pending}[/bold]")
    console.print(f"enqueued today          : {today_enqueued}")
    console.print(f"spend today (USD)       : ${today_cost:.4f}")

    rows = list(conn.execute(
        "SELECT job_id, job_type, state, enqueued_ts, finished_ts, "
        "brief_id, cost_usd, error "
        "FROM queue_jobs ORDER BY job_id DESC LIMIT 10"
    ))
    if not rows:
        console.print("(no jobs)")
        return
    t = Table("id", "type", "state", "enqueued", "finished", "brief", "$", "err")
    for r in rows:
        t.add_row(
            str(r["job_id"]), r["job_type"], r["state"],
            (r["enqueued_ts"] or "")[:19],
            (r["finished_ts"] or "")[:19],
            (r["brief_id"] or "")[:8],
            f"{(r['cost_usd'] or 0.0):.4f}",
            (r["error"] or "")[:40],
        )
    console.print(t)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_forge_orchestrator.py -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/forge.py tests/cli/test_forge_orchestrator.py
git commit -m "cli(forge): orchestrator promoter|worker|status sub-app"
```

---

## Task 17: systemd unit files (promoter + worker)

**Files:**
- Create: `ops/systemd/iic-promoter.service`
- Create: `ops/systemd/iic-worker.service`

No tests here — these are deployment artifacts. The boundary check happens during the live exit-gate window (Task 19) when `systemctl show … --property=NRestarts` must equal 0.

- [ ] **Step 1: Create the promoter unit**

Create `ops/systemd/iic-promoter.service`:

```ini
# /etc/systemd/system/iic-promoter.service
#
# IIC-FORGE F4 — promoter service
# Polls events table every 10s, enqueues event_alert jobs into queue_jobs.
# Defensive retry-internal: see tradingagents/orchestrator/promoter.py
# The exit-gate evaluator (scripts/f4_exit_gate.py) fails the gate if this
# unit's NRestarts > 0 during the observation window.

[Unit]
Description=IIC-FORGE — F4 promoter (events → queue_jobs)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.orchestrator.promoter
Restart=on-failure
RestartSec=30
MemoryMax=256M
CPUQuota=25%
StandardOutput=append:/var/log/iic/promoter.log
StandardError=append:/var/log/iic/promoter.log

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create the worker unit**

Create `ops/systemd/iic-worker.service`:

```ini
# /etc/systemd/system/iic-worker.service
#
# IIC-FORGE F4 — worker service
# Polls queue_jobs every 2s, leases one job at a time, runs 3 personas
# in parallel inside the job. MemoryMax allows for 3-persona parallelism;
# the F1 deep-dive baseline uses ~2GB RSS at peak.

[Unit]
Description=IIC-FORGE — F4 worker (queue_jobs → briefs)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.orchestrator.worker
Restart=on-failure
RestartSec=30
MemoryMax=4G
CPUQuota=200%
TimeoutStopSec=1500
StandardOutput=append:/var/log/iic/worker.log
StandardError=append:/var/log/iic/worker.log

[Install]
WantedBy=multi-user.target
```

(Note `TimeoutStopSec=1500` — 25 min — gives an in-flight job time to finish on SIGTERM. The worker's signal handler sets `_shutdown = True` and the loop exits after the current job completes.)

- [ ] **Step 3: Commit**

```bash
git add ops/systemd/iic-promoter.service ops/systemd/iic-worker.service
git commit -m "ops(systemd): F4 promoter + worker unit files (caps + Restart=on-failure)"
```

---

## Task 18: Runbook — `ops/runbooks/f4-exit-gate.md`

**Files:**
- Create: `ops/runbooks/f4-exit-gate.md`

- [ ] **Step 1: Write the runbook**

Create `ops/runbooks/f4-exit-gate.md`:

```markdown
# IIC-FORGE F4 — Exit-gate runbook

> Spec: [docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md](../../docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md) §9
> Evaluator: [scripts/f4_exit_gate.py](../../scripts/f4_exit_gate.py)

The F4 exit gate has two parts that pass independently:

1. **Synthetic-event smoke** — `pytest tests/smoke/test_f4_exit_gate.py` on the same commit. Must PASS.
2. **Live observation window** — 6–12 h with F3 adapters + F4 promoter+worker running on the dev machine. SLA `p95 ≤ 15 min` (or per the tiered rule when fewer than 3 briefs land).

## Pre-flight checklist

Run sequentially. Any failure → fix before proceeding.

1. **F3 stack healthy.**
   ```bash
   for svc in iic-sense-polygon iic-sense-rss iic-sense-gdelt iic-sense-macro \
              iic-sense-telegram iic-triage; do
       systemctl is-active "$svc" || { echo "❌ $svc not active"; exit 1; }
   done
   ```

2. **Watchlist non-empty.** The trigger rule requires `ticker ∈ watchlist`.
   ```bash
   forge watchlist list
   ```
   If empty: `forge watchlist add AAPL` (and the user's other standing tickers).

3. **Tickers reference table seeded.**
   ```bash
   sqlite3 ~/.tradingagents/iic.db "SELECT COUNT(*) FROM tickers WHERE active=1"
   # Expect ≥ 8000
   ```

4. **All cost guards confirmed OFF.** Gate observes the natural profile.
   ```bash
   python - <<'EOF'
   from tradingagents.default_config import DEFAULT_CONFIG as C
   for k in ("cost_guard_enabled", "trigger_backpressure_enabled",
             "trigger_daily_rate_enabled", "daily_budget_enabled"):
       assert C[k] is False, f"{k} must be False for the gate"
   print("all guards OFF ✓")
   EOF
   ```

5. **Synthetic smoke passes on the current commit.**
   ```bash
   cd /home/iic/TradingAgents/TradingAgents
   pytest tests/smoke/test_f4_exit_gate.py -v
   ```
   Must PASS.

6. **Disable unattended-upgrades for the window.**
   ```bash
   sudo systemctl stop unattended-upgrades.timer
   ```
   Re-enable after the gate completes.

7. **Promoter + worker units installed and enabled.**
   ```bash
   sudo cp ops/systemd/iic-promoter.service ops/systemd/iic-worker.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now iic-promoter iic-worker
   ```

## Run procedure

1. **Record `--since` timestamp.**
   ```bash
   export F4_GATE_SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   echo "$F4_GATE_SINCE" > /tmp/f4_gate_since
   ```

2. **Hold sleep for the window.**
   ```bash
   systemd-inhibit --what=sleep --who="F4 exit gate" \
                   --why="12h orchestrator soak" sleep infinity &
   ```

3. **Walk away.** Recommended window: 12 h.

4. **At window end, run the evaluator.**
   ```bash
   F4_GATE_SINCE=$(cat /tmp/f4_gate_since)
   python scripts/f4_exit_gate.py --since "$F4_GATE_SINCE" --window-hours 12 \
       > docs/superpowers/artifacts/$(date -u +%Y-%m-%d)-f4-exit-gate-report.md
   ```

5. **Review the artifact.** Sign the operator line at the bottom.

6. **Re-enable unattended-upgrades and stop the inhibit:**
   ```bash
   sudo systemctl start unattended-upgrades.timer
   kill %1   # stop systemd-inhibit background job
   ```

## Pass criteria

Cited from spec §9:

- `NRestarts == 0` for `iic-promoter` and `iic-worker` over the window. (Restart audit in the artifact.)
- Synthetic-smoke result: PASS (recorded in the artifact alongside the live signal).
- Live SLA (tiered):
  - **≥ 3 briefs** during the window → `p95 latency ≤ 15 min`.
  - **1–2 briefs** → `max latency ≤ 15 min` + operator note confirming the window was "normal".
  - **0 briefs** → not a pass signal; re-run during a more active window.

## Failure modes and recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| Promoter restarts > 0 | unhandled exception in the loop body | grep `/var/log/iic/promoter.log` for traceback; the defensive `except Exception` should have swallowed it — file an issue |
| Worker restarts > 0 | OOM during persona fan-out, or an unhandled exception outside `drain_one`'s try/except | check `journalctl -u iic-worker` for `Killed (out of memory)`; raise `MemoryMax` if needed |
| Latency p95 > 15 min | personas slow, LLM upstream lag, queue backlog | check per-job timing in the artifact; consider falling back to `quick_think_llm` for the synthesis call (open question #2 in the spec) |
| 0 briefs during window | quiet news period or watchlist too small | spec §9 explicitly: re-run during an active window; do not pad with synthetic |
| `error` state jobs | LLM crash, malformed event, timeout | inspect `queue_jobs.error` via `forge orchestrator status`; the underlying `runs` rows have artifacts under `data/runs/<run_id>/` |
```

- [ ] **Step 2: Commit**

```bash
git add ops/runbooks/f4-exit-gate.md
git commit -m "ops(runbook): F4 exit-gate pre-flight + run procedure + failure modes"
```

---

## Task 19: Exit-gate evaluator — `scripts/f4_exit_gate.py`

**Files:**
- Create: `scripts/f4_exit_gate.py`
- Test: `tests/orchestrator/test_f4_exit_gate_evaluator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/orchestrator/test_f4_exit_gate_evaluator.py`:

```python
import json
import pytest
from datetime import datetime, timedelta, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "iic.db")
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", p)
    return p


def _seed_brief_with_latency(conn, *, latency_seconds, ev_id, brief_id):
    base = datetime.now(timezone.utc) - timedelta(minutes=30)
    ev_ts = base.isoformat()
    brief_ts = (base + timedelta(seconds=latency_seconds)).isoformat()
    store.insert_event(conn, event_id=ev_id, source="rss",
                       ingested_ts=ev_ts, salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert",
                       scope="AAPL", generated_ts=brief_ts,
                       content_path=f"briefs/{brief_id}.md",
                       run_ids=["r"], parent_brief_id=None,
                       trigger_event_id=ev_id)


@pytest.mark.unit
def test_evaluator_computes_latency_percentiles(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    for i, sec in enumerate([60, 180, 600, 800, 900]):
        _seed_brief_with_latency(conn, latency_seconds=sec,
                                  ev_id=f"ev{i}", brief_id=f"b{i}")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["brief_count"] == 5
    # p95 of [60, 180, 600, 800, 900] ≈ 900s
    assert result["latency_p95_s"] >= 800
    assert result["latency_p95_s"] <= 900


@pytest.mark.unit
def test_evaluator_passes_when_p95_under_15min(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    for i, sec in enumerate([60, 120, 180, 240, 300]):
        _seed_brief_with_latency(conn, latency_seconds=sec,
                                  ev_id=f"ev{i}", brief_id=f"b{i}")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["sla_pass"] is True
    assert result["sla_rule_applied"] == "p95"


@pytest.mark.unit
def test_evaluator_uses_max_rule_when_one_or_two_briefs(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    _seed_brief_with_latency(conn, latency_seconds=500,
                              ev_id="ev0", brief_id="b0")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["brief_count"] == 1
    assert result["sla_rule_applied"] == "max"
    assert result["sla_pass"] is True   # 500s < 15min


@pytest.mark.unit
def test_evaluator_marks_zero_briefs_as_inconclusive(db):
    from scripts.f4_exit_gate import evaluate
    conn = connect(db)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = evaluate(conn, since=since, window_hours=2)
    assert result["brief_count"] == 0
    assert result["sla_pass"] is None   # inconclusive
    assert result["sla_rule_applied"] == "none"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orchestrator/test_f4_exit_gate_evaluator.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the evaluator**

Create `scripts/f4_exit_gate.py`:

```python
#!/usr/bin/env python
"""F4 exit-gate evaluator.

Reads queue_jobs / briefs / events over a window and renders the artifact
markdown to stdout. The operator commits the artifact under
docs/superpowers/artifacts/.

Usage:
    python scripts/f4_exit_gate.py --since 2026-05-27T08:00:00Z [--window-hours 12]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f, c = int(k), int(k) + 1
    if c >= len(s):
        return s[-1]
    return s[f] + (s[c] - s[f]) * (k - f)


def _latency_seconds(ev_ts: str, brief_ts: str) -> float:
    a = datetime.fromisoformat(ev_ts.replace("Z", "+00:00"))
    b = datetime.fromisoformat(brief_ts.replace("Z", "+00:00"))
    return (b - a).total_seconds()


def _systemctl_nrestarts(unit: str) -> int:
    try:
        out = subprocess.check_output(
            ["systemctl", "show", unit, "--property=NRestarts"],
            text=True, stderr=subprocess.DEVNULL,
        )
        return int(out.strip().split("=")[1])
    except Exception:
        return -1   # unknown (not on this host, etc.)


def evaluate(
    conn: sqlite3.Connection, *, since: datetime, window_hours: int = 12,
) -> Dict[str, Any]:
    until = since + timedelta(hours=window_hours)

    rows = list(conn.execute(
        "SELECT b.brief_id, b.generated_ts, b.trigger_event_id, b.scope, "
        "       e.ingested_ts, q.cost_usd, q.state "
        "FROM briefs b "
        "JOIN events e ON e.event_id = b.trigger_event_id "
        "LEFT JOIN queue_jobs q ON q.brief_id = b.brief_id "
        "WHERE b.mode = 'event_alert' "
        "  AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))

    per_brief = []
    latencies = []
    total_cost = 0.0
    for r in rows:
        lat = _latency_seconds(r["ingested_ts"], r["generated_ts"])
        latencies.append(lat)
        cost = float(r["cost_usd"] or 0.0)
        total_cost += cost
        per_brief.append({
            "brief_id": r["brief_id"],
            "ticker": r["scope"],
            "event_id": r["trigger_event_id"],
            "ingested_ts": r["ingested_ts"],
            "brief_ts": r["generated_ts"],
            "latency_min": lat / 60.0,
            "cost_usd": cost,
        })

    n = len(per_brief)
    if n >= 3:
        p95 = _percentile(latencies, 0.95)
        sla_pass = p95 <= 15 * 60
        sla_rule = "p95"
    elif n >= 1:
        max_lat = max(latencies)
        sla_pass = max_lat <= 15 * 60
        sla_rule = "max"
    else:
        sla_pass = None
        sla_rule = "none"

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "brief_count": n,
        "per_brief": per_brief,
        "latencies_s": latencies,
        "latency_p50_s": _percentile(latencies, 0.50) if n else 0.0,
        "latency_p95_s": _percentile(latencies, 0.95) if n else 0.0,
        "latency_p99_s": _percentile(latencies, 0.99) if n else 0.0,
        "total_cost_usd": total_cost,
        "sla_pass": sla_pass,
        "sla_rule_applied": sla_rule,
        "promoter_nrestarts": _systemctl_nrestarts("iic-promoter"),
        "worker_nrestarts": _systemctl_nrestarts("iic-worker"),
    }


def render_md(result: Dict[str, Any]) -> str:
    out: List[str] = []
    today = datetime.now(timezone.utc).date().isoformat()
    out.append(f"# F4 exit-gate report — {today}")
    out.append("")
    out.append(f"**Window:** `{result['since']}` → `{result['until']}`")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"- briefs produced: **{result['brief_count']}**")
    out.append(f"- total cost: **${result['total_cost_usd']:.4f}**")
    out.append(f"- latency p50 / p95 / p99: "
               f"{result['latency_p50_s']/60:.2f} / "
               f"{result['latency_p95_s']/60:.2f} / "
               f"{result['latency_p99_s']/60:.2f} min")
    out.append("")
    out.append("## Restart audit")
    out.append("")
    out.append(f"- iic-promoter NRestarts: `{result['promoter_nrestarts']}` "
               f"(must be 0; -1 = host check unavailable)")
    out.append(f"- iic-worker NRestarts:   `{result['worker_nrestarts']}` "
               f"(must be 0)")
    out.append("")
    out.append("## Per-brief table")
    out.append("")
    out.append("| brief_id | ticker | event_id | ingested | brief | latency (min) | cost |")
    out.append("|---|---|---|---|---|---|---|")
    for b in result["per_brief"]:
        out.append(
            f"| `{b['brief_id'][:8]}` | {b['ticker']} | `{b['event_id'][:8]}` "
            f"| {b['ingested_ts'][:19]} | {b['brief_ts'][:19]} "
            f"| {b['latency_min']:.2f} | ${b['cost_usd']:.4f} |"
        )
    out.append("")
    out.append("## SLA verdict")
    out.append("")
    sla_pass = result["sla_pass"]
    rule = result["sla_rule_applied"]
    if sla_pass is None:
        out.append("- **inconclusive** — 0 briefs landed in window. Re-run during a more active period.")
    elif sla_pass:
        out.append(f"- **PASS** (rule: {rule}, ≤ 15 min)")
    else:
        out.append(f"- **FAIL** (rule: {rule}, > 15 min)")
    out.append("")
    out.append("## Synthetic-smoke result")
    out.append("")
    out.append("- `tests/smoke/test_f4_exit_gate.py` on commit `<COMMIT>`: __PASS__ / __FAIL__ (fill manually)")
    out.append("")
    out.append("## Operator sign-off")
    out.append("")
    out.append("- [ ] Operator confirms restart audit and SLA verdict above.")
    out.append("- Notes: ____________________________________________________________")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True,
                    help="ISO-8601 start of the gate window, e.g. 2026-05-27T08:00:00Z")
    ap.add_argument("--window-hours", type=int, default=12)
    args = ap.parse_args()

    db_path = os.environ.get("TRADINGAGENTS_IIC_DB_PATH") or DEFAULT_CONFIG["iic_db_path"]
    conn = connect(db_path)
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    result = evaluate(conn, since=since, window_hours=args.window_hours)
    sys.stdout.write(render_md(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/orchestrator/test_f4_exit_gate_evaluator.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/f4_exit_gate.py tests/orchestrator/test_f4_exit_gate_evaluator.py
git commit -m "scripts: F4 exit-gate evaluator (latency percentiles + restart audit)"
```

---

## Task 20: Smoke test + final suite verification

**Files:**
- Create: `tests/smoke/test_f4_exit_gate.py`

The synthetic-event smoke from spec D8. Boots promoter + worker as threads, directly inserts a synthetic `events` row (bypassing F3 triage in CI), waits up to 60s, asserts a brief landed.

- [ ] **Step 1: Write the smoke test**

Create `tests/smoke/test_f4_exit_gate.py`:

```python
import json
import threading
import time
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store, promoter, worker


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.smoke
def test_f4_synthetic_event_produces_brief_under_60s(tmp_path, monkeypatch):
    """End-to-end: inject a salient triaged event, run promoter once,
    run drain_one once, assert a brief lands.

    Bypasses the real graph by mocking `Secretary.compose_event_alert`."""
    db = str(tmp_path / "iic.db")
    data_dir = str(tmp_path / "data")
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", db)
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", data_dir)

    # Reload config so the env vars take effect.
    import importlib
    import tradingagents.default_config as m
    importlib.reload(m)

    # Seed: watchlist + raw event file + events row
    conn = connect(db)
    store.upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])
    (Path(data_dir) / "events").mkdir(parents=True, exist_ok=True)
    raw = Path(data_dir) / "events" / "ev1.json"
    raw.write_text(json.dumps({"text": "Apple beats Q3 earnings by 12%.",
                               "source": "polygon_news"}))
    store.insert_event(conn, event_id="ev1", source="polygon_news",
                       ingested_ts=_now(), salience=0.9,
                       raw_path=str(raw),
                       status="triaged", deduped_of=None)
    store.insert_event_ticker(conn, event_id="ev1", ticker="AAPL",
                              confidence=0.95)

    # Promoter: one cycle
    n = promoter.run_once(conn,
                          salience_threshold=0.7,
                          ticker_conf_threshold=0.8,
                          batch_size=10, cooldown_min=60)
    assert n == 1, "promoter should have enqueued one job"
    assert queue_store.pending_count(conn) == 1

    # Worker: mock secretary to avoid real LLM/graph
    sec = MagicMock()

    def fake_compose(event_id, ticker, job_id):
        bid = f"b-{event_id}"
        (Path(data_dir) / "briefs").mkdir(parents=True, exist_ok=True)
        (Path(data_dir) / "briefs" / f"{bid}.md").write_text(
            f"# Event Alert\n\nTrigger: {event_id} / {ticker}\n"
        )
        store.insert_brief(
            conn, brief_id=bid, mode="event_alert", scope=ticker,
            generated_ts=_now(),
            content_path=f"briefs/{bid}.md",
            run_ids=[], parent_brief_id=None,
            trigger_event_id=event_id,
        )
        return bid
    sec.compose_event_alert = lambda **kw: fake_compose(
        kw["event_id"], kw["ticker"], kw["job_id"],
    )

    t0 = time.time()
    worker.drain_one(conn, secretary=sec, job_timeout_seconds=30)
    elapsed = time.time() - t0
    assert elapsed < 60, f"drain_one took {elapsed:.1f}s, expected < 60s"

    # Assertions
    job = conn.execute("SELECT * FROM queue_jobs WHERE trigger_event_id='ev1'").fetchone()
    assert job["state"] == "done"
    assert job["brief_id"] is not None

    brief = store.get_brief(conn, brief_id=job["brief_id"])
    assert brief is not None
    assert brief["trigger_event_id"] == "ev1"
    md_path = Path(data_dir) / brief["content_path"]
    assert md_path.exists()
    assert "AAPL" in md_path.read_text()

    # SLA assertion: brief_ts - event_ts < 60s
    ev = store.get_event(conn, event_id="ev1")
    latency = (
        datetime.fromisoformat(brief["generated_ts"].replace("Z", "+00:00"))
        - datetime.fromisoformat(ev["ingested_ts"].replace("Z", "+00:00"))
    ).total_seconds()
    assert latency < 60, f"latency {latency:.1f}s exceeded 60s CI bound"
```

- [ ] **Step 2: Run the smoke**

```bash
pytest tests/smoke/test_f4_exit_gate.py -v
```

Expected: PASS within seconds.

- [ ] **Step 3: Run the full F4 + persistence + smoke test suite**

```bash
pytest tests/orchestrator/ tests/persistence/ tests/cli/test_forge_orchestrator.py \
       tests/smoke/test_f1_exit_gate.py tests/smoke/test_f2_exit_gate.py \
       tests/smoke/test_f3_exit_gate.py tests/smoke/test_f4_exit_gate.py \
       tests/test_default_config_f4.py -v
```

Expected: every test PASSES. If any pre-existing F1/F2/F3 test fails, investigate before committing — the schema changes (`ALTER`s) and `insert_brief` signature change are the most likely culprits.

- [ ] **Step 4: Run the FULL test suite once**

```bash
pytest -v 2>&1 | tail -40
```

Inspect the final summary line. Pass rate must equal the pre-F4 baseline (existing test count) + the new F4 tests. No regressions.

- [ ] **Step 5: Final commit**

```bash
git add tests/smoke/test_f4_exit_gate.py
git commit -m "test(smoke): F4 exit-gate synthetic-event end-to-end (< 60s SLA)"
```

- [ ] **Step 6: Push the branch and open a PR**

```bash
git push -u origin feat/iic-forge-07-f4
gh pr create --title "feat(F4): autonomous trigger loop (promoter + worker + compose_event_alert)" \
             --body "$(cat <<'EOF'
## Summary

Implements IIC-FORGE F4 per [docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md](docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md):

- `iic-promoter.service` polls events table → enqueues event_alert jobs (atomic enqueue + suppression cooldown).
- `iic-worker.service` leases jobs, dispatches to `Secretary.compose_event_alert(event_id, ticker, job_id)` — replaces the F1 `NotImplementedError` stub.
- 5 append-only `ALTER TABLE ADD COLUMN` statements on `queue_jobs` / `briefs` / `runs` for SLA + cost telemetry.
- All four cost/backpressure guards ship `enabled=False` per Appendix A.
- Exit-gate evaluator + runbook.

## Test plan

- [ ] `pytest tests/orchestrator/ -v` — all unit + integration tests pass.
- [ ] `pytest tests/smoke/test_f4_exit_gate.py -v` — synthetic CI smoke passes (< 60s SLA).
- [ ] `pytest -v` — full suite, no regressions.
- [ ] Live exit-gate window (per `ops/runbooks/f4-exit-gate.md`) — operator follow-up.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

*End of IIC-FORGE-07 implementation plan. After the live exit-gate window completes successfully, save the artifact at `docs/superpowers/artifacts/2026-MM-DD-f4-exit-gate-report.md` and merge the PR.*
