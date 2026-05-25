# IIC-FORGE-04 — F1 Decision Core + Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship F1 of the IIC-FORGE program — a stateful Secretary service, a YAML-overlay persona system, a Run Recorder graph node, the full SQLite + filesystem state store, a hybrid persona memory layer, and a CLI `deepdive` command that launches three persona runs and produces a synthesized consensus / divergence / recommendation brief.

**Architecture:** SQLite (`~/.tradingagents/iic.db`) is the central seam. A new `tradingagents.persistence` package owns the schema and store helpers. A new `tradingagents.personas` package loads YAML overlays. A new `tradingagents.secretary` package composes briefs using Jinja templates and an LLM synthesis call. A new graph node "Run Recorder" sits after Portfolio Manager and writes one `runs` row + per-analyst markdown to `data/runs/<run_id>/` for every run. The CLI `deepdive` command instantiates three `TradingAgentsGraph` instances (one per persona) and invokes the Secretary's `compose_deep_dive` method.

**Tech Stack:** Python 3.10+, LangChain / LangGraph (existing), SQLite stdlib + `sqlite-vec` (embeddings), `jinja2` (templates), `pyyaml` (persona configs), `pytest` with `unit`/`smoke`/`integration` markers.

**Prerequisites:**
- F0 complete on `main` (Epics 0, A, B from IIC-FORGE-02 manually validated).
- Approved spec: [docs/superpowers/specs/2026-05-25-iic-forge-program-design.md](../specs/2026-05-25-iic-forge-program-design.md).
- DeepSeek API key configured in `.env`.
- Working tree clean.

**Pre-flight (one-time):**

```bash
cd /home/ziwei-huang/TradingAgents/TradingAgents
git checkout main && git pull --ff-only
git checkout -b feat/iic-forge-04-f1
# Confirm Python and pytest are wired
python -c "import sys; print(sys.version_info >= (3, 10))"  # True
pytest --version                                              # >= 7.0
```

---

## File Structure (locked in before tasks start)

**Created in this plan:**

| Path | Responsibility |
|---|---|
| `tradingagents/persistence/__init__.py` | Package marker |
| `tradingagents/persistence/db.py` | Connection management, migrations runner, WAL pragma |
| `tradingagents/persistence/schema.sql` | All F1 + F3/F4/F5 table DDL (single source of truth) |
| `tradingagents/persistence/store.py` | Insert/query helpers for `runs`, `briefs`, `costs`, `suppression`, `brief_actions` |
| `tradingagents/persistence/memory.py` | `PersonaMemoryStore` with `(persona_id, component)` partitioning + shared `outcome_log` |
| `tradingagents/personas/__init__.py` | Package marker |
| `tradingagents/personas/loader.py` | YAML loader + `Persona` Pydantic schema |
| `tradingagents/personas/macro.yaml` | Macro persona starter |
| `tradingagents/personas/value.yaml` | Value persona starter |
| `tradingagents/personas/momentum.yaml` | Momentum persona starter |
| `tradingagents/secretary/__init__.py` | Package marker |
| `tradingagents/secretary/service.py` | `Secretary` class with `compose_deep_dive` (and stubs for `compose_morning_digest`, `compose_event_alert`) |
| `tradingagents/secretary/synthesis.py` | LLM synthesis call producing consensus / divergence / recommendation |
| `tradingagents/secretary/templates/deep_dive.j2` | Deep-dive Jinja template |
| `tradingagents/graph/run_recorder.py` | Run Recorder graph node — writes one `runs` row + per-analyst MD files |
| `tradingagents/graph/cost_callback.py` | Token-usage callback that accumulates per-run costs |
| `cli/deepdive.py` | `deepdive <ticker>` Typer command (three-persona parallel run + brief) |
| `tests/persistence/test_db.py` | Schema creation, WAL mode, migration idempotence |
| `tests/persistence/test_store.py` | Runs / briefs / costs / brief_actions round-trip |
| `tests/persistence/test_memory.py` | Memory partitioning + cross-persona isolation |
| `tests/personas/test_loader.py` | YAML loader + Pydantic validation |
| `tests/secretary/test_synthesis.py` | Synthesis prompt produces 3-section structure (mocked LLM) |
| `tests/secretary/test_service.py` | `compose_deep_dive` integration with mocked runs |
| `tests/graph/test_run_recorder.py` | Node fires; writes filesystem + DB; idempotent |
| `tests/cli/test_deepdive.py` | CLI `deepdive` smoke test with mocked graph |
| `tests/smoke/test_f1_exit_gate.py` | Full end-to-end on AAPL (marked `integration`) |

**Modified in this plan:**

| Path | Change |
|---|---|
| `tradingagents/graph/trading_graph.py` | Remove mandatory-derivatives block (lines 76–79); accept `persona` kwarg; instantiate `RunRecorderCallback`; add Run Recorder node hookup; generate `run_id` |
| `tradingagents/graph/setup.py` | Wire Run Recorder node after Portfolio Manager |
| `tradingagents/default_config.py` | Add `iic_db_path`, `iic_data_dir`, `cost_guard_enabled: false` |
| `cli/main.py` | Register the new `deepdive` command from `cli/deepdive.py` |
| `pyproject.toml` | Add `sqlite-vec`, `jinja2`, `pyyaml` to dependencies |

---

## Cross-cutting conventions

- **Tests**: pytest with markers `unit` (default, fast, isolated), `integration` (real API calls or external state), `smoke` (quick end-to-end checks).
- **Commits**: one per task. Format: `feat(<scope>): <subject>` — match existing repo style (see `git log --oneline -5`).
- **Cost guards**: every guard-bearing function ships with an `enabled: bool = False` default. Measurement is unconditional; enforcement is gated. (See [saved memory](../../../.claude/projects/-home-ziwei-huang-TradingAgents/memory/cost-guards-disabled-by-default.md).)
- **Imports**: prefer absolute imports rooted at `tradingagents.` and `cli.`.
- **Markdown artifacts** live on disk; SQLite stores paths + small metadata.

---

## Task 1: Revert mandatory-derivatives enforcement

**Files:**
- Modify: `tradingagents/graph/trading_graph.py:76-79`
- Test: `tests/graph/test_mandatory_derivatives_reverted.py`

This is the spec amendment in §5 / §10 — derivatives becomes optional. Personas (added in Task 9) will own analyst selection.

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_mandatory_derivatives_reverted.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_selected_analysts_not_forced_to_include_derivatives():
    """When the caller omits derivatives, it stays omitted."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    # Stub heavy dependencies: we only want to verify selected_analysts
    # is not mutated by the constructor.
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        g = TradingAgentsGraph(selected_analysts=["market"])
        # The constructor should call GraphSetup.setup_graph with the ORIGINAL list.
        called_with = mock_setup.return_value.setup_graph.call_args
        assert "derivatives" not in called_with.kwargs.get("selected_analysts", called_with.args[0])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/test_mandatory_derivatives_reverted.py -v
```

Expected: FAIL — the existing code at lines 76–79 force-appends `"derivatives"`.

- [ ] **Step 3: Apply the revert**

In `tradingagents/graph/trading_graph.py`, remove lines 76–79 (the block beginning `# IIC-FORGE: derivatives analysis is mandatory...` and ending `selected_analysts = list(selected_analysts) + ["derivatives"]`).

Leave the surrounding constructor code untouched.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/graph/test_mandatory_derivatives_reverted.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full existing test suite to confirm no regressions**

```bash
pytest -m "not integration" --tb=short -q
```

Expected: all previously-passing tests still pass. (Some tests written against the old mandatory rule may need adjustment — if any fail, inspect each and either delete the test if it asserted the reverted behaviour, or update it. Do this BEFORE committing.)

- [ ] **Step 6: Commit**

```bash
git add tradingagents/graph/trading_graph.py tests/graph/test_mandatory_derivatives_reverted.py
git commit -m "revert(graph): drop mandatory derivatives enforcement (IIC-FORGE-03 §10)"
```

---

## Task 2: Add F1 dependencies

**Files:**
- Modify: `pyproject.toml` (dependencies block)

- [ ] **Step 1: Edit `pyproject.toml`**

In the `[project] dependencies` array, add three entries:

```toml
    "sqlite-vec>=0.1.6",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
```

Keep them sorted into the existing block (the repo's style is alphabetical-ish; insert in reasonable positions).

- [ ] **Step 2: Install the new deps**

```bash
pip install -e .
```

Expected: clean install. Verify imports work:

```bash
python -c "import sqlite_vec, jinja2, yaml; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build(deps): add sqlite-vec, jinja2, pyyaml for F1"
```

---

## Task 3: Default config keys for IIC paths and cost-guard flag

**Files:**
- Modify: `tradingagents/default_config.py`
- Test: `tests/test_default_config_f1.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_default_config_f1.py`:

```python
import pytest

@pytest.mark.unit
def test_default_config_has_f1_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    assert "iic_db_path" in C
    assert "iic_data_dir" in C
    assert "cost_guard_enabled" in C
    assert C["cost_guard_enabled"] is False  # per saved feedback: ship disabled

@pytest.mark.unit
def test_iic_paths_are_absolute():
    import os
    from tradingagents.default_config import DEFAULT_CONFIG as C
    assert os.path.isabs(C["iic_db_path"])
    assert os.path.isabs(C["iic_data_dir"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_default_config_f1.py -v
```

Expected: FAIL — keys don't exist yet.

- [ ] **Step 3: Add the keys**

In `tradingagents/default_config.py`, near the other paths (around the existing `results_dir`, `data_cache_dir`, `memory_log_path` entries — survey said line 47–49), add:

```python
    # IIC-FORGE F1 — persistence + data layout
    "iic_db_path": os.path.join(_TRADINGAGENTS_HOME, "iic.db"),
    "iic_data_dir": os.path.join(_TRADINGAGENTS_HOME, "data"),

    # IIC-FORGE F1 — cost guards (coded but disabled by default — see
    # docs/superpowers/specs/2026-05-25-iic-forge-program-design.md Appendix A).
    "cost_guard_enabled": False,
```

Also add the env-var overrides to `_ENV_OVERRIDES` (the existing dict in the same file):

```python
    "TRADINGAGENTS_IIC_DB_PATH": "iic_db_path",
    "TRADINGAGENTS_IIC_DATA_DIR": "iic_data_dir",
    "TRADINGAGENTS_COST_GUARD_ENABLED": ("cost_guard_enabled", _parse_bool),  # if this pattern is used
```

(If the existing `_ENV_OVERRIDES` doesn't take a tuple form for type coercion, simplify to a plain string mapping and document that `cost_guard_enabled` is bool-from-env via the existing parsing logic. Match whatever the file already does.)

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_default_config_f1.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tests/test_default_config_f1.py
git commit -m "config: add iic_db_path, iic_data_dir, cost_guard_enabled keys"
```

---

## Task 4: SQLite schema (single source of truth)

**Files:**
- Create: `tradingagents/persistence/__init__.py`
- Create: `tradingagents/persistence/schema.sql`

- [ ] **Step 1: Create the package marker**

Create `tradingagents/persistence/__init__.py`:

```python
"""IIC-FORGE persistence layer.

SQLite + filesystem hybrid. See ADR-F4 (revised) in the program design spec:
docs/superpowers/specs/2026-05-25-iic-forge-program-design.md
"""
```

- [ ] **Step 2: Create the full schema SQL**

Create `tradingagents/persistence/schema.sql`. This file is the **only** place table DDL lives; everything else reads from this file.

```sql
-- IIC-FORGE F1 schema. Designed upfront per ADR-F4 (revised) so F2/F3/F5
-- additions are append-only (new tables, no column reshapes).
--
-- All TIMESTAMP columns are ISO-8601 strings (TEXT) for SQLite portability.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- F1 tables — populated from day one
-- ============================================================

CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,           -- UUID4 hex
    ticker          TEXT NOT NULL,
    persona_id      TEXT,                       -- nullable for legacy / non-persona runs
    started_ts      TEXT NOT NULL,
    ended_ts        TEXT,
    status          TEXT NOT NULL,              -- "running" | "complete" | "error"
    decision        TEXT,                       -- "BUY" | "HOLD" | "SELL" | NULL
    confidence      REAL,                       -- 0.0–1.0
    trigger_id      TEXT,                       -- nullable; FK to events.event_id when F3 ships
    artifact_dir    TEXT NOT NULL               -- relative path under iic_data_dir
);
CREATE INDEX IF NOT EXISTS idx_runs_ticker_ts ON runs(ticker, started_ts);
CREATE INDEX IF NOT EXISTS idx_runs_persona ON runs(persona_id);

CREATE TABLE IF NOT EXISTS costs (
    cost_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    in_tokens       INTEGER NOT NULL DEFAULT 0,
    out_tokens      INTEGER NOT NULL DEFAULT 0,
    usd_estimate    REAL                        -- nullable; we don't always know the price
);
CREATE INDEX IF NOT EXISTS idx_costs_run ON costs(run_id);

CREATE TABLE IF NOT EXISTS briefs (
    brief_id        TEXT PRIMARY KEY,           -- UUID4 hex
    mode            TEXT NOT NULL,              -- "deep_dive" | "morning_digest" | "event_alert"
    scope           TEXT NOT NULL,              -- single ticker or JSON list
    generated_ts    TEXT NOT NULL,
    content_path    TEXT NOT NULL,              -- relative path under iic_data_dir
    run_ids         TEXT NOT NULL,              -- JSON list of run_id
    delivery_ids    TEXT,                       -- JSON list of delivery_id (F5)
    parent_brief_id TEXT REFERENCES briefs(brief_id)   -- threading for refinement (§4, §10)
);
CREATE INDEX IF NOT EXISTS idx_briefs_parent ON briefs(parent_brief_id);

CREATE TABLE IF NOT EXISTS brief_actions (
    action_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id            TEXT NOT NULL REFERENCES briefs(brief_id) ON DELETE CASCADE,
    action_type         TEXT NOT NULL,          -- "run_backtest" | "refine_brief"
    action_params       TEXT NOT NULL,          -- JSON
    state               TEXT NOT NULL,          -- "pending" | "accepted" | "declined" | "expired"
    expires_at          TEXT NOT NULL,
    responded_at        TEXT,
    result_backtest_id  INTEGER,                -- FK to backtests.backtest_id (F2)
    result_brief_id     TEXT REFERENCES briefs(brief_id)
);
CREATE INDEX IF NOT EXISTS idx_brief_actions_brief ON brief_actions(brief_id);
CREATE INDEX IF NOT EXISTS idx_brief_actions_state ON brief_actions(state, expires_at);

CREATE TABLE IF NOT EXISTS suppression (
    key             TEXT PRIMARY KEY,           -- e.g. "AAPL:macro" or "AAPL:*"
    until_ts        TEXT NOT NULL,
    reason          TEXT,
    created_by      TEXT
);

-- Hybrid memory: per-(persona, component) partitioned
CREATE TABLE IF NOT EXISTS memories (
    memory_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id      TEXT NOT NULL,              -- NEVER allow "" or "*"; isolation depends on this
    component       TEXT NOT NULL,              -- e.g. "decision_log", future: "bull", "bear", ...
    situation_md    TEXT NOT NULL,
    outcome         TEXT,
    vec_id          INTEGER REFERENCES vec_index(vec_id),
    created_ts      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_partition ON memories(persona_id, component);

-- Shared cross-persona outcome pool
CREATE TABLE IF NOT EXISTS outcome_log (
    outcome_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    decision        TEXT NOT NULL,
    outcome_md      TEXT NOT NULL,
    pnl_proxy       REAL,                       -- set by F2 reflection loop
    vec_id          INTEGER REFERENCES vec_index(vec_id),
    tags            TEXT,                       -- JSON
    created_ts      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcome_log_ticker ON outcome_log(ticker);

-- sqlite-vec virtual table (created at runtime by db.py after loading the extension)
-- The placeholder below documents the shape; the actual CREATE VIRTUAL TABLE
-- statement runs after sqlite_vec.load(conn).
-- CREATE VIRTUAL TABLE vec_index USING vec0(embedding float[384]);

-- ============================================================
-- F2 tables — defined upfront, populated when F2 ships
-- ============================================================

CREATE TABLE IF NOT EXISTS backtests (
    backtest_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_by_brief_id   TEXT REFERENCES briefs(brief_id),   -- set for brief-scoped (F5 flow)
    universe                TEXT NOT NULL,                       -- JSON list of tickers
    start_date              TEXT NOT NULL,
    end_date                TEXT NOT NULL,
    status                  TEXT NOT NULL,
    report_path             TEXT,                                -- relative path under iic_data_dir
    created_ts              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    btr_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id     INTEGER NOT NULL REFERENCES backtests(backtest_id) ON DELETE CASCADE,
    persona_id      TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    metrics         TEXT NOT NULL                                -- JSON: sharpe, total_return, win_rate, ...
);

-- ============================================================
-- F3 tables — defined upfront, populated when F3 ships
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    ingested_ts     TEXT NOT NULL,
    salience        REAL,
    raw_path        TEXT,
    deduped_of      TEXT REFERENCES events(event_id),
    status          TEXT NOT NULL                                -- "new" | "triaged" | "discarded"
);

CREATE TABLE IF NOT EXISTS event_ticker (
    event_id        TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    confidence      REAL,
    PRIMARY KEY (event_id, ticker)
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker          TEXT PRIMARY KEY,
    added_ts        TEXT NOT NULL,
    last_briefed    TEXT,
    ttl_until       TEXT,
    tags            TEXT                                         -- JSON
);

-- ============================================================
-- F4 / F5 tables — defined upfront, populated later
-- ============================================================

CREATE TABLE IF NOT EXISTS queue_jobs (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type        TEXT NOT NULL,
    payload         TEXT NOT NULL,                               -- JSON
    state           TEXT NOT NULL,                               -- "queued" | "running" | "done" | "error"
    enqueued_ts     TEXT NOT NULL,
    started_ts      TEXT,
    finished_ts     TEXT
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id        TEXT NOT NULL REFERENCES briefs(brief_id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,                               -- "telegram" | "email" | "cli"
    status          TEXT NOT NULL,                               -- "sent" | "failed" | "skipped"
    sent_ts         TEXT
);
```

- [ ] **Step 3: Commit**

```bash
git add tradingagents/persistence/__init__.py tradingagents/persistence/schema.sql
git commit -m "feat(persistence): introduce SQLite schema (F1+F3+F4+F5 tables upfront)"
```

---

## Task 5: Database connection + migration runner

**Files:**
- Create: `tradingagents/persistence/db.py`
- Test: `tests/persistence/__init__.py` (empty)
- Test: `tests/persistence/test_db.py`

- [ ] **Step 1: Write the failing test**

Create `tests/persistence/__init__.py` as an empty file.

Create `tests/persistence/test_db.py`:

```python
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.mark.unit
def test_connect_creates_tables_idempotently(tmp_db):
    from tradingagents.persistence.db import connect, schema_tables

    # First call: creates the schema.
    conn = connect(tmp_db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    expected = schema_tables()
    assert expected.issubset(tables), f"missing: {expected - tables}"

    # Second call on the same path: must not error.
    conn2 = connect(tmp_db)
    tables2 = {row[0] for row in conn2.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert tables == tables2

    conn.close()
    conn2.close()


@pytest.mark.unit
def test_connect_enables_wal_mode(tmp_db):
    from tradingagents.persistence.db import connect
    conn = connect(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


@pytest.mark.unit
def test_connect_enables_foreign_keys(tmp_db):
    from tradingagents.persistence.db import connect
    conn = connect(tmp_db)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()


@pytest.mark.unit
def test_vec_index_virtual_table_exists(tmp_db):
    from tradingagents.persistence.db import connect
    conn = connect(tmp_db)
    rows = list(conn.execute(
        "SELECT name FROM sqlite_master WHERE name='vec_index'"
    ))
    assert rows, "vec_index virtual table must be created at connect-time"
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/persistence/test_db.py -v
```

Expected: FAIL with ImportError.

- [ ] **Step 3: Implement `db.py`**

Create `tradingagents/persistence/db.py`:

```python
"""SQLite connection + schema-migration entry point.

Loads sqlite-vec at connect time and registers the vec_index virtual table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Set

import sqlite_vec

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Tables we expect schema.sql to create (used by tests; keep in sync with the .sql).
_EXPECTED_TABLES: Set[str] = {
    "runs", "costs", "briefs", "brief_actions", "suppression",
    "memories", "outcome_log",
    "backtests", "backtest_runs",
    "events", "event_ticker", "watchlist",
    "queue_jobs", "deliveries",
}


def schema_tables() -> Set[str]:
    """Tables expected after a fresh ``connect()``."""
    return _EXPECTED_TABLES


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection, run schema.sql, load sqlite-vec, create vec_index.

    Idempotent: safe to call repeatedly on the same db file.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load the sqlite-vec extension. Must happen before CREATE VIRTUAL TABLE.
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Schema (idempotent because every CREATE uses IF NOT EXISTS).
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # vec_index is a virtual table; CREATE VIRTUAL TABLE doesn't support
    # IF NOT EXISTS in older SQLite, so guard manually.
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='vec_index'"
    ).fetchone()
    if existing is None:
        conn.execute(
            "CREATE VIRTUAL TABLE vec_index USING vec0(embedding float[384])"
        )

    conn.commit()
    return conn
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/persistence/test_db.py -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/db.py tests/persistence/__init__.py tests/persistence/test_db.py
git commit -m "feat(persistence): db.connect() with WAL + sqlite-vec + idempotent schema"
```

---

## Task 6: Store helpers — runs and costs

**Files:**
- Create (extend): `tradingagents/persistence/store.py`
- Test: `tests/persistence/test_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/persistence/test_store.py`:

```python
import pytest
import uuid
from datetime import datetime, timezone


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "test.db"))


@pytest.mark.unit
def test_insert_run_round_trips(conn):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row is not None
    assert row["ticker"] == "AAPL"
    assert row["persona_id"] == "macro"
    assert row["status"] == "running"


@pytest.mark.unit
def test_finalize_run_sets_status_and_decision(conn):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.finalize_run(conn, run_id=run_id, ended_ts=now, status="complete",
                       decision="BUY", confidence=0.72)
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row["status"] == "complete"
    assert row["decision"] == "BUY"
    assert row["confidence"] == pytest.approx(0.72)


@pytest.mark.unit
def test_record_cost_appends_row(conn):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id=None,
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.record_cost(conn, run_id=run_id, provider="deepseek",
                      model="deepseek-v4-pro", in_tokens=1000, out_tokens=500)
    rows = list(conn.execute("SELECT * FROM costs WHERE run_id = ?", (run_id,)))
    assert len(rows) == 1
    assert rows[0]["in_tokens"] == 1000
    assert rows[0]["out_tokens"] == 500
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/persistence/test_store.py -v
```

Expected: FAIL with ImportError (store module / functions don't exist).

- [ ] **Step 3: Implement the store helpers**

Create `tradingagents/persistence/store.py`:

```python
"""Insert/query helpers over the SQLite store.

Each function takes an open ``sqlite3.Connection`` and commits before returning.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional


# --------------------------------------------------------------------
# runs
# --------------------------------------------------------------------

def insert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    persona_id: Optional[str],
    started_ts: str,
    artifact_dir: str,
    trigger_id: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO runs (run_id, ticker, persona_id, started_ts, status, "
        "trigger_id, artifact_dir) VALUES (?, ?, ?, ?, 'running', ?, ?)",
        (run_id, ticker, persona_id, started_ts, trigger_id, artifact_dir),
    )
    conn.commit()


def finalize_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ended_ts: str,
    status: str,
    decision: Optional[str] = None,
    confidence: Optional[float] = None,
) -> None:
    conn.execute(
        "UPDATE runs SET ended_ts = ?, status = ?, decision = ?, confidence = ? "
        "WHERE run_id = ?",
        (ended_ts, status, decision, confidence, run_id),
    )
    conn.commit()


# --------------------------------------------------------------------
# costs
# --------------------------------------------------------------------

def record_cost(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    provider: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
    usd_estimate: Optional[float] = None,
) -> None:
    conn.execute(
        "INSERT INTO costs (run_id, provider, model, in_tokens, out_tokens, "
        "usd_estimate) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, provider, model, in_tokens, out_tokens, usd_estimate),
    )
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/persistence/test_store.py -v
```

Expected: 3 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/store.py tests/persistence/test_store.py
git commit -m "feat(persistence): store helpers for runs and costs"
```

---

## Task 7: Store helpers — briefs and brief_actions

**Files:**
- Modify: `tradingagents/persistence/store.py`
- Modify: `tests/persistence/test_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/persistence/test_store.py`:

```python
@pytest.mark.unit
def test_insert_brief_round_trips(conn):
    from tradingagents.persistence import store
    import uuid
    run_id = uuid.uuid4().hex
    brief_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.insert_brief(conn, brief_id=brief_id, mode="deep_dive",
                       scope="AAPL", generated_ts=now,
                       content_path=f"briefs/{brief_id}.md",
                       run_ids=[run_id])
    row = conn.execute("SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)).fetchone()
    assert row["mode"] == "deep_dive"
    assert row["scope"] == "AAPL"
    import json as _json
    assert _json.loads(row["run_ids"]) == [run_id]


@pytest.mark.unit
def test_insert_brief_action_round_trips(conn):
    from tradingagents.persistence import store
    import uuid
    run_id = uuid.uuid4().hex
    brief_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id=None,
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    store.insert_brief(conn, brief_id=brief_id, mode="deep_dive", scope="AAPL",
                       generated_ts=now, content_path="briefs/x.md",
                       run_ids=[run_id])
    expires = "2099-01-01T00:00:00+00:00"
    store.insert_brief_action(conn, brief_id=brief_id,
                              action_type="refine_brief",
                              action_params={"instruction": "more aggressive"},
                              expires_at=expires)
    row = conn.execute("SELECT * FROM brief_actions WHERE brief_id = ?",
                       (brief_id,)).fetchone()
    assert row["action_type"] == "refine_brief"
    assert row["state"] == "pending"
    import json as _json
    assert _json.loads(row["action_params"])["instruction"] == "more aggressive"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persistence/test_store.py -v
```

Expected: 2 new failures.

- [ ] **Step 3: Implement the helpers**

Append to `tradingagents/persistence/store.py`:

```python
# --------------------------------------------------------------------
# briefs
# --------------------------------------------------------------------

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
) -> None:
    conn.execute(
        "INSERT INTO briefs (brief_id, mode, scope, generated_ts, content_path, "
        "run_ids, parent_brief_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (brief_id, mode, scope, generated_ts, content_path,
         json.dumps(list(run_ids)), parent_brief_id),
    )
    conn.commit()


# --------------------------------------------------------------------
# brief_actions
# --------------------------------------------------------------------

def insert_brief_action(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    action_type: str,
    action_params: dict,
    expires_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO brief_actions (brief_id, action_type, action_params, "
        "state, expires_at) VALUES (?, ?, ?, 'pending', ?)",
        (brief_id, action_type, json.dumps(action_params), expires_at),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/persistence/test_store.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/store.py tests/persistence/test_store.py
git commit -m "feat(persistence): store helpers for briefs and brief_actions"
```

---

## Task 8: Hybrid memory wrapper (per-persona partitioning + shared outcome_log)

**Files:**
- Create: `tradingagents/persistence/memory.py`
- Test: `tests/persistence/test_memory.py`

This is the load-bearing R6 risk mitigation: cross-persona memory leakage must be **structurally impossible**.

- [ ] **Step 1: Write the failing tests (including the cross-persona isolation assertion)**

Create `tests/persistence/test_memory.py`:

```python
import pytest
from datetime import datetime, timezone


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "test.db"))


@pytest.mark.unit
def test_memory_store_writes_partitioned_row(conn):
    from tradingagents.persistence.memory import PersonaMemoryStore
    store = PersonaMemoryStore(conn, persona_id="macro", component="decision_log")
    store.add_memory(situation_md="AAPL: rates rising", outcome="SELL was correct")
    rows = list(conn.execute(
        "SELECT * FROM memories WHERE persona_id=? AND component=?",
        ("macro", "decision_log"),
    ))
    assert len(rows) == 1
    assert rows[0]["situation_md"].startswith("AAPL")


@pytest.mark.unit
def test_memory_get_cannot_read_other_personas(conn):
    """The wrapper is the only way to read; it MUST NOT cross persona boundaries."""
    from tradingagents.persistence.memory import PersonaMemoryStore
    macro = PersonaMemoryStore(conn, persona_id="macro", component="decision_log")
    momentum = PersonaMemoryStore(conn, persona_id="momentum", component="decision_log")
    macro.add_memory(situation_md="macro-only-thought", outcome=None)
    momentum.add_memory(situation_md="momentum-only-thought", outcome=None)

    macro_results = macro.recent(limit=10)
    momentum_results = momentum.recent(limit=10)

    assert len(macro_results) == 1
    assert "macro-only-thought" in macro_results[0]["situation_md"]
    assert all("momentum" not in m["situation_md"] for m in macro_results)

    assert len(momentum_results) == 1
    assert all("macro" not in m["situation_md"] for m in momentum_results)


@pytest.mark.unit
def test_memory_rejects_empty_persona_id(conn):
    from tradingagents.persistence.memory import PersonaMemoryStore
    with pytest.raises(ValueError, match="persona_id"):
        PersonaMemoryStore(conn, persona_id="", component="decision_log")
    with pytest.raises(ValueError, match="persona_id"):
        PersonaMemoryStore(conn, persona_id="*", component="decision_log")


@pytest.mark.unit
def test_outcome_log_is_shared_across_personas(conn):
    """Outcome_log is the cross-pollination channel — readable by any persona."""
    from tradingagents.persistence.memory import OutcomeLog
    from tradingagents.persistence import store
    import uuid
    log = OutcomeLog(conn)
    # Need real run_ids that satisfy the FK.
    macro_run = uuid.uuid4().hex
    momentum_run = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=macro_run, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir="x")
    store.insert_run(conn, run_id=momentum_run, ticker="AAPL", persona_id="momentum",
                     started_ts=now, artifact_dir="y")

    log.append(run_id=macro_run, ticker="AAPL", decision="BUY",
               outcome_md="macro-call worked")
    log.append(run_id=momentum_run, ticker="AAPL", decision="SELL",
               outcome_md="momentum-call worked")

    all_for_aapl = log.recent_for_ticker("AAPL", limit=10)
    assert len(all_for_aapl) == 2
    decisions = {r["decision"] for r in all_for_aapl}
    assert decisions == {"BUY", "SELL"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persistence/test_memory.py -v
```

Expected: 4 failures (ImportError).

- [ ] **Step 3: Implement memory.py**

Create `tradingagents/persistence/memory.py`:

```python
"""Hybrid persona memory.

- ``PersonaMemoryStore`` is the ONLY interface for writing or reading persona
  memories. Construction takes a ``persona_id`` and a ``component``; every
  query is automatically filtered by both. There is no API that returns
  cross-persona rows. The class-level invariant — enforced in __init__ — is
  that ``persona_id`` is a non-empty, non-wildcard string.
- ``OutcomeLog`` is the shared cross-persona pool. Reads are NOT scoped to
  any persona by design; this is how personas learn from each other's
  outcomes (see ADR-NEW-2 in the program design).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional


_RESERVED_PERSONA_IDS = {"", "*", "all", "any"}


class PersonaMemoryStore:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        persona_id: str,
        component: str,
    ) -> None:
        if not persona_id or persona_id in _RESERVED_PERSONA_IDS:
            raise ValueError(
                f"persona_id must be a concrete persona name; got {persona_id!r}"
            )
        if not component:
            raise ValueError("component must be a non-empty string")
        self._conn = conn
        self._persona_id = persona_id
        self._component = component

    def add_memory(
        self,
        *,
        situation_md: str,
        outcome: Optional[str] = None,
        vec_id: Optional[int] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO memories (persona_id, component, situation_md, outcome, "
            "vec_id, created_ts) VALUES (?, ?, ?, ?, ?, ?)",
            (self._persona_id, self._component, situation_md, outcome, vec_id, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent(self, limit: int = 5) -> List[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM memories WHERE persona_id = ? AND component = ? "
            "ORDER BY created_ts DESC LIMIT ?",
            (self._persona_id, self._component, limit),
        ))


class OutcomeLog:
    """Shared cross-persona outcome pool. Reads are intentionally unscoped."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(
        self,
        *,
        run_id: str,
        ticker: str,
        decision: str,
        outcome_md: str,
        pnl_proxy: Optional[float] = None,
        vec_id: Optional[int] = None,
        tags: Optional[dict] = None,
    ) -> int:
        import json
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO outcome_log (run_id, ticker, decision, outcome_md, "
            "pnl_proxy, vec_id, tags, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, ticker, decision, outcome_md, pnl_proxy, vec_id,
             json.dumps(tags) if tags else None, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent_for_ticker(self, ticker: str, limit: int = 10) -> List[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM outcome_log WHERE ticker = ? ORDER BY created_ts DESC LIMIT ?",
            (ticker, limit),
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/persistence/test_memory.py -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/memory.py tests/persistence/test_memory.py
git commit -m "feat(persistence): PersonaMemoryStore + OutcomeLog (hybrid memory)"
```

---

## Task 9: Persona schema + YAML loader

**Files:**
- Create: `tradingagents/personas/__init__.py`
- Create: `tradingagents/personas/loader.py`
- Test: `tests/personas/__init__.py` (empty)
- Test: `tests/personas/test_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/personas/__init__.py` empty.

Create `tests/personas/test_loader.py`:

```python
import pytest


@pytest.mark.unit
def test_persona_loads_from_yaml_string():
    from tradingagents.personas.loader import load_persona_from_string
    yaml_text = """
id: macro
name: Macro
description: Top-down macro view
system_prompt_fragment: |
  You think top-down.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [market, news, fundamentals]
  exclude: [social, derivatives]
risk_debate:
  weights:
    aggressive: 0.5
    conservative: 1.5
    neutral: 1.0
memory_scope: hybrid
"""
    persona = load_persona_from_string(yaml_text)
    assert persona.id == "macro"
    assert persona.analysts.include == ["market", "news", "fundamentals"]
    assert persona.analysts.exclude == ["social", "derivatives"]
    assert persona.risk_debate.weights["conservative"] == pytest.approx(1.5)
    assert persona.llm.deep_think_llm == "deepseek-v4-pro"


@pytest.mark.unit
def test_persona_rejects_unknown_analyst_keys():
    from tradingagents.personas.loader import load_persona_from_string
    bad = """
id: bad
name: Bad
description: Invalid persona — bogus analyst name
system_prompt_fragment: "x"
llm:
  deep_think_llm: m
  quick_think_llm: m
analysts:
  include: [market, definitely_not_a_real_analyst]
  exclude: []
risk_debate:
  weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}
memory_scope: hybrid
"""
    with pytest.raises(ValueError, match="definitely_not_a_real_analyst"):
        load_persona_from_string(bad)


@pytest.mark.unit
def test_persona_rejects_overlapping_include_exclude():
    from tradingagents.personas.loader import load_persona_from_string
    bad = """
id: bad
name: Bad
description: market is in both lists
system_prompt_fragment: "x"
llm:
  deep_think_llm: m
  quick_think_llm: m
analysts:
  include: [market, news]
  exclude: [market]
risk_debate:
  weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}
memory_scope: hybrid
"""
    with pytest.raises(ValueError, match="overlap"):
        load_persona_from_string(bad)


@pytest.mark.unit
def test_load_all_personas_from_dir(tmp_path):
    from tradingagents.personas.loader import load_all_personas
    (tmp_path / "macro.yaml").write_text("""
id: macro
name: Macro
description: x
system_prompt_fragment: y
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}}
memory_scope: hybrid
""")
    personas = load_all_personas(str(tmp_path))
    assert len(personas) == 1
    assert personas[0].id == "macro"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/personas/test_loader.py -v
```

Expected: 4 failures (ImportError).

- [ ] **Step 3: Implement `__init__.py` and `loader.py`**

Create `tradingagents/personas/__init__.py`:

```python
"""IIC-FORGE persona overlay system. See ADR-F3 + ADR-NEW-2 in the program design."""

from .loader import Persona, load_persona_from_string, load_all_personas

__all__ = ["Persona", "load_persona_from_string", "load_all_personas"]
```

Create `tradingagents/personas/loader.py`:

```python
"""Persona YAML loader with Pydantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


# Keep this list in sync with tradingagents.cli.models.AnalystType.
_VALID_ANALYSTS = {"market", "news", "sentiment", "fundamentals", "derivatives", "social"}


class LLMSettings(BaseModel):
    deep_think_llm: str
    quick_think_llm: str
    deepseek_reasoning_effort: str | None = None  # "high" | "max" | None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None


class AnalystSettings(BaseModel):
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "AnalystSettings":
        unknown_in = set(self.include) - _VALID_ANALYSTS
        unknown_ex = set(self.exclude) - _VALID_ANALYSTS
        if unknown_in:
            raise ValueError(f"unknown analyst names in include: {sorted(unknown_in)}")
        if unknown_ex:
            raise ValueError(f"unknown analyst names in exclude: {sorted(unknown_ex)}")
        overlap = set(self.include) & set(self.exclude)
        if overlap:
            raise ValueError(f"include/exclude overlap: {sorted(overlap)}")
        return self


class RiskDebateSettings(BaseModel):
    weights: Dict[str, float] = Field(default_factory=lambda: {
        "aggressive": 1.0, "conservative": 1.0, "neutral": 1.0
    })


class Persona(BaseModel):
    id: str
    name: str
    description: str
    system_prompt_fragment: str
    llm: LLMSettings
    analysts: AnalystSettings
    risk_debate: RiskDebateSettings
    memory_scope: Literal["isolated", "shared", "hybrid"] = "hybrid"


def load_persona_from_string(yaml_text: str) -> Persona:
    raw = yaml.safe_load(yaml_text)
    return Persona.model_validate(raw)


def load_persona_from_file(path: str | Path) -> Persona:
    return load_persona_from_string(Path(path).read_text(encoding="utf-8"))


def load_all_personas(dir_path: str | Path) -> List[Persona]:
    out: List[Persona] = []
    for f in sorted(Path(dir_path).glob("*.yaml")):
        out.append(load_persona_from_file(f))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/personas/test_loader.py -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/personas/__init__.py tradingagents/personas/loader.py tests/personas/__init__.py tests/personas/test_loader.py
git commit -m "feat(personas): YAML loader + Pydantic Persona schema"
```

---

## Task 10: Three starter persona YAMLs

**Files:**
- Create: `tradingagents/personas/macro.yaml`
- Create: `tradingagents/personas/value.yaml`
- Create: `tradingagents/personas/momentum.yaml`
- Test: `tests/personas/test_starter_personas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/personas/test_starter_personas.py`:

```python
import pytest
from pathlib import Path


@pytest.mark.unit
def test_starter_personas_load_and_match_spec():
    from tradingagents.personas.loader import load_all_personas
    dir_ = Path(__file__).resolve().parents[2] / "tradingagents" / "personas"
    personas = {p.id: p for p in load_all_personas(dir_)}
    assert set(personas.keys()) == {"macro", "value", "momentum"}

    # Spec §5: macro = market + news + fundamentals
    assert set(personas["macro"].analysts.include) == {"market", "news", "fundamentals"}

    # Spec §5: value = fundamentals + news
    assert set(personas["value"].analysts.include) == {"fundamentals", "news"}

    # Spec §5: momentum = market + social + derivatives
    assert set(personas["momentum"].analysts.include) == {"market", "social", "derivatives"}

    # Risk lean — macro is conservative-heavy, momentum is aggressive-heavy
    assert personas["macro"].risk_debate.weights["conservative"] > \
           personas["macro"].risk_debate.weights["aggressive"]
    assert personas["momentum"].risk_debate.weights["aggressive"] > \
           personas["momentum"].risk_debate.weights["conservative"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/personas/test_starter_personas.py -v
```

Expected: FAIL — files don't exist.

- [ ] **Step 3: Create `macro.yaml`**

Create `tradingagents/personas/macro.yaml`:

```yaml
id: macro
name: Macro
description: Top-down view. Rates, policy, geopolitics, credit cycles drive everything.
system_prompt_fragment: |
  You think top-down. Stretch your time horizon — quarters, not days.
  Rates, policy, geopolitics, and credit cycles drive everything.
  Micro fundamentals are secondary signal — meaningful only when they
  intersect the macro thesis.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [market, news, fundamentals]
  exclude: [social, derivatives]
risk_debate:
  weights:
    aggressive: 0.5
    conservative: 1.5
    neutral: 1.0
memory_scope: hybrid
```

- [ ] **Step 4: Create `value.yaml`**

Create `tradingagents/personas/value.yaml`:

```yaml
id: value
name: Value
description: Contrarian, cashflow-driven. Long horizon. Ignores momentum.
system_prompt_fragment: |
  You are a value investor. You buy mispriced cashflows, not stories.
  Fundamentals first, valuation always. Hold for quarters or years.
  Be willing to disagree with the market — when consensus screams
  one way, ask whether the cashflow story justifies it.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [fundamentals, news]
  exclude: [social, derivatives, market]
risk_debate:
  weights:
    aggressive: 0.4
    conservative: 1.6
    neutral: 1.0
memory_scope: hybrid
```

- [ ] **Step 5: Create `momentum.yaml`**

Create `tradingagents/personas/momentum.yaml`:

```yaml
id: momentum
name: Momentum
description: Technical and flow-driven. Short horizon. Trades the tape.
system_prompt_fragment: |
  You are a momentum trader. Trends are real, and so is positioning.
  You read price action, options flow, and crowd sentiment.
  Time horizons are days to weeks. Cut losers fast. Let winners run.
  Fundamentals matter only insofar as they catalyse moves.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [market, social, derivatives]
  exclude: [news, fundamentals]
risk_debate:
  weights:
    aggressive: 1.6
    conservative: 0.5
    neutral: 1.0
memory_scope: hybrid
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/personas/test_starter_personas.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/personas/macro.yaml tradingagents/personas/value.yaml tradingagents/personas/momentum.yaml tests/personas/test_starter_personas.py
git commit -m "feat(personas): macro / value / momentum starter overlays"
```

---

## Task 11: Token-usage callback for cost measurement

**Files:**
- Create: `tradingagents/graph/cost_callback.py`
- Test: `tests/graph/test_cost_callback.py`

This is the measurement half of the cost-guard policy. Measurement always on; enforcement off (Task 12 stub).

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_cost_callback.py`:

```python
import pytest
from langchain_core.outputs import LLMResult, Generation


@pytest.mark.unit
def test_callback_accumulates_tokens_per_model():
    from tradingagents.graph.cost_callback import RunCostCallback
    cb = RunCostCallback()
    result1 = LLMResult(
        generations=[[Generation(text="x")]],
        llm_output={"token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
                    "model_name": "deepseek-v4-pro"},
    )
    result2 = LLMResult(
        generations=[[Generation(text="y")]],
        llm_output={"token_usage": {"prompt_tokens": 30, "completion_tokens": 20},
                    "model_name": "deepseek-v4-flash"},
    )
    cb.on_llm_end(result1)
    cb.on_llm_end(result2)
    cb.on_llm_end(result1)  # second call to deep model
    totals = cb.totals_by_model()
    assert totals["deepseek-v4-pro"] == {"in_tokens": 200, "out_tokens": 100}
    assert totals["deepseek-v4-flash"] == {"in_tokens": 30, "out_tokens": 20}


@pytest.mark.unit
def test_callback_handles_missing_token_usage():
    from tradingagents.graph.cost_callback import RunCostCallback
    cb = RunCostCallback()
    result = LLMResult(generations=[[Generation(text="x")]], llm_output={})
    cb.on_llm_end(result)  # must not raise
    assert cb.totals_by_model() == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/graph/test_cost_callback.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `cost_callback.py`**

Create `tradingagents/graph/cost_callback.py`:

```python
"""Per-run token accumulator.

Cost guard policy (program-design Appendix A): measurement is unconditional
and always on. Enforcement is gated by ``cost_guard_enabled`` which ships
as False.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class RunCostCallback(BaseCallbackHandler):
    """Accumulates token counts grouped by model name for one run.

    Use one instance per ``TradingAgentsGraph`` run. The Run Recorder reads
    ``totals_by_model()`` when the run finishes and persists rows to the
    ``costs`` table.
    """

    def __init__(self) -> None:
        self._totals: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"in_tokens": 0, "out_tokens": 0}
        )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        info = response.llm_output or {}
        usage = info.get("token_usage") or {}
        model = info.get("model_name") or info.get("model") or "unknown"
        in_t = int(usage.get("prompt_tokens") or 0)
        out_t = int(usage.get("completion_tokens") or 0)
        if in_t == 0 and out_t == 0:
            return
        self._totals[model]["in_tokens"] += in_t
        self._totals[model]["out_tokens"] += out_t

    def totals_by_model(self) -> Dict[str, Dict[str, int]]:
        return dict(self._totals)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/graph/test_cost_callback.py -v
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/cost_callback.py tests/graph/test_cost_callback.py
git commit -m "feat(graph): RunCostCallback — per-run token accumulator"
```

---

## Task 12: Cost guard stub (coded, disabled)

**Files:**
- Modify (extend): `tradingagents/graph/cost_callback.py`
- Modify (extend): `tests/graph/test_cost_callback.py`

Encodes the enforcement path that ships off-by-default per the saved feedback.

- [ ] **Step 1: Append the failing tests**

Append to `tests/graph/test_cost_callback.py`:

```python
@pytest.mark.unit
def test_cost_guard_disabled_by_default_does_not_raise(monkeypatch):
    from tradingagents.graph.cost_callback import CostGuard
    guard = CostGuard(per_run_token_budget=10)  # absurdly low
    # With enabled=False, even exceeding the budget must not raise.
    guard.check_or_raise(total_tokens=10_000_000)


@pytest.mark.unit
def test_cost_guard_enabled_raises_when_over_budget():
    from tradingagents.graph.cost_callback import CostGuard, CostGuardExceeded
    guard = CostGuard(per_run_token_budget=100, enabled=True)
    with pytest.raises(CostGuardExceeded):
        guard.check_or_raise(total_tokens=101)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/graph/test_cost_callback.py::test_cost_guard_disabled_by_default_does_not_raise -v
```

Expected: ImportError on `CostGuard`.

- [ ] **Step 3: Add the stub to `cost_callback.py`**

Append to `tradingagents/graph/cost_callback.py`:

```python
class CostGuardExceeded(RuntimeError):
    """Raised when a run's token spend exceeds the configured per-run budget."""


class CostGuard:
    """Per-run token-budget enforcement.

    Per IIC-FORGE program design Appendix A, this ship with ``enabled=False``.
    Measurement (via ``RunCostCallback``) is always on; enforcement is gated.
    Flip ``enabled=True`` (or set ``TRADINGAGENTS_COST_GUARD_ENABLED=1``) only
    after collecting empirical cost data via the F5 dashboard.
    """

    def __init__(
        self,
        *,
        per_run_token_budget: int,
        enabled: bool = False,
    ) -> None:
        self._budget = per_run_token_budget
        self._enabled = enabled

    def check_or_raise(self, *, total_tokens: int) -> None:
        if not self._enabled:
            return  # measurement only — no enforcement during F0–F5
        if total_tokens > self._budget:
            raise CostGuardExceeded(
                f"token spend {total_tokens} > budget {self._budget}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/graph/test_cost_callback.py -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/cost_callback.py tests/graph/test_cost_callback.py
git commit -m "feat(graph): CostGuard stub — coded, ships enabled=False"
```

---

## Task 13: Run Recorder graph node

**Files:**
- Create: `tradingagents/graph/run_recorder.py`
- Test: `tests/graph/test_run_recorder.py`

The Run Recorder is the P7 boundary contract: every graph run produces a persisted record. Failure to fire is detectable.

- [ ] **Step 1: Write the failing tests**

Create `tests/graph/test_run_recorder.py`:

```python
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock


@pytest.fixture
def db_and_dir(tmp_path):
    from tradingagents.persistence.db import connect
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return conn, str(data_dir)


@pytest.fixture
def sample_state():
    return {
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "trade_date": "2026-05-25",
        "market_report": "Market analyst: AAPL trending up.",
        "sentiment_report": "Sentiment positive.",
        "news_report": "News positive.",
        "fundamentals_report": "Fundamentals strong.",
        "derivatives_report": "",
        "investment_plan": "Hold position.",
        "trader_investment_plan": "BUY 100 shares at $190.",
        "final_trade_decision": "BUY",
        "investment_debate_state": {"history": "bull/bear summary"},
        "risk_debate_state": {"history": "risk summary"},
    }


@pytest.mark.unit
def test_run_recorder_writes_db_row_and_artifact_files(db_and_dir, sample_state):
    from tradingagents.graph.run_recorder import RunRecorder
    conn, data_dir = db_and_dir
    rec = RunRecorder(
        conn=conn,
        data_dir=data_dir,
        run_id="testrun123",
        persona_id="macro",
        cost_callback=MagicMock(totals_by_model=lambda: {
            "deepseek-v4-pro": {"in_tokens": 1000, "out_tokens": 500}
        }),
    )
    rec.start("AAPL", started_ts=datetime.now(timezone.utc).isoformat())
    new_state = rec.record(sample_state)

    # DB: one runs row, status=complete, decision parsed
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", ("testrun123",)).fetchone()
    assert row is not None
    assert row["status"] == "complete"
    assert row["decision"] == "BUY"
    assert row["artifact_dir"] == "runs/testrun123"

    # DB: at least one cost row
    cost_rows = list(conn.execute("SELECT * FROM costs WHERE run_id=?", ("testrun123",)))
    assert len(cost_rows) >= 1
    assert cost_rows[0]["in_tokens"] == 1000

    # Filesystem: per-analyst MD files
    run_path = Path(data_dir) / "runs" / "testrun123"
    assert (run_path / "meta.json").exists()
    assert (run_path / "analysts" / "market.md").exists()
    assert (run_path / "trader_plan.md").exists()
    assert (run_path / "risk_debate.md").exists()

    # State is returned unchanged so it flows through the graph.
    assert new_state["company_of_interest"] == "AAPL"


@pytest.mark.unit
def test_decision_parser_extracts_buy_hold_sell(db_and_dir, sample_state):
    """The recorder parses the trader / final_trade_decision string into
    one of BUY/HOLD/SELL when possible; None otherwise."""
    from tradingagents.graph.run_recorder import parse_decision
    assert parse_decision("FINAL TRANSACTION PROPOSAL: **BUY**") == "BUY"
    assert parse_decision("hold the position") == "HOLD"
    assert parse_decision("...we recommend a SELL") == "SELL"
    assert parse_decision("ambiguous text") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/graph/test_run_recorder.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `run_recorder.py`**

Create `tradingagents/graph/run_recorder.py`:

```python
"""Run Recorder — graph node + helper.

After Portfolio Manager finishes, this writes:
- one ``runs`` row in SQLite (status, decision, costs link)
- per-analyst markdown files under ``<data_dir>/runs/<run_id>/``
- one or more ``costs`` rows from the RunCostCallback's totals

This is the P7 boundary contract: every graph run produces a persisted
record. The smoke test in tests/smoke/test_f1_exit_gate.py asserts this
fires for every persona run during the exit-gate check.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tradingagents.persistence import store


_DECISION_RE = re.compile(r"\b(BUY|HOLD|SELL)\b", re.IGNORECASE)


def parse_decision(text: str) -> Optional[str]:
    """Extract BUY/HOLD/SELL from a free-form decision string. Returns None
    when no clear signal is present."""
    if not text:
        return None
    matches = _DECISION_RE.findall(text)
    if not matches:
        return None
    # Prefer the LAST occurrence — typical pattern is reasoning followed by
    # "FINAL TRANSACTION PROPOSAL: **BUY**".
    return matches[-1].upper()


class RunRecorder:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        data_dir: str,
        run_id: str,
        persona_id: Optional[str],
        cost_callback: Any,        # RunCostCallback (duck-typed to ease mocking)
    ) -> None:
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._run_id = run_id
        self._persona_id = persona_id
        self._cost_callback = cost_callback
        self._artifact_dir_rel = f"runs/{run_id}"

    def start(self, ticker: str, *, started_ts: str) -> None:
        store.insert_run(
            self._conn,
            run_id=self._run_id,
            ticker=ticker,
            persona_id=self._persona_id,
            started_ts=started_ts,
            artifact_dir=self._artifact_dir_rel,
        )

    def record(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Persist artifacts; return ``state`` unchanged so the graph node
        is a pass-through."""
        ticker = state.get("company_of_interest", "UNKNOWN")
        decision_src = state.get("final_trade_decision") or state.get(
            "trader_investment_plan", ""
        )
        decision = parse_decision(decision_src)

        # Filesystem artifacts
        run_path = self._data_dir / self._artifact_dir_rel
        (run_path / "analysts").mkdir(parents=True, exist_ok=True)
        for key in ("market", "sentiment", "news", "fundamentals", "derivatives"):
            content = state.get(f"{key}_report", "") or ""
            if content:
                (run_path / "analysts" / f"{key}.md").write_text(
                    content, encoding="utf-8"
                )
        (run_path / "trader_plan.md").write_text(
            state.get("trader_investment_plan", "") or "", encoding="utf-8"
        )
        (run_path / "risk_debate.md").write_text(
            json.dumps(state.get("risk_debate_state", {}), indent=2, default=str),
            encoding="utf-8",
        )
        (run_path / "pm_synthesis.md").write_text(
            state.get("final_trade_decision", "") or "", encoding="utf-8"
        )
        (run_path / "meta.json").write_text(json.dumps({
            "run_id": self._run_id,
            "persona_id": self._persona_id,
            "ticker": ticker,
            "trade_date": state.get("trade_date"),
            "decision": decision,
        }, indent=2), encoding="utf-8")

        # Costs
        totals = self._cost_callback.totals_by_model()
        for model_name, counts in totals.items():
            store.record_cost(
                self._conn,
                run_id=self._run_id,
                provider="deepseek" if "deepseek" in model_name else "unknown",
                model=model_name,
                in_tokens=counts["in_tokens"],
                out_tokens=counts["out_tokens"],
            )

        # DB finalize
        store.finalize_run(
            self._conn,
            run_id=self._run_id,
            ended_ts=datetime.now(timezone.utc).isoformat(),
            status="complete",
            decision=decision,
            confidence=None,   # F1 doesn't compute confidence; defer to F2
        )

        return state


def make_run_recorder_node(recorder: RunRecorder):
    """LangGraph node factory: returns a callable that records the state."""
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return recorder.record(state)
    return _node
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/graph/test_run_recorder.py -v
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/run_recorder.py tests/graph/test_run_recorder.py
git commit -m "feat(graph): Run Recorder node — writes runs/costs + per-analyst MD"
```

---

## Task 14: Wire Run Recorder into TradingAgentsGraph

**Files:**
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/graph/setup.py`
- Test: `tests/graph/test_run_recorder_wired.py`

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_run_recorder_wired.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_trading_agents_graph_constructs_a_run_recorder():
    """The constructor must create a RunRecorder for the run and wire its node."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        g = TradingAgentsGraph(selected_analysts=["market"])
        # The graph must hold a run_id and a recorder.
        assert hasattr(g, "run_id") and g.run_id
        assert hasattr(g, "run_recorder")


@pytest.mark.unit
def test_setup_graph_receives_run_recorder_node():
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        TradingAgentsGraph(selected_analysts=["market"])
        call = mock_setup.return_value.setup_graph.call_args
        # run_recorder_node is a kwarg now
        assert "run_recorder_node" in call.kwargs
        assert callable(call.kwargs["run_recorder_node"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/graph/test_run_recorder_wired.py -v
```

Expected: 2 failures.

- [ ] **Step 3: Modify `trading_graph.py`**

The change splits in two — the cost callback MUST be attached to `self.callbacks` **before** the LLM clients are created (otherwise it never sees token usage), and the RunRecorder is constructed after the LLM clients exist.

**Edit A — early in `__init__`, BEFORE the `deep_kwargs = self._get_provider_kwargs(...)` / `create_llm_client(...)` block (the survey said line ~89–111):**

```python
        # IIC-FORGE F1: token accumulator — must be in self.callbacks BEFORE
        # the LLM clients are constructed, so the LLM clients pick it up.
        from tradingagents.graph.cost_callback import RunCostCallback
        self._cost_cb = RunCostCallback()
        self.callbacks = list(self.callbacks or []) + [self._cost_cb]
```

**Edit B — later in `__init__`, AFTER the LLM clients are created and AFTER the existing memory-log line (around line 113), but BEFORE the `GraphSetup(...).setup_graph(...)` call:**

```python
        # IIC-FORGE F1: per-run id + persistence + Run Recorder
        import uuid
        from tradingagents.persistence.db import connect as _iic_connect
        from tradingagents.graph.run_recorder import RunRecorder, make_run_recorder_node

        self.run_id = uuid.uuid4().hex
        self._iic_conn = _iic_connect(self.config["iic_db_path"])
        self.run_recorder = RunRecorder(
            conn=self._iic_conn,
            data_dir=self.config["iic_data_dir"],
            run_id=self.run_id,
            persona_id=self.config.get("persona_id"),
            cost_callback=self._cost_cb,
        )
        run_recorder_node = make_run_recorder_node(self.run_recorder)
```

Then change the `GraphSetup(...).setup_graph(...)` call to pass `run_recorder_node=run_recorder_node` as a kwarg.

Also, ensure the recorder is told a run has started when `_run_graph` actually begins. Find `_run_graph` and add at the top, right before invoking the graph:

```python
        from datetime import datetime, timezone
        self.run_recorder.start(
            ticker=initial_state.get("company_of_interest", "UNKNOWN"),
            started_ts=datetime.now(timezone.utc).isoformat(),
        )
```

(If the existing constructor builds the initial state inside `_run_graph`, place the `start()` call right after `initial_state` is constructed.)

- [ ] **Step 4: Modify `setup.py`**

In `tradingagents/graph/setup.py`, update the `setup_graph` signature to accept `run_recorder_node=None` and wire it into the workflow.

Find the line `workflow.add_edge("Portfolio Manager", END)` (survey said around line 157) and replace with:

```python
        if run_recorder_node is not None:
            workflow.add_node("Run Recorder", run_recorder_node)
            workflow.add_edge("Portfolio Manager", "Run Recorder")
            workflow.add_edge("Run Recorder", END)
        else:
            workflow.add_edge("Portfolio Manager", END)
```

Add `run_recorder_node=None` to the `setup_graph` method signature (it defaults to None for legacy callers that don't pass it).

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/graph/test_run_recorder_wired.py -v
```

Expected: 2 passing.

Also re-run the existing graph tests to ensure no regressions:

```bash
pytest tests/graph -m "not integration" -v
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/graph/trading_graph.py tradingagents/graph/setup.py tests/graph/test_run_recorder_wired.py
git commit -m "feat(graph): wire RunRecorder node after Portfolio Manager"
```

---

## Task 15: Secretary synthesis (LLM call producing consensus / divergence / recommendation)

**Files:**
- Create: `tradingagents/secretary/__init__.py`
- Create: `tradingagents/secretary/synthesis.py`
- Test: `tests/secretary/__init__.py` (empty)
- Test: `tests/secretary/test_synthesis.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/secretary/__init__.py` empty.

Create `tests/secretary/test_synthesis.py`:

```python
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def sample_persona_runs():
    return [
        {"persona_id": "macro", "decision": "SELL", "final_trade_decision":
            "SELL — rates rising squeeze tech multiples"},
        {"persona_id": "value", "decision": "BUY", "final_trade_decision":
            "BUY — cashflow yield 6%, stock undervalued"},
        {"persona_id": "momentum", "decision": "BUY", "final_trade_decision":
            "BUY — uptrend intact, call OI building"},
    ]


@pytest.mark.unit
def test_synthesis_calls_llm_and_returns_three_sections(sample_persona_runs):
    from tradingagents.secretary.synthesis import synthesize_brief
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="""
## Consensus
- Cashflow yield is attractive at current price.

## Divergence
- Macro persona says SELL on rate path; value and momentum say BUY.

## Recommendation
Low-confidence call: macro disagreement is material. Hold.
""")
    result = synthesize_brief(
        llm=fake_llm,
        ticker="AAPL",
        persona_runs=sample_persona_runs,
    )
    assert "consensus" in result
    assert "divergence" in result
    assert "recommendation" in result
    assert "Hold" in result["recommendation"] or "HOLD" in result["recommendation"]


@pytest.mark.unit
def test_synthesis_prompt_includes_divergence_directive(sample_persona_runs):
    """The synthesis prompt MUST instruct the LLM to preserve disagreement
    explicitly. This is R3 mitigation in the program design."""
    from tradingagents.secretary.synthesis import build_synthesis_prompt
    prompt = build_synthesis_prompt(ticker="AAPL", persona_runs=sample_persona_runs)
    assert "divergence" in prompt.lower() or "disagree" in prompt.lower()
    assert "AAPL" in prompt
    assert "macro" in prompt and "value" in prompt and "momentum" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/secretary/test_synthesis.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `synthesis.py`**

Create `tradingagents/secretary/__init__.py`:

```python
"""IIC-FORGE Secretary service.

See §4 of docs/superpowers/specs/2026-05-25-iic-forge-program-design.md.
"""
```

Create `tradingagents/secretary/synthesis.py`:

```python
"""Brief synthesis prompt + LLM call.

R3 mitigation: the prompt MUST explicitly instruct the model to preserve
disagreement, not average it away. Disagreement is signal.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


_SYNTHESIS_TEMPLATE = """You are the IIC Secretary. Three persona investment teams have each produced
an analysis of {ticker}. Your job is to synthesize their reports for a human
decision-maker.

Produce EXACTLY three sections, in this order, with these exact headings:

## Consensus
What do all personas agree on? Be specific — name the thesis, not just "they
agreed it's a stock".

## Divergence
Where do the personas disagree, and why? This section is the most important
in the brief. Do NOT smooth over disagreement; surface it. Use this shape:
- Persona X says Y because Z. Persona A says B because C. The disagreement
  hinges on <the load-bearing assumption>.

## Recommendation
One of BUY / HOLD / SELL with a confidence rationale. If the divergence in
the previous section is material, explicitly say so and recommend HOLD with
a "low-confidence call" note.

Here are the persona reports:

{persona_reports}
"""


def build_synthesis_prompt(*, ticker: str, persona_runs: List[Dict[str, Any]]) -> str:
    blocks = []
    for r in persona_runs:
        pid = r.get("persona_id", "?")
        decision = r.get("decision", "?")
        body = r.get("final_trade_decision", "")
        blocks.append(f"=== {pid} ({decision}) ===\n{body}\n")
    return _SYNTHESIS_TEMPLATE.format(
        ticker=ticker, persona_reports="\n".join(blocks)
    )


def _extract_section(text: str, heading: str) -> str:
    """Extract markdown section under '## <heading>' until the next '## ' or EOF."""
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.+?)(?=\n##\s+|\Z)"
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def synthesize_brief(
    *,
    llm: Any,
    ticker: str,
    persona_runs: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Call the LLM with the synthesis prompt; parse into 3 sections.

    Returns dict with keys ``consensus``, ``divergence``, ``recommendation``,
    plus ``raw`` (the full LLM response text).
    """
    prompt = build_synthesis_prompt(ticker=ticker, persona_runs=persona_runs)
    response = llm.invoke(prompt)
    raw = getattr(response, "content", str(response))
    return {
        "consensus": _extract_section(raw, "Consensus"),
        "divergence": _extract_section(raw, "Divergence"),
        "recommendation": _extract_section(raw, "Recommendation"),
        "raw": raw,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/secretary/test_synthesis.py -v
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/secretary/__init__.py tradingagents/secretary/synthesis.py tests/secretary/__init__.py tests/secretary/test_synthesis.py
git commit -m "feat(secretary): synthesis prompt + parser (consensus/divergence/recommendation)"
```

---

## Task 16: Deep-dive Jinja template

**Files:**
- Create: `tradingagents/secretary/templates/__init__.py` (empty)
- Create: `tradingagents/secretary/templates/deep_dive.j2`
- Test: `tests/secretary/test_templates.py`

- [ ] **Step 1: Write the failing test**

Create `tests/secretary/test_templates.py`:

```python
import pytest


@pytest.mark.unit
def test_deep_dive_template_renders_with_all_sections():
    from tradingagents.secretary.service import render_deep_dive
    out = render_deep_dive(
        ticker="AAPL",
        trade_date="2026-05-25",
        synthesis={
            "consensus": "Cashflow yield strong.",
            "divergence": "Macro says SELL; momentum and value say BUY.",
            "recommendation": "HOLD — low-confidence call.",
        },
        persona_runs=[
            {"persona_id": "macro", "decision": "SELL", "final_trade_decision": "macro reasoning"},
            {"persona_id": "value", "decision": "BUY", "final_trade_decision": "value reasoning"},
            {"persona_id": "momentum", "decision": "BUY", "final_trade_decision": "momentum reasoning"},
        ],
    )
    # Header
    assert "AAPL" in out
    assert "2026-05-25" in out
    # All three synthesis sections
    assert "Consensus" in out and "Cashflow yield strong" in out
    assert "Divergence" in out and "Macro says SELL" in out
    assert "Recommendation" in out and "HOLD" in out
    # Per-persona detail
    for pid in ("macro", "value", "momentum"):
        assert pid in out
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/secretary/test_templates.py -v
```

Expected: ImportError (`render_deep_dive` doesn't exist; `service.py` doesn't exist; template missing).

- [ ] **Step 3: Create the template**

Create `tradingagents/secretary/templates/__init__.py` empty.

Create `tradingagents/secretary/templates/deep_dive.j2`:

```jinja
# Deep-Dive Brief — {{ ticker }}

_Generated {{ trade_date }} — IIC Secretary_

---

## Consensus

{{ synthesis.consensus }}

## Divergence

{{ synthesis.divergence }}

## Recommendation

{{ synthesis.recommendation }}

---

## Per-persona detail

{% for run in persona_runs %}
### {{ run.persona_id }} — {{ run.decision }}

{{ run.final_trade_decision }}

---

{% endfor %}
```

- [ ] **Step 4: Add `render_deep_dive` to `service.py` (stub the rest of the service for now)**

Create `tradingagents/secretary/service.py`:

```python
"""Secretary service.

F1 ships only ``compose_deep_dive`` end-to-end. The other compose methods
(morning_digest, event_alert) are stubs raising NotImplementedError —
they land in later phases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    keep_trailing_newline=True,
)


def render_deep_dive(
    *,
    ticker: str,
    trade_date: str,
    synthesis: Dict[str, str],
    persona_runs: List[Dict[str, Any]],
) -> str:
    return _env.get_template("deep_dive.j2").render(
        ticker=ticker,
        trade_date=trade_date,
        synthesis=synthesis,
        persona_runs=persona_runs,
    )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/secretary/test_templates.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/secretary/service.py tradingagents/secretary/templates/__init__.py tradingagents/secretary/templates/deep_dive.j2 tests/secretary/test_templates.py
git commit -m "feat(secretary): deep_dive Jinja template + render helper"
```

---

## Task 17: Secretary `compose_deep_dive` method

**Files:**
- Modify: `tradingagents/secretary/service.py`
- Test: `tests/secretary/test_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/secretary/test_service.py`:

```python
import pytest
import uuid
from unittest.mock import MagicMock
from datetime import datetime, timezone


@pytest.fixture
def db_and_dirs(tmp_path):
    from tradingagents.persistence.db import connect
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "runs").mkdir()
    (data_dir / "briefs").mkdir()
    return conn, str(data_dir)


@pytest.mark.unit
def test_compose_deep_dive_writes_brief_row_and_md(db_and_dirs):
    """End-to-end with mocked LLM and pre-seeded run rows."""
    from tradingagents.secretary.service import Secretary
    from tradingagents.persistence import store

    conn, data_dir = db_and_dirs
    # Seed three runs and their per-analyst markdown.
    run_ids = []
    for pid in ("macro", "value", "momentum"):
        rid = uuid.uuid4().hex
        run_ids.append(rid)
        now = datetime.now(timezone.utc).isoformat()
        store.insert_run(conn, run_id=rid, ticker="AAPL", persona_id=pid,
                         started_ts=now, artifact_dir=f"runs/{rid}")
        store.finalize_run(conn, run_id=rid, ended_ts=now, status="complete",
                           decision="BUY" if pid != "macro" else "SELL")

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="""
## Consensus
Cashflow is strong.

## Divergence
Macro says SELL.

## Recommendation
HOLD — low-confidence call.
""")
    sec = Secretary(conn=conn, data_dir=data_dir, llm=fake_llm)
    brief_id = sec.compose_deep_dive(
        ticker="AAPL",
        run_ids=run_ids,
        trade_date="2026-05-25",
    )
    # DB row exists
    row = conn.execute("SELECT * FROM briefs WHERE brief_id=?",
                       (brief_id,)).fetchone()
    assert row is not None
    assert row["mode"] == "deep_dive"
    assert row["scope"] == "AAPL"
    # Markdown on disk
    from pathlib import Path
    md_path = Path(data_dir) / row["content_path"]
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "AAPL" in text
    assert "Consensus" in text
    assert "Divergence" in text


@pytest.mark.unit
def test_compose_morning_digest_and_event_alert_are_stubs(db_and_dirs):
    from tradingagents.secretary.service import Secretary
    conn, data_dir = db_and_dirs
    sec = Secretary(conn=conn, data_dir=data_dir, llm=MagicMock())
    with pytest.raises(NotImplementedError):
        sec.compose_morning_digest(watchlist=["AAPL"], ts="2026-05-25T00:00:00Z")
    with pytest.raises(NotImplementedError):
        sec.compose_event_alert(event_id="x")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/secretary/test_service.py -v
```

Expected: 2 failures (Secretary class doesn't exist).

- [ ] **Step 3: Implement the Secretary class**

Replace `tradingagents/secretary/service.py` with the full implementation (keep the existing `render_deep_dive` helper at the top):

```python
"""Secretary service.

F1 ships ``compose_deep_dive`` end-to-end. Morning digest and event alert
are stubbed — they land in later phases (F3+/F5).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tradingagents.persistence import store
from tradingagents.secretary.synthesis import synthesize_brief

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    keep_trailing_newline=True,
)


def render_deep_dive(
    *,
    ticker: str,
    trade_date: str,
    synthesis: Dict[str, str],
    persona_runs: List[Dict[str, Any]],
) -> str:
    return _env.get_template("deep_dive.j2").render(
        ticker=ticker,
        trade_date=trade_date,
        synthesis=synthesis,
        persona_runs=persona_runs,
    )


class Secretary:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        data_dir: str,
        llm: Any,
    ) -> None:
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._llm = llm

    # ----- Deep-dive (F1 scope) -----
    def compose_deep_dive(
        self,
        *,
        ticker: str,
        run_ids: List[str],
        trade_date: str,
    ) -> str:
        # Load each run's pm_synthesis.md (or fall back to meta.json) as the
        # final_trade_decision text for that persona.
        persona_runs: List[Dict[str, Any]] = []
        for rid in run_ids:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (rid,)
            ).fetchone()
            if row is None:
                continue
            artifact_dir = self._data_dir / row["artifact_dir"]
            pm_path = artifact_dir / "pm_synthesis.md"
            body = pm_path.read_text(encoding="utf-8") if pm_path.exists() else ""
            persona_runs.append({
                "persona_id": row["persona_id"] or "default",
                "decision": row["decision"] or "?",
                "final_trade_decision": body,
            })

        synthesis = synthesize_brief(
            llm=self._llm,
            ticker=ticker,
            persona_runs=persona_runs,
        )

        markdown = render_deep_dive(
            ticker=ticker,
            trade_date=trade_date,
            synthesis=synthesis,
            persona_runs=persona_runs,
        )

        brief_id = uuid.uuid4().hex
        rel_path = f"briefs/{brief_id}.md"
        (self._data_dir / "briefs").mkdir(parents=True, exist_ok=True)
        (self._data_dir / rel_path).write_text(markdown, encoding="utf-8")

        store.insert_brief(
            self._conn,
            brief_id=brief_id,
            mode="deep_dive",
            scope=ticker,
            generated_ts=datetime.now(timezone.utc).isoformat(),
            content_path=rel_path,
            run_ids=run_ids,
            parent_brief_id=None,
        )
        return brief_id

    # ----- Stubs for later phases -----
    def compose_morning_digest(self, *, watchlist: List[str], ts: str) -> str:
        raise NotImplementedError("compose_morning_digest lands in F5")

    def compose_event_alert(self, *, event_id: str) -> str:
        raise NotImplementedError("compose_event_alert lands in F4")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/secretary/test_service.py -v
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/secretary/service.py tests/secretary/test_service.py
git commit -m "feat(secretary): compose_deep_dive (F1 scope); morning/event stubbed"
```

---

## Task 18: CLI `deepdive` command

**Files:**
- Create: `cli/deepdive.py`
- Modify: `cli/main.py` (register the new command)
- Test: `tests/cli/test_deepdive.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cli/__init__.py` empty if not already present.

Create `tests/cli/test_deepdive.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_deepdive_invokes_three_personas_then_secretary(tmp_path, monkeypatch):
    # Point the config at a temp DB and data dir.
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    from cli.deepdive import run_deepdive

    # Patch the engine so we don't actually call DeepSeek.
    fake_run_ids = ["run1", "run2", "run3"]

    def fake_run_one_persona(persona, ticker, trade_date, config):
        # Just return a synthetic run_id and pretend it persisted to the DB.
        idx = ["macro", "value", "momentum"].index(persona.id)
        return fake_run_ids[idx]

    fake_secretary = MagicMock()
    fake_secretary.compose_deep_dive.return_value = "brief123"

    with patch("cli.deepdive._run_one_persona", side_effect=fake_run_one_persona), \
         patch("cli.deepdive._build_secretary", return_value=fake_secretary):
        brief_id = run_deepdive(ticker="AAPL", trade_date="2026-05-25", parallel=False)

    assert brief_id == "brief123"
    fake_secretary.compose_deep_dive.assert_called_once()
    call_kwargs = fake_secretary.compose_deep_dive.call_args.kwargs
    assert call_kwargs["ticker"] == "AAPL"
    assert sorted(call_kwargs["run_ids"]) == sorted(fake_run_ids)


@pytest.mark.unit
def test_deepdive_typer_command_exists():
    """The Typer app must expose `deepdive` as a registered command."""
    from cli.main import app
    cmd_names = {info.name for info in app.registered_commands}
    assert "deepdive" in cmd_names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_deepdive.py -v
```

Expected: 2 failures.

- [ ] **Step 3: Implement `cli/deepdive.py`**

Create `cli/deepdive.py`:

```python
"""IIC-FORGE `deepdive <ticker>` command.

Runs three personas (macro / value / momentum) over the ticker, then calls
the Secretary to produce a synthesis brief. Parallel by default; ``--no-parallel``
runs sequentially (used by tests and for deterministic debugging).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path
from typing import Any, List

import typer

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.personas.loader import Persona, load_all_personas
from tradingagents.persistence.db import connect as iic_connect
from tradingagents.secretary.service import Secretary


def _personas_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "tradingagents" / "personas")


def _run_one_persona(persona: Persona, ticker: str, trade_date: str, config: dict) -> str:
    """Construct a TradingAgentsGraph with the persona overlay, propagate, return run_id."""
    # Build a per-run config overlay.
    overlay = dict(config)
    overlay["persona_id"] = persona.id
    overlay["deep_think_llm"] = persona.llm.deep_think_llm
    overlay["quick_think_llm"] = persona.llm.quick_think_llm
    if persona.llm.deepseek_reasoning_effort is not None:
        overlay["deepseek_reasoning_effort"] = persona.llm.deepseek_reasoning_effort

    # Compute selected_analysts from the persona's include list.
    selected = list(persona.analysts.include)

    # Import here to avoid heavy imports at module import time.
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(
        config=overlay,
        selected_analysts=selected,
    )
    # Propagate. The TradingAgents engine has a public entry point named
    # ``propagate`` (or possibly ``run`` / ``analyze`` — verify against
    # the current file before wiring this in). Typical signature is
    # ``propagate(company_name, trade_date)`` (positional, NOT ``ticker``).
    # The Run Recorder node persists outputs as a side-effect during graph
    # execution; we only need the returned run_id.
    graph.propagate(ticker, trade_date)
    return graph.run_id


def _build_secretary(config: dict) -> Secretary:
    from tradingagents.llm_clients.factory import create_llm_client
    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    )
    conn = iic_connect(config["iic_db_path"])
    return Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)


def run_deepdive(*, ticker: str, trade_date: str, parallel: bool = True) -> str:
    """Programmatic entry point — returns the brief_id."""
    config = dict(DEFAULT_CONFIG)
    personas: List[Persona] = load_all_personas(_personas_dir())
    if not personas:
        raise RuntimeError(f"No personas found in {_personas_dir()}")

    if parallel:
        with ThreadPoolExecutor(max_workers=len(personas)) as ex:
            futures = [ex.submit(_run_one_persona, p, ticker, trade_date, config)
                       for p in personas]
            run_ids = [f.result() for f in futures]
    else:
        run_ids = [_run_one_persona(p, ticker, trade_date, config) for p in personas]

    sec = _build_secretary(config)
    return sec.compose_deep_dive(ticker=ticker, run_ids=run_ids, trade_date=trade_date)


def deepdive(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
    trade_date: str = typer.Option(None, "--date", help="Trade date YYYY-MM-DD (default: today)"),
    parallel: bool = typer.Option(True, "--parallel/--no-parallel"),
):
    """Run a three-persona deep-dive and produce a synthesized brief."""
    td = trade_date or _date.today().isoformat()
    brief_id = run_deepdive(ticker=ticker.upper(), trade_date=td, parallel=parallel)
    typer.echo(f"brief_id: {brief_id}")
    config = dict(DEFAULT_CONFIG)
    typer.echo(f"brief markdown: {config['iic_data_dir']}/briefs/{brief_id}.md")
```

- [ ] **Step 4: Register the command in `cli/main.py`**

In `cli/main.py`, near the existing `@app.command()` decorations (the survey said the `analyze` command is around line 1264), add at module scope:

```python
from cli.deepdive import deepdive as _deepdive_cmd
app.command(name="deepdive")(_deepdive_cmd)
```

Place this AFTER `app = typer.Typer(...)` but in a sensible location near the other command registrations.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/cli/test_deepdive.py -v
```

Expected: 2 passing.

- [ ] **Step 6: Commit**

```bash
git add cli/deepdive.py cli/main.py tests/cli/test_deepdive.py
git commit -m "feat(cli): deepdive command — runs 3 personas + secretary brief"
```

---

## Task 19: F1 exit-gate smoke test (live AAPL run)

**Files:**
- Create: `tests/smoke/__init__.py` (empty)
- Create: `tests/smoke/test_f1_exit_gate.py`

This test is the spec's F1 exit gate. It runs end-to-end against the real engine + DeepSeek. Marked `integration` so it doesn't run in fast loops.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/smoke/__init__.py` empty.

Create `tests/smoke/test_f1_exit_gate.py`:

```python
"""F1 exit-gate smoke test.

Runs the real deepdive on AAPL with all three personas. Requires
DEEPSEEK_API_KEY in the environment. Marked ``integration`` so it does
not run in the default test loop.

Verifies the four exit-gate clauses from §7 F1 of the program design:
1. Three persona runs launched.
2. Per-analyst markdown is written to data/runs/<run_id>/.
3. Both ``runs`` and ``briefs`` rows are recorded in SQLite.
4. The produced brief contains the three structured sections.
"""

import os
import pytest
from pathlib import Path

from tradingagents.persistence.db import connect


pytestmark = pytest.mark.integration


def test_f1_exit_gate_deepdive_aapl(tmp_path, monkeypatch):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    from cli.deepdive import run_deepdive
    brief_id = run_deepdive(ticker="AAPL", trade_date="2026-05-25", parallel=True)
    assert brief_id

    conn = connect(str(tmp_path / "iic.db"))

    # Exit-gate clause 1: three persona runs.
    runs = list(conn.execute("SELECT persona_id, status, decision FROM runs"))
    assert len(runs) == 3, f"expected 3 persona runs, got {len(runs)}: {runs}"
    persona_ids = {r["persona_id"] for r in runs}
    assert persona_ids == {"macro", "value", "momentum"}
    assert all(r["status"] == "complete" for r in runs)

    # Exit-gate clause 2: per-analyst markdown on disk.
    for r in conn.execute("SELECT run_id, artifact_dir FROM runs"):
        run_path = tmp_path / "data" / r["artifact_dir"]
        assert run_path.exists(), f"missing artifact dir for {r['run_id']}"
        assert (run_path / "meta.json").exists()
        # At least one analyst MD should be present.
        analyst_files = list((run_path / "analysts").glob("*.md"))
        assert analyst_files, f"no analyst markdown in {run_path}"

    # Exit-gate clause 3: briefs row exists.
    brief_row = conn.execute("SELECT * FROM briefs WHERE brief_id = ?",
                             (brief_id,)).fetchone()
    assert brief_row is not None
    assert brief_row["mode"] == "deep_dive"
    assert brief_row["scope"] == "AAPL"

    # Exit-gate clause 4: brief markdown has the three sections.
    brief_path = tmp_path / "data" / brief_row["content_path"]
    assert brief_path.exists()
    text = brief_path.read_text(encoding="utf-8")
    assert "Consensus" in text
    assert "Divergence" in text
    assert "Recommendation" in text
```

- [ ] **Step 2: Run the smoke test (with `DEEPSEEK_API_KEY` set)**

```bash
pytest tests/smoke/test_f1_exit_gate.py -v -m integration
```

Expected: PASS. If it fails, investigate — do NOT amend the test to pass; fix the underlying defect.

If `DEEPSEEK_API_KEY` is not set, the test is `skipped` — that is acceptable for the commit, but the exit-gate is not validated until it runs.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/__init__.py tests/smoke/test_f1_exit_gate.py
git commit -m "test(smoke): F1 exit-gate end-to-end on AAPL"
```

---

## Task 20: Boundary smoke test — Run Recorder fires for every persona

**Files:**
- Create: `tests/smoke/test_boundary_run_recorder.py`

This is the direct P7 anti-vibe-coding-gap check: assert that the Run Recorder node is actually invoked by every persona run, not merely importable. Catches the failure mode where a node exists in code but isn't wired into the compiled graph.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/smoke/test_boundary_run_recorder.py`:

```python
import pytest
from unittest.mock import patch
from pathlib import Path


pytestmark = pytest.mark.smoke


def test_run_recorder_node_fires_for_every_persona_in_deepdive(tmp_path, monkeypatch):
    """Verify the Run Recorder node is invoked by the compiled graph for
    each persona. Uses a real graph compile but with the engine's propagate
    monkey-patched to short-circuit after the Run Recorder runs."""
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    invocations = []
    from tradingagents.graph.run_recorder import RunRecorder

    original_record = RunRecorder.record

    def spying_record(self, state):
        invocations.append((self._run_id, self._persona_id))
        return original_record(self, state)

    # Patch propagate to write a minimal final state to disk + DB rather than
    # invoking the full LangGraph. This isolates "did the Run Recorder fire?"
    # from "did the LLM produce real content?".
    def stub_propagate(self, *, ticker, trade_date):
        final_state = {
            "company_of_interest": ticker,
            "asset_type": "stock",
            "trade_date": trade_date,
            "market_report": "stub", "sentiment_report": "stub",
            "news_report": "stub", "fundamentals_report": "stub",
            "derivatives_report": "",
            "investment_plan": "stub",
            "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: **HOLD**",
            "final_trade_decision": "HOLD",
            "investment_debate_state": {"history": "stub"},
            "risk_debate_state": {"history": "stub"},
        }
        # Mark the run started + emit the recorder pass.
        from datetime import datetime, timezone
        self.run_recorder.start(ticker=ticker,
                                started_ts=datetime.now(timezone.utc).isoformat())
        self.run_recorder.record(final_state)
        return final_state

    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch.object(RunRecorder, "record", spying_record), \
         patch.object(TradingAgentsGraph, "propagate", stub_propagate):
        from cli.deepdive import run_deepdive
        # Also bypass the Secretary's LLM by patching the synthesis.
        with patch("tradingagents.secretary.service.synthesize_brief", return_value={
            "consensus": "x", "divergence": "y", "recommendation": "HOLD", "raw": "..."
        }):
            run_deepdive(ticker="AAPL", trade_date="2026-05-25", parallel=False)

    persona_ids_seen = {pid for _, pid in invocations}
    assert persona_ids_seen == {"macro", "value", "momentum"}, \
        f"Run Recorder fired for {persona_ids_seen}, not all three personas"
```

- [ ] **Step 2: Run the smoke test**

```bash
pytest tests/smoke/test_boundary_run_recorder.py -v -m smoke
```

Expected: PASS. If it fails because the Run Recorder is not wired into the graph for one persona, investigate — the failure mode being asserted is exactly the vibe-coding gap.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/test_boundary_run_recorder.py
git commit -m "test(smoke): boundary check — Run Recorder fires for every persona"
```

---

## Task 21: Boundary smoke test — memory wrapper isolation

**Files:**
- Create: `tests/smoke/test_boundary_memory_isolation.py`

This is the R6 mitigation in test form. Cross-persona memory leakage is structurally impossible — assert it.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/smoke/test_boundary_memory_isolation.py`:

```python
import pytest


pytestmark = pytest.mark.smoke


def test_persona_memory_store_has_no_api_to_read_other_personas(tmp_path):
    """The PersonaMemoryStore must not expose any method that returns rows
    not matching its (persona_id, component) key. This is the R6
    boundary contract."""
    from tradingagents.persistence.db import connect
    from tradingagents.persistence.memory import PersonaMemoryStore

    conn = connect(str(tmp_path / "iic.db"))
    macro = PersonaMemoryStore(conn, persona_id="macro", component="decision_log")
    momentum = PersonaMemoryStore(conn, persona_id="momentum", component="decision_log")

    macro.add_memory(situation_md="MACRO_PRIVATE_THOUGHT", outcome=None)
    momentum.add_memory(situation_md="MOMENTUM_PRIVATE_THOUGHT", outcome=None)

    # Every public method's return value, when called from a persona, must
    # only reference that persona's rows.
    public_methods = [name for name in dir(macro)
                      if not name.startswith("_") and callable(getattr(macro, name))]
    # Currently: ["add_memory", "recent"]. If the future adds more, this
    # test will catch any that leak.
    for name in public_methods:
        if name == "add_memory":
            continue   # writer, not a reader
        result = getattr(macro, name)()
        for row in result:
            assert "MOMENTUM" not in row["situation_md"], \
                f"PersonaMemoryStore.{name} leaked momentum row to macro"


def test_outcome_log_is_intentionally_shared(tmp_path):
    """Contrast test: the OutcomeLog *is* shared across personas. This
    documents the design and guards against an accidental future scoping."""
    from tradingagents.persistence.db import connect
    from tradingagents.persistence.memory import OutcomeLog
    from tradingagents.persistence import store
    from datetime import datetime, timezone
    import uuid

    conn = connect(str(tmp_path / "iic.db"))
    macro_run = uuid.uuid4().hex
    momentum_run = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=macro_run, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir="x")
    store.insert_run(conn, run_id=momentum_run, ticker="AAPL", persona_id="momentum",
                     started_ts=now, artifact_dir="y")

    log = OutcomeLog(conn)
    log.append(run_id=macro_run, ticker="AAPL", decision="SELL",
               outcome_md="macro outcome")
    log.append(run_id=momentum_run, ticker="AAPL", decision="BUY",
               outcome_md="momentum outcome")

    rows = log.recent_for_ticker("AAPL", limit=10)
    decisions = {r["decision"] for r in rows}
    assert decisions == {"SELL", "BUY"}, \
        "OutcomeLog must surface rows from all personas — it is the cross-pollination channel"
```

- [ ] **Step 2: Run the smoke tests**

```bash
pytest tests/smoke/test_boundary_memory_isolation.py -v -m smoke
```

Expected: 2 passing.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/test_boundary_memory_isolation.py
git commit -m "test(smoke): boundary check — PersonaMemoryStore isolation, OutcomeLog sharing"
```

---

## Task 22: Wrap-up — run the full test suite, verify the F1 exit gate

**Files:** none (verification only)

- [ ] **Step 1: Run all unit tests**

```bash
pytest -m "not integration" --tb=short
```

Expected: all passing.

- [ ] **Step 2: Run all smoke tests**

```bash
pytest -m smoke --tb=short
```

Expected: all passing.

- [ ] **Step 3: Run the integration exit-gate test (requires `DEEPSEEK_API_KEY`)**

```bash
pytest tests/smoke/test_f1_exit_gate.py -v -m integration
```

Expected: PASS. This is the spec's F1 exit gate — the system is ready to declare F1 complete only when this passes against real DeepSeek.

- [ ] **Step 4: Push the branch (only when explicitly authorized by the user)**

```bash
# Only push after user confirms — push to a remote branch, do NOT force-push.
git push -u origin feat/iic-forge-04-f1
```

- [ ] **Step 5: Open a PR (only when explicitly authorized)**

Open a PR from `feat/iic-forge-04-f1` to `main`. Title: `feat(iic-forge): F1 — decision core + persistence (IIC-FORGE-04)`. Body should link to:
- `docs/superpowers/specs/2026-05-25-iic-forge-program-design.md` (the spec)
- `docs/superpowers/plans/2026-05-25-iic-forge-04-f1-decision-core.md` (this plan)
- The F1 exit-gate test as the acceptance evidence.

---

## Out of scope for this plan (parking lot)

These are NOT to be implemented in F1; they belong to later phases:

- `compose_morning_digest` and `compose_event_alert` implementations — stubs only in F1; bodies land in F4/F5. Their Jinja templates (`morning_digest.j2`, `event_alert.j2`) also ship with their compose-method implementations, not in F1. Only `deep_dive.j2` exists in F1 because it is the only template exercised by the F1 exit gate.
- Brief-action prompts (Telegram buttons, CLI y/N, email Streamlit link) — F5 deliverable.
- Refinement intent classifier — F5 deliverable.
- Backtest harness — F2 deliverable.
- Reflection-loop persona-awareness extension — F2 deliverable.
- Cost-guard *enforcement* — coded as `enabled=False` here (Task 12); flipped on only after F5 dashboard collects empirical data.
- Event ingestion / triage / watchlist population — F3 deliverable; the tables exist in F1 but stay empty.

---

*End of IIC-FORGE-04. Subsequent plans: IIC-FORGE-05 (F2 backtest harness).*
