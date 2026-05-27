# IIC-FORGE-06 — F3 Always-on Sensing + Triage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship F3 of the IIC-FORGE program — a continuous ingestion service that pulls from six external sources, deduplicates and scores every incoming item with a context-aware salience LLM call, and maintains a user-curated + auto-promoted watchlist. All artifacts land in F1's SQLite store; the only schema changes are four append-only tables plus a comment-only enum extension on `events.status`.

**Architecture:** Six adapter processes (one systemd unit each, defensively retry-internal) `XADD` envelopes to a Redis stream `ingest:raw`. A single triage process runs N async consumers in one Redis consumer group; each envelope is dedup'd in two stages (SHA-256 + external_id, then `sqlite-vec` cosine), scored by a `quick_think_llm` call (Redis-cached), ticker-validated against a reference table, and persisted as an `events` row. High-salience events upsert into `watchlist` with a 7-day TTL; user-curated rows never expire. An hourly sweep prunes expired auto-rows.

**Tech Stack:** Python 3.10+, existing `redis>=6.2.0` (using `redis.asyncio`), existing `sqlite-vec` (existing schema's 384-dim vec_index), existing LLM client factory + `quick_think_llm`. **New deps:** `sentence-transformers>=2.5` (CPU torch — local 384-dim embedder matching the schema), `feedparser>=6.0` (RSS adapter), `fakeredis>=2.20` (dev-only — unit tests). `telethon>=1.36` and `tweepy>=4.14` already ship in the `osint` extras.

**Prerequisites:**
- F1 complete on `main` (commits up to `4d5b0b5` shipped). F2 plan exists but is *not* required to land before F3 — schema additions are independent.
- Approved spec: [docs/superpowers/specs/2026-05-26-iic-forge-06-f3-sensing-triage-design.md](../specs/2026-05-26-iic-forge-06-f3-sensing-triage-design.md).
- DeepSeek API key configured in `.env` (used for the salience `quick_think_llm` call).
- Redis 7+ installed on the dev machine (`sudo apt install redis-server` on Ubuntu; the actual systemd unit is configured in Task 31, but the package needs to be installable for the integration tests that don't use `fakeredis`).
- Working tree on a feature branch (`feat/iic-forge-06-f3` already checked out per repo state).

**Pre-flight (one-time):**

```bash
cd /home/ziwei-huang/TradingAgents/TradingAgents
git status                                                  # working tree clean, on feat/iic-forge-06-f3
python -c "import sys; print(sys.version_info >= (3, 10))"  # True
python -c "import redis.asyncio; print('redis.asyncio OK')" # OK; ships in redis>=4.2
pytest --version                                            # >= 7.0
which redis-server || echo "install redis-server before integration tests"
```

---

## File Structure (locked in before tasks start)

**Created in this plan:**

| Path | Responsibility |
|---|---|
| `tradingagents/sensing/__init__.py` | Package marker |
| `tradingagents/sensing/envelope.py` | `Envelope` dataclass + JSON serialize/deserialize for Redis stream payloads |
| `tradingagents/sensing/cursor.py` | `CursorStore` — atomic upsert on `ingest_cursor` table |
| `tradingagents/sensing/redis_client.py` | Async Redis factory + consumer-group setup helper |
| `tradingagents/sensing/dedupe.py` | `DedupeStage1` (hash + external_id) + `DedupeStage2` (vec cosine) |
| `tradingagents/sensing/embeddings.py` | `Embedder` Protocol + `SentenceTransformerEmbedder` (384-dim) + `MockEmbedder` for tests |
| `tradingagents/sensing/ticker_validator.py` | Validates LLM-extracted tickers against the `tickers` reference table |
| `tradingagents/sensing/salience.py` | `score_salience()` — Redis-cached `quick_think_llm` call returning the structured JSON |
| `tradingagents/sensing/prompts.py` | `build_salience_prompt(envelope, watchlist, macro)` |
| `tradingagents/sensing/watchlist.py` | `add_user()`, `auto_promote()`, `sweep_expired()` — write paths into `watchlist` |
| `tradingagents/sensing/triage.py` | `process_one()` + `consume()` — XREADGROUP loop, dead-letter on N failures |
| `tradingagents/sensing/seed_tickers.py` | Pulls Polygon `/v3/reference/tickers` + crypto YAML; populates the `tickers` table |
| `tradingagents/sensing/data/crypto_universe.yaml` | Top-20 crypto static reference list |
| `tradingagents/sensing/adapters/__init__.py` | Package marker |
| `tradingagents/sensing/adapters/base.py` | `IngestAdapter` Protocol; `EnvelopeWriter` helper that does `XADD` + cursor.set |
| `tradingagents/sensing/adapters/polygon_news.py` | Polygon news REST polling, 60s interval, cursor=`last_published_utc`; `__main__` entry point |
| `tradingagents/sensing/adapters/rss.py` | `feedparser` per feed, 5-min interval, cursor=per-feed max `published_ts`; `__main__` entry point |
| `tradingagents/sensing/adapters/gdelt.py` | GDELT 2.0 doc API, 15-min interval, cursor=`last_seen_date`; `__main__` entry point |
| `tradingagents/sensing/adapters/macro.py` | FRED + TradingEconomics calendar, 30-min interval; `__main__` entry point |
| `tradingagents/sensing/adapters/telegram.py` | Telethon `add_event_handler(NewMessage)` streaming, dedicated session; `__main__` entry point |
| `tradingagents/sensing/adapters/x.py` | Polled search via `tweepy`, behind `enabled=False` config gate; `__main__` entry point |
| `cli/forge.py` | Typer sub-app — gains `watchlist` and `sense` sub-commands (this plan creates the file if F2 hasn't yet) |
| `scripts/f3_exit_gate.py` | Reads `events`/`watchlist`/`systemctl` for the 24h window; renders the dedup spot-check sample |
| `ops/redis/redis.conf` | AOF=everysec, maxmemory=256mb, noeviction |
| `ops/backup.sh` | Daily backup: SQLite via `.backup`, Redis via BGREWRITEAOF + cp |
| `ops/systemd/iic-sense-polygon.service` | systemd unit for Polygon adapter |
| `ops/systemd/iic-sense-telegram.service` | systemd unit for Telegram adapter |
| `ops/systemd/iic-sense-x.service` | systemd unit for X adapter |
| `ops/systemd/iic-sense-rss.service` | systemd unit for RSS adapter |
| `ops/systemd/iic-sense-gdelt.service` | systemd unit for GDELT adapter |
| `ops/systemd/iic-sense-macro.service` | systemd unit for macro adapter |
| `ops/systemd/iic-triage.service` | systemd unit for triage consumer |
| `ops/systemd/iic-watchlist-sweep.service` | systemd one-shot for the watchlist TTL prune |
| `ops/systemd/iic-watchlist-sweep.timer` | hourly timer for the sweep |
| `ops/runbooks/f3-exit-gate.md` | Pre-flight checklist for the 24h exit-gate run |
| `tests/sensing/__init__.py` | empty |
| `tests/sensing/test_envelope.py` | Envelope round-trip JSON |
| `tests/sensing/test_cursor.py` | Atomic upsert; cross-process safety via two connections |
| `tests/sensing/test_redis_client.py` | Consumer-group creation is idempotent (already-exists tolerated) |
| `tests/sensing/test_dedupe_stage1.py` | Repeat envelope → `status='duplicate'`, `deduped_of` set |
| `tests/sensing/test_dedupe_stage2.py` | Near-duplicate text → cosine ≥ 0.92 → `status='duplicate'` |
| `tests/sensing/test_embeddings.py` | MockEmbedder shape; SentenceTransformerEmbedder skipped if model not downloaded |
| `tests/sensing/test_ticker_validator.py` | Reference-table filtering; unknown symbols dropped |
| `tests/sensing/test_salience.py` | Redis cache hits on second call; LLM called once |
| `tests/sensing/test_prompts.py` | Watchlist CSV substituted; macro-context optional |
| `tests/sensing/test_watchlist.py` | user-add never expires; auto-promote gate; sweep skips `user` |
| `tests/sensing/test_seed_tickers.py` | Crypto YAML merged; Polygon mock pagination handled |
| `tests/sensing/test_adapter_polygon_news.py` | Envelope shape; cursor advances; mocked HTTP |
| `tests/sensing/test_adapter_rss.py` | Mocked feedparser; per-feed cursors |
| `tests/sensing/test_adapter_gdelt.py` | Mocked GDELT response shape |
| `tests/sensing/test_adapter_macro.py` | FRED + TE mocks; cursor advances |
| `tests/sensing/test_adapter_telegram.py` | Telethon event handler invoked produces an envelope |
| `tests/sensing/test_adapter_x.py` | `enabled=False` → adapter exits with code 0 (skipped, not an error) |
| `tests/sensing/test_triage_loop.py` | Single envelope flows envelope → events row → watchlist upsert |
| `tests/sensing/test_dead_letter.py` | After N=5 failures, message moves to `ingest:dead` |
| `tests/sensing/test_seed_tickers_integration.py` | (`integration` marker) hits real Polygon `/v3/reference/tickers` |
| `tests/test_default_config_f3.py` | F3 keys present with documented defaults |
| `tests/cli/test_forge_watchlist.py` | `forge watchlist add/list/remove` smoke |
| `tests/cli/test_forge_sense.py` | `forge sense reseed-tickers` invokes seeder |
| `tests/smoke/test_f3_exit_gate.py` | Boundary smoke: short synthetic-feed soak; gate evaluator pass/fail wiring |

**Modified in this plan:**

| Path | Change |
|---|---|
| `tradingagents/persistence/schema.sql` | Append 4 new `CREATE TABLE IF NOT EXISTS` blocks (ingest_cursor, tickers, event_fingerprints, event_embeddings) + extend the `events.status` enum comment to add `"duplicate"` |
| `tradingagents/persistence/db.py` | Extend `_EXPECTED_TABLES` set with the four new table names |
| `tradingagents/persistence/store.py` | Add helpers: `insert_event`, `insert_event_ticker`, `insert_event_fingerprint`, `insert_event_embedding`, `upsert_watchlist`, `upsert_ticker`, `get_active_watchlist`, `get_tickers_set` |
| `tradingagents/default_config.py` | Add F3 keys (see Task 1) |
| `tradingagents/dataflows/telegram_osint.py` | Replace stub with real Telethon `iter_messages` for the F0 analyst pull path; reads `TELEGRAM_OSINT_SESSION` (separate from F3's `TELEGRAM_SENSING_SESSION`) |
| `pyproject.toml` | Add `sentence-transformers`, `feedparser`, `redis-streams` is unneeded (use stdlib `redis.asyncio`); new `dev` optional dep on `fakeredis>=2.20` |
| `.env.example` | Document new sensing env vars: `TELEGRAM_OSINT_SESSION`, `TELEGRAM_SENSING_SESSION`, `FRED_API_KEY`, `TRADINGECONOMICS_KEY`, `GDELT_QUERY`, `X_BEARER_TOKEN` (already there), `RSS_FEEDS` |
| `cli/main.py` | Register `forge` sub-app (idempotent — F2 plan also registers it; whichever lands first does the work, the second skips) |

---

## Cross-cutting conventions

- **Tests:** pytest with markers `unit` (default, fast, isolated), `integration` (real API / external service), `smoke` (quick end-to-end).
- **Commits:** one per task. Format: `feat(<scope>): <subject>` matching repo style (see `git log --oneline -5`).
- **Cost guards:** every guard ships with `enabled: bool = False` default. Measurement always on. (See [saved memory](../../../.claude/projects/-home-ziwei-huang-TradingAgents/memory/cost-guards-disabled-by-default.md).)
- **Imports:** absolute, rooted at `tradingagents.` and `cli.`.
- **Schema:** append-only — no reshape of any existing F1/F2 table. New tables and one comment-only edit on `events.status`.
- **Time:** All timestamps are `datetime.now(timezone.utc).isoformat()` strings; comparisons use `datetime('now')` in SQL.
- **Async:** Triage + adapters use `asyncio`. Redis is `redis.asyncio.Redis`. Test fakes use `fakeredis.aioredis`.
- **Integration test gating:** Anything that hits a real external service is marked `integration` and skipped automatically when the relevant env var is unset/placeholder (see [conftest dummy_api_keys memory](../../../.claude/projects/-home-ziwei-huang-TradingAgents/memory/conftest-dummy-api-keys.md) — for tests needing real keys, call `load_dotenv(override=True)` inside the test body).

---

## Task 1: F3 default_config keys

**Files:**
- Modify: `tradingagents/default_config.py`
- Test: `tests/test_default_config_f3.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_default_config_f3.py`:

```python
import pytest


@pytest.mark.unit
def test_default_config_has_f3_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    # Buffer / Redis
    assert C["sensing_redis_url"] == "redis://127.0.0.1:6379/0"
    assert C["sensing_ingest_stream"] == "ingest:raw"
    assert C["sensing_consumer_group"] == "triage"
    assert C["sensing_dead_stream"] == "ingest:dead"
    # Triage
    assert C["sensing_triage_consumers"] == 4
    assert C["sensing_triage_max_failures"] == 5
    # Dedupe
    assert C["sensing_dedupe_cosine_threshold"] == 0.92
    assert C["sensing_dedupe_window_hours"] == 24
    assert C["sensing_fingerprint_ttl_hours"] == 72
    # Watchlist gate
    assert C["sensing_watchlist_salience_threshold"] == 0.7
    assert C["sensing_watchlist_confidence_threshold"] == 0.8
    assert C["sensing_watchlist_ttl_days"] == 7
    # Adapter enablement (X off by default — see spec D8/R-F3-3)
    assert C["sensing_adapters_enabled"] == {
        "polygon_news": True, "telegram": True, "rss": True,
        "gdelt": True, "macro": True, "x": False,
    }
    # Salience cache
    assert C["sensing_salience_cache_ttl_seconds"] == 86400
    # Watchlist refresh inside triage consumer
    assert C["sensing_watchlist_refresh_seconds"] == 60
    # Embedder
    assert C["sensing_embedder_model"] == "sentence-transformers/all-MiniLM-L6-v2"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_default_config_f3.py -v
```

Expected: FAIL — keys missing.

- [ ] **Step 3: Add the keys**

In `tradingagents/default_config.py`, after the F1 `cost_guard_enabled` block (around line 60), add:

```python
    # IIC-FORGE F3 — always-on sensing + triage
    "sensing_redis_url": "redis://127.0.0.1:6379/0",
    "sensing_ingest_stream": "ingest:raw",
    "sensing_consumer_group": "triage",
    "sensing_dead_stream": "ingest:dead",
    "sensing_triage_consumers": 4,
    "sensing_triage_max_failures": 5,
    "sensing_dedupe_cosine_threshold": 0.92,
    "sensing_dedupe_window_hours": 24,
    "sensing_fingerprint_ttl_hours": 72,
    "sensing_watchlist_salience_threshold": 0.7,
    "sensing_watchlist_confidence_threshold": 0.8,
    "sensing_watchlist_ttl_days": 7,
    "sensing_watchlist_refresh_seconds": 60,
    "sensing_salience_cache_ttl_seconds": 86400,
    "sensing_embedder_model": "sentence-transformers/all-MiniLM-L6-v2",
    "sensing_adapters_enabled": {
        "polygon_news": True,
        "telegram": True,
        "rss": True,
        "gdelt": True,
        "macro": True,
        "x": False,   # off by default per spec D8 / R-F3-3
    },
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_default_config_f3.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tests/test_default_config_f3.py
git commit -m "config: add F3 sensing + triage defaults"
```

---

## Task 2: pyproject.toml — new deps

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Inspect the existing optional-dependencies block**

```bash
grep -n "optional-dependencies\|sentence\|feedparser\|fakeredis\|osint" pyproject.toml
```

Confirms `osint = ["telethon>=1.36", "tweepy>=4.14"]` already exists.

- [ ] **Step 2: Edit `pyproject.toml`**

In the `[project.optional-dependencies]` block, change the `osint` line to keep Telethon+Tweepy AND extend with the new sensing deps in a fresh `sensing` extra, then add a `dev` extra for `fakeredis`:

```toml
osint = ["telethon>=1.36", "tweepy>=4.14"]
sensing = [
    "telethon>=1.36",                  # F3 telegram adapter (also in osint for F0)
    "tweepy>=4.14",                    # F3 x adapter
    "feedparser>=6.0",                 # F3 rss adapter
    "sentence-transformers>=2.5",      # 384-dim local embedder; matches vec_index schema
]
dev = [
    "fakeredis>=2.20",                 # async-compatible Redis fake for unit tests
]
```

- [ ] **Step 3: Sync the env (do not fail the plan if torch wheel is large — pre-flight)**

```bash
pip install -e ".[sensing,dev]"
python -c "import feedparser, telethon, tweepy, fakeredis; print('sensing deps OK')"
python -c "from sentence_transformers import SentenceTransformer; print('st OK')"
```

Expected: imports succeed. Sentence-transformers will lazy-download the model on first use — that download is deferred to runtime (Task 10 task notes).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add F3 sensing extras (feedparser, sentence-transformers) + dev fakeredis"
```

---

## Task 3: Schema additions — four new tables + status comment

**Files:**
- Modify: `tradingagents/persistence/schema.sql`
- Modify: `tradingagents/persistence/db.py`
- Test: `tests/persistence/test_schema_f3.py`

- [ ] **Step 1: Write the failing test**

Create `tests/persistence/test_schema_f3.py`:

```python
import pytest
from tradingagents.persistence.db import connect, schema_tables


@pytest.mark.unit
def test_f3_tables_present(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    rows = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"ingest_cursor", "tickers", "event_fingerprints",
            "event_embeddings"} <= rows


@pytest.mark.unit
def test_expected_tables_set_includes_f3():
    assert {"ingest_cursor", "tickers", "event_fingerprints",
            "event_embeddings"} <= schema_tables()


@pytest.mark.unit
def test_event_fingerprints_pk_is_composite(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = list(conn.execute("PRAGMA table_info(event_fingerprints)"))
    pk_cols = [c[1] for c in cols if c[5] > 0]
    assert set(pk_cols) == {"fingerprint", "kind"}


@pytest.mark.unit
def test_tickers_active_index(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    idx_names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )]
    assert "idx_tickers_active" in idx_names


@pytest.mark.unit
def test_status_enum_comment_extended_with_duplicate():
    from pathlib import Path
    text = Path("tradingagents/persistence/schema.sql").read_text()
    # Status comment line for `events.status` now documents the four-value enum.
    assert '"new" | "triaged" | "discarded" | "duplicate"' in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persistence/test_schema_f3.py -v
```

Expected: FAIL — tables and comment don't exist.

- [ ] **Step 3: Append the four tables to `schema.sql`**

Add this block to the END of `tradingagents/persistence/schema.sql`:

```sql
-- ============================================================
-- F3 sensing/triage append-only tables (added by IIC-FORGE-06)
-- ============================================================

CREATE TABLE IF NOT EXISTS ingest_cursor (
    source     TEXT PRIMARY KEY,           -- e.g., "polygon_news"
    cursor     TEXT NOT NULL,              -- adapter-specific opaque payload
    updated_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickers (
    ticker     TEXT PRIMARY KEY,           -- "AAPL", "BTC-USD"
    exchange   TEXT NOT NULL,              -- "NASDAQ" | "NYSE" | "ARCA" | "CRYPTO"
    name       TEXT NOT NULL,
    aliases    TEXT,                       -- JSON array: ["Apple", "Apple Computer"]
    active     INTEGER NOT NULL DEFAULT 1, -- 0 = delisted (filtered)
    updated_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickers_active ON tickers(active);

CREATE TABLE IF NOT EXISTS event_fingerprints (
    fingerprint TEXT NOT NULL,             -- external_id or sha256 hex
    kind        TEXT NOT NULL,             -- 'external_id' | 'sha256'
    event_id    TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    created_ts  TEXT NOT NULL,
    PRIMARY KEY (fingerprint, kind)
);
CREATE INDEX IF NOT EXISTS idx_event_fingerprints_event ON event_fingerprints(event_id);

CREATE TABLE IF NOT EXISTS event_embeddings (
    event_id   TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    vec_id     INTEGER NOT NULL,           -- app-layer FK to vec_index.rowid
    created_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_embeddings_vec ON event_embeddings(vec_id);
```

- [ ] **Step 4: Extend the `events.status` comment**

In `tradingagents/persistence/schema.sql`, find the line:

```sql
    status          TEXT NOT NULL                                -- "new" | "triaged" | "discarded"
```

Change it to:

```sql
    status          TEXT NOT NULL                                -- "new" | "triaged" | "discarded" | "duplicate"
```

- [ ] **Step 5: Extend `_EXPECTED_TABLES` in `db.py`**

In `tradingagents/persistence/db.py`, change `_EXPECTED_TABLES` to include the four new names:

```python
_EXPECTED_TABLES: Set[str] = {
    "runs", "costs", "briefs", "brief_actions", "suppression",
    "memories", "outcome_log",
    "backtests", "backtest_runs",
    "events", "event_ticker", "watchlist",
    "queue_jobs", "deliveries",
    # F3:
    "ingest_cursor", "tickers", "event_fingerprints", "event_embeddings",
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/persistence/test_schema_f3.py -v
```

Expected: 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/persistence/schema.sql tradingagents/persistence/db.py tests/persistence/test_schema_f3.py
git commit -m "schema(f3): add ingest_cursor, tickers, event_fingerprints, event_embeddings; extend events.status enum"
```

---

## Task 4: Store helpers for events, event_ticker, watchlist

**Files:**
- Modify: `tradingagents/persistence/store.py`
- Test: `tests/persistence/test_store_f3.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/persistence/test_store_f3.py`:

```python
import json
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_insert_event(conn):
    from tradingagents.persistence.store import insert_event
    insert_event(
        conn, event_id="e1", source="polygon_news",
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        salience=0.9, raw_path="data/events/e1.json",
        status="triaged", deduped_of=None,
    )
    row = conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
    assert row["status"] == "triaged"
    assert row["salience"] == pytest.approx(0.9)


@pytest.mark.unit
def test_insert_event_ticker(conn):
    from tradingagents.persistence.store import insert_event, insert_event_ticker
    insert_event(conn, event_id="e1", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.6, raw_path="data/events/e1.json",
                 status="triaged", deduped_of=None)
    insert_event_ticker(conn, event_id="e1", ticker="AAPL", confidence=0.92)
    row = conn.execute("SELECT * FROM event_ticker WHERE event_id='e1'").fetchone()
    assert row["ticker"] == "AAPL"
    assert row["confidence"] == pytest.approx(0.92)


@pytest.mark.unit
def test_upsert_watchlist_user(conn):
    from tradingagents.persistence.store import upsert_watchlist
    upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='AAPL'").fetchone()
    assert row["ttl_until"] is None
    assert "user" in json.loads(row["tags"])


@pytest.mark.unit
def test_upsert_watchlist_auto(conn):
    from tradingagents.persistence.store import upsert_watchlist
    ttl = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    upsert_watchlist(conn, ticker="TSLA", ttl_until=ttl,
                     tags=["auto", "event:e-42"])
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='TSLA'").fetchone()
    assert row["ttl_until"] == ttl
    assert set(json.loads(row["tags"])) == {"auto", "event:e-42"}


@pytest.mark.unit
def test_upsert_watchlist_preserves_added_ts(conn):
    """Second upsert must NOT overwrite the original added_ts."""
    from tradingagents.persistence.store import upsert_watchlist
    upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    first = conn.execute("SELECT added_ts FROM watchlist WHERE ticker='NVDA'").fetchone()
    upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user", "extra"])
    second = conn.execute("SELECT added_ts FROM watchlist WHERE ticker='NVDA'").fetchone()
    assert first["added_ts"] == second["added_ts"]


@pytest.mark.unit
def test_get_active_watchlist(conn):
    from tradingagents.persistence.store import upsert_watchlist, get_active_watchlist
    now = datetime.now(timezone.utc)
    upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])
    upsert_watchlist(conn, ticker="OLD",
                     ttl_until=(now - timedelta(days=1)).isoformat(),
                     tags=["auto"])
    upsert_watchlist(conn, ticker="TSLA",
                     ttl_until=(now + timedelta(days=3)).isoformat(),
                     tags=["auto"])
    active = get_active_watchlist(conn)
    assert set(active) == {"AAPL", "TSLA"}  # OLD is expired


@pytest.mark.unit
def test_upsert_ticker_and_get_set(conn):
    from tradingagents.persistence.store import upsert_ticker, get_tickers_set
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=["Apple"], active=True)
    upsert_ticker(conn, ticker="DEAD", exchange="NYSE",
                  name="Defunct Co", aliases=[], active=False)
    s = get_tickers_set(conn)
    assert "AAPL" in s
    assert "DEAD" not in s  # inactive filtered out


@pytest.mark.unit
def test_insert_event_fingerprint(conn):
    from tradingagents.persistence.store import insert_event, insert_event_fingerprint
    insert_event(conn, event_id="e1", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="data/events/e1.json",
                 status="triaged", deduped_of=None)
    insert_event_fingerprint(conn, fingerprint="abc123",
                             kind="sha256", event_id="e1", source="rss")
    row = conn.execute(
        "SELECT * FROM event_fingerprints WHERE fingerprint='abc123' AND kind='sha256'"
    ).fetchone()
    assert row["event_id"] == "e1"


@pytest.mark.unit
def test_insert_event_embedding(conn):
    from tradingagents.persistence.store import insert_event, insert_event_embedding
    insert_event(conn, event_id="e1", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="data/events/e1.json",
                 status="triaged", deduped_of=None)
    insert_event_embedding(conn, event_id="e1", vec_id=42)
    row = conn.execute("SELECT * FROM event_embeddings WHERE event_id='e1'").fetchone()
    assert row["vec_id"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persistence/test_store_f3.py -v
```

Expected: ImportError / AttributeError on each helper.

- [ ] **Step 3: Implement the helpers in `tradingagents/persistence/store.py`**

Append to the end of `tradingagents/persistence/store.py`:

```python
# --------------------------------------------------------------------
# F3 helpers — events / event_ticker / watchlist / tickers / fingerprints
# --------------------------------------------------------------------

import json as _json
from datetime import datetime as _dt, timezone as _tz


def _now_iso() -> str:
    return _dt.now(_tz.utc).isoformat()


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    source: str,
    ingested_ts: str,
    salience: Optional[float],
    raw_path: Optional[str],
    status: str,
    deduped_of: Optional[str],
) -> None:
    conn.execute(
        "INSERT INTO events (event_id, source, ingested_ts, salience, "
        "raw_path, deduped_of, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, source, ingested_ts, salience, raw_path, deduped_of, status),
    )
    conn.commit()


def insert_event_ticker(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    ticker: str,
    confidence: Optional[float],
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_ticker (event_id, ticker, confidence) "
        "VALUES (?, ?, ?)",
        (event_id, ticker, confidence),
    )
    conn.commit()


def upsert_watchlist(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    ttl_until: Optional[str],
    tags: Iterable[str],
) -> None:
    """Insert or update a watchlist row.

    - On insert, sets ``added_ts = now()`` and ``last_briefed = now()``.
    - On update, preserves ``added_ts``; refreshes ``last_briefed`` and ``ttl_until``;
      merges tag set.
    """
    now = _now_iso()
    incoming_tags = sorted(set(tags))
    existing = conn.execute(
        "SELECT added_ts, tags FROM watchlist WHERE ticker = ?", (ticker,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO watchlist (ticker, added_ts, last_briefed, ttl_until, tags) "
            "VALUES (?, ?, ?, ?, ?)",
            (ticker, now, now, ttl_until, _json.dumps(incoming_tags)),
        )
    else:
        prior_tags = _json.loads(existing["tags"]) if existing["tags"] else []
        merged = sorted(set(prior_tags) | set(incoming_tags))
        conn.execute(
            "UPDATE watchlist SET last_briefed = ?, ttl_until = ?, tags = ? "
            "WHERE ticker = ?",
            (now, ttl_until, _json.dumps(merged), ticker),
        )
    conn.commit()


def get_active_watchlist(conn: sqlite3.Connection) -> list[str]:
    """Tickers that are either user-curated (ttl_until IS NULL) or not yet expired."""
    rows = conn.execute(
        "SELECT ticker FROM watchlist "
        "WHERE ttl_until IS NULL OR ttl_until > datetime('now')"
    )
    return [r["ticker"] for r in rows]


def upsert_ticker(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    exchange: str,
    name: str,
    aliases: Iterable[str],
    active: bool,
) -> None:
    conn.execute(
        "INSERT INTO tickers (ticker, exchange, name, aliases, active, updated_ts) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(ticker) DO UPDATE SET "
        "exchange = excluded.exchange, "
        "name = excluded.name, "
        "aliases = excluded.aliases, "
        "active = excluded.active, "
        "updated_ts = excluded.updated_ts",
        (ticker, exchange, name, _json.dumps(list(aliases)),
         1 if active else 0, _now_iso()),
    )
    conn.commit()


def get_tickers_set(conn: sqlite3.Connection) -> set[str]:
    """All currently-active tickers — used by ticker validator."""
    rows = conn.execute("SELECT ticker FROM tickers WHERE active = 1")
    return {r["ticker"] for r in rows}


def insert_event_fingerprint(
    conn: sqlite3.Connection,
    *,
    fingerprint: str,
    kind: str,
    event_id: str,
    source: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_fingerprints "
        "(fingerprint, kind, event_id, source, created_ts) VALUES (?, ?, ?, ?, ?)",
        (fingerprint, kind, event_id, source, _now_iso()),
    )
    conn.commit()


def insert_event_embedding(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    vec_id: int,
) -> None:
    conn.execute(
        "INSERT INTO event_embeddings (event_id, vec_id, created_ts) "
        "VALUES (?, ?, ?)",
        (event_id, vec_id, _now_iso()),
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/persistence/test_store_f3.py -v
```

Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/persistence/store.py tests/persistence/test_store_f3.py
git commit -m "persist(f3): event/event_ticker/watchlist/tickers/fingerprint/embedding helpers"
```

---

## Task 5: Envelope dataclass

**Files:**
- Create: `tradingagents/sensing/__init__.py`
- Create: `tradingagents/sensing/envelope.py`
- Test: `tests/sensing/__init__.py` (empty)
- Test: `tests/sensing/test_envelope.py`

- [ ] **Step 1: Create empty package markers**

Create `tradingagents/sensing/__init__.py`:

```python
"""IIC-FORGE F3 always-on sensing + triage.

See ADR / design in:
docs/superpowers/specs/2026-05-26-iic-forge-06-f3-sensing-triage-design.md
"""
```

Create `tests/sensing/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

Create `tests/sensing/test_envelope.py`:

```python
import json
import pytest


@pytest.mark.unit
def test_envelope_round_trip_json():
    from tradingagents.sensing.envelope import Envelope
    env = Envelope(
        source="polygon_news",
        ingested_ts="2026-05-26T14:33:21.123Z",
        external_id="pn:abc123",
        text="Apple reports earnings beat.",
        source_tags={"tickers": ["AAPL"], "category": "earnings"},
        raw_path="data/events/staging/2026-05-26/abc123.json",
    )
    blob = env.to_json()
    parsed = Envelope.from_json(blob)
    assert parsed == env


@pytest.mark.unit
def test_envelope_to_redis_fields():
    """Redis XADD takes a flat dict[str, str]; envelope must serialize cleanly."""
    from tradingagents.sensing.envelope import Envelope
    env = Envelope(
        source="rss", ingested_ts="2026-05-26T00:00:00Z",
        external_id="rss:1", text="...", source_tags={}, raw_path="p",
    )
    fields = env.to_redis_fields()
    assert isinstance(fields, dict)
    assert all(isinstance(k, str) and isinstance(v, str)
               for k, v in fields.items())
    assert "data" in fields
    assert json.loads(fields["data"])["source"] == "rss"


@pytest.mark.unit
def test_envelope_from_redis_fields():
    from tradingagents.sensing.envelope import Envelope
    env = Envelope(source="x", ingested_ts="t", external_id="x:1",
                   text="hello", source_tags={"a": 1}, raw_path="p")
    fields = env.to_redis_fields()
    assert Envelope.from_redis_fields(fields) == env


@pytest.mark.unit
def test_envelope_text_truncation_for_fingerprint():
    """Whitespace + leading/trailing-noise normalization for SHA-256 input."""
    from tradingagents.sensing.envelope import normalize_for_fingerprint
    assert normalize_for_fingerprint("  Hello   World\n\n") == \
           normalize_for_fingerprint("hello world")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/sensing/test_envelope.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `envelope.py`**

Create `tradingagents/sensing/envelope.py`:

```python
"""Envelope: the single message shape on the ``ingest:raw`` Redis stream.

Adapters construct ``Envelope`` instances and call ``redis.xadd(stream, env.to_redis_fields())``.
The triage consumer reverses with ``Envelope.from_redis_fields(fields)``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_fingerprint(text: str) -> str:
    """Whitespace-collapsed, lowercased text for SHA-256 dedup hashing.

    Identical wording with different whitespace / casing must hash equal.
    """
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


@dataclass(frozen=True)
class Envelope:
    source: str            # "polygon_news", "telegram", "x", "rss", "gdelt", "macro"
    ingested_ts: str       # ISO-8601 UTC, e.g. "2026-05-26T14:33:21.123Z"
    external_id: str       # source-supplied stable ID; empty string if unavailable
    text: str              # normalized full text the LLM and embedder see
    source_tags: Dict[str, Any]  # e.g. {"tickers": ["AAPL"], "category": "earnings"}
    raw_path: str          # filesystem path under data/events/staging/...

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, blob: str) -> "Envelope":
        return cls(**json.loads(blob))

    def to_redis_fields(self) -> Dict[str, str]:
        # One field carries the whole JSON. Keeps XADD payload simple and avoids
        # collisions with Redis-reserved field names.
        return {"data": self.to_json()}

    @classmethod
    def from_redis_fields(cls, fields: Dict[str, str]) -> "Envelope":
        # Redis returns bytes when decode_responses=False; tolerate both.
        data = fields.get("data") or fields.get(b"data")
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return cls.from_json(data)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/sensing/test_envelope.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/sensing/__init__.py tradingagents/sensing/envelope.py \
        tests/sensing/__init__.py tests/sensing/test_envelope.py
git commit -m "sensing: Envelope dataclass + Redis-field serialization"
```

---

## Task 6: CursorStore — atomic upsert on ingest_cursor

**Files:**
- Create: `tradingagents/sensing/cursor.py`
- Test: `tests/sensing/test_cursor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_cursor.py`:

```python
import pytest
from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_cursor_get_missing_returns_none(conn):
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    assert cs.get("polygon_news") is None


@pytest.mark.unit
def test_cursor_set_and_get(conn):
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    cs.set("polygon_news", "2026-05-26T14:00:00Z")
    assert cs.get("polygon_news") == "2026-05-26T14:00:00Z"


@pytest.mark.unit
def test_cursor_set_overwrites(conn):
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    cs.set("rss", "a")
    cs.set("rss", "b")
    assert cs.get("rss") == "b"


@pytest.mark.unit
def test_cursor_updated_ts_advances(conn):
    import time
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    cs.set("x", "1")
    t1 = conn.execute("SELECT updated_ts FROM ingest_cursor WHERE source='x'").fetchone()[0]
    time.sleep(0.01)
    cs.set("x", "2")
    t2 = conn.execute("SELECT updated_ts FROM ingest_cursor WHERE source='x'").fetchone()[0]
    assert t2 > t1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_cursor.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `cursor.py`**

Create `tradingagents/sensing/cursor.py`:

```python
"""Per-adapter resume-cursor store backed by the `ingest_cursor` SQLite table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


class CursorStore:
    """Thin wrapper over `ingest_cursor`. WAL mode keeps it lock-free in practice."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, source: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT cursor FROM ingest_cursor WHERE source = ?", (source,)
        ).fetchone()
        return row["cursor"] if row else None

    def set(self, source: str, cursor: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO ingest_cursor (source, cursor, updated_ts) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET cursor = excluded.cursor, "
            "updated_ts = excluded.updated_ts",
            (source, cursor, now),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_cursor.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/cursor.py tests/sensing/test_cursor.py
git commit -m "sensing: CursorStore atomic upsert"
```

---

## Task 7: Redis async client factory + consumer-group helper

**Files:**
- Create: `tradingagents/sensing/redis_client.py`
- Test: `tests/sensing/test_redis_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_redis_client.py`:

```python
import pytest
import fakeredis.aioredis


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_consumer_group_creates_when_missing():
    from tradingagents.sensing.redis_client import ensure_consumer_group
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="ingest:raw", group="triage")
    info = await r.xinfo_groups("ingest:raw")
    assert any(g["name"] == "triage" for g in info)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_consumer_group_tolerates_already_exists():
    from tradingagents.sensing.redis_client import ensure_consumer_group
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="s", group="g")
    # Second call must not raise.
    await ensure_consumer_group(r, stream="s", group="g")
```

- [ ] **Step 2: Install `pytest-asyncio` for the asyncio mark**

```bash
pip install "pytest-asyncio>=0.23"
```

And add to `pyproject.toml` under `[project.optional-dependencies] dev`:

```toml
dev = [
    "fakeredis>=2.20",
    "pytest-asyncio>=0.23",
]
```

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/sensing/test_redis_client.py -v
```

Expected: ImportError on `tradingagents.sensing.redis_client`.

- [ ] **Step 4: Implement `redis_client.py`**

Create `tradingagents/sensing/redis_client.py`:

```python
"""Async Redis factory + helpers shared by adapters and triage."""

from __future__ import annotations

import redis.asyncio as aioredis
from redis.exceptions import ResponseError


def make_redis(url: str) -> aioredis.Redis:
    """Single point that constructs the async Redis client.

    `decode_responses=True` so all reads return ``str`` — keeps Envelope
    serialization simple.
    """
    return aioredis.from_url(url, decode_responses=True)


async def ensure_consumer_group(
    r: aioredis.Redis, *, stream: str, group: str,
) -> None:
    """Idempotent XGROUP CREATE with MKSTREAM.

    Already-exists is the only acceptable error.
    """
    try:
        await r.xgroup_create(name=stream, groupname=group, id="0",
                              mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/sensing/test_redis_client.py -v
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/sensing/redis_client.py tests/sensing/test_redis_client.py pyproject.toml
git commit -m "sensing: async Redis client + idempotent consumer-group helper"
```

---

## Task 8: Stage-1 dedupe (external_id + SHA-256 hash)

**Files:**
- Create: `tradingagents/sensing/dedupe.py`
- Test: `tests/sensing/test_dedupe_stage1.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_dedupe_stage1.py`:

```python
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


def _env(text="Apple beats", ext_id="pn:1", source="polygon_news"):
    from tradingagents.sensing.envelope import Envelope
    return Envelope(
        source=source,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id=ext_id,
        text=text,
        source_tags={},
        raw_path="data/events/staging/x.json",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stage1_first_event_not_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage1
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    hit = await ds1.check(_env())
    assert hit is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stage1_repeat_external_id_is_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage1
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    env = _env(ext_id="pn:42")
    await ds1.record(env, event_id="ev-1")
    hit = await ds1.check(_env(text="totally different", ext_id="pn:42"))
    assert hit == "ev-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stage1_repeat_text_is_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage1
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    await ds1.record(_env(text="Apple beats earnings"), event_id="ev-1")
    hit = await ds1.check(_env(text="apple beats   earnings", ext_id="pn:other"))
    assert hit == "ev-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stage1_redis_hot_path_avoids_sqlite(conn):
    """If Redis SISMEMBER hits, no SQLite query should be needed."""
    from tradingagents.sensing.dedupe import DedupeStage1, _fp
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    env = _env(text="foo")
    await ds1.record(env, event_id="ev-1")
    # The recorder should have populated Redis.
    assert await r.sismember(ds1._sha_key(), _fp(env.text))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_dedupe_stage1.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement Stage-1 in `dedupe.py`**

Create `tradingagents/sensing/dedupe.py`:

```python
"""Two-stage dedupe pipeline.

Stage 1 catches re-deliveries / re-publishes via external_id + SHA-256 of the
normalized text. Cheap: one Redis SISMEMBER + one SQLite PK lookup.

Stage 2 (Task 12) catches semantic duplicates across sources via embedding
cosine similarity over the last 24h.

Duplicates are NOT dropped — they are written to ``events`` with
``status='duplicate'`` and ``deduped_of=<original>`` so the exit gate
can score the 80% deduped criterion.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from .envelope import Envelope, normalize_for_fingerprint


def _fp(text: str) -> str:
    """SHA-256 hex of the normalized text. Used as the canonical fingerprint."""
    return hashlib.sha256(
        normalize_for_fingerprint(text).encode("utf-8")
    ).hexdigest()


class DedupeStage1:
    """Hash + external_id lookup via Redis hot-path then SQLite durable record."""

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        redis: aioredis.Redis,
        fingerprint_ttl_hours: int,
    ) -> None:
        self._conn = conn
        self._redis = redis
        self._ttl_seconds = fingerprint_ttl_hours * 3600

    def _today_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    def _sha_key(self) -> str:
        return f"fingerprints:sha:{self._today_utc()}"

    def _ext_key(self) -> str:
        return f"fingerprints:ext:{self._today_utc()}"

    async def check(self, env: Envelope) -> Optional[str]:
        """Return event_id of the original if this envelope is a duplicate, else None."""
        fp = _fp(env.text)

        # Hot path: Redis fingerprint sets for the last few days.
        # SISMEMBER is O(1); falling through to SQLite happens only on misses.
        if env.external_id:
            if await self._redis.sismember(self._ext_key(), env.external_id):
                row = self._conn.execute(
                    "SELECT event_id FROM event_fingerprints "
                    "WHERE fingerprint = ? AND kind = 'external_id'",
                    (env.external_id,),
                ).fetchone()
                if row:
                    return row["event_id"]
        if await self._redis.sismember(self._sha_key(), fp):
            row = self._conn.execute(
                "SELECT event_id FROM event_fingerprints "
                "WHERE fingerprint = ? AND kind = 'sha256'",
                (fp,),
            ).fetchone()
            if row:
                return row["event_id"]

        # Cold path: Redis missed (set expired or eviction). Check SQLite directly.
        if env.external_id:
            row = self._conn.execute(
                "SELECT event_id FROM event_fingerprints "
                "WHERE fingerprint = ? AND kind = 'external_id'",
                (env.external_id,),
            ).fetchone()
            if row:
                return row["event_id"]
        row = self._conn.execute(
            "SELECT event_id FROM event_fingerprints "
            "WHERE fingerprint = ? AND kind = 'sha256'",
            (fp,),
        ).fetchone()
        return row["event_id"] if row else None

    async def record(self, env: Envelope, *, event_id: str) -> None:
        """Persist the new event's fingerprints. Call ONLY on non-duplicates."""
        from tradingagents.persistence.store import insert_event_fingerprint
        fp = _fp(env.text)
        if env.external_id:
            insert_event_fingerprint(
                self._conn, fingerprint=env.external_id, kind="external_id",
                event_id=event_id, source=env.source,
            )
            await self._redis.sadd(self._ext_key(), env.external_id)
            await self._redis.expire(self._ext_key(), self._ttl_seconds)
        insert_event_fingerprint(
            self._conn, fingerprint=fp, kind="sha256",
            event_id=event_id, source=env.source,
        )
        await self._redis.sadd(self._sha_key(), fp)
        await self._redis.expire(self._sha_key(), self._ttl_seconds)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_dedupe_stage1.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/dedupe.py tests/sensing/test_dedupe_stage1.py
git commit -m "sensing: Stage-1 dedupe (Redis hot-path + SQLite durable fingerprints)"
```

---

## Task 9: Embedder — Protocol + sentence-transformers + mock

**Files:**
- Create: `tradingagents/sensing/embeddings.py`
- Test: `tests/sensing/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_embeddings.py`:

```python
import pytest


@pytest.mark.unit
def test_mock_embedder_shape():
    from tradingagents.sensing.embeddings import MockEmbedder
    e = MockEmbedder(dim=384)
    v = e.embed("hello world")
    assert len(v) == 384
    assert all(isinstance(x, float) for x in v)


@pytest.mark.unit
def test_mock_embedder_deterministic():
    from tradingagents.sensing.embeddings import MockEmbedder
    e = MockEmbedder(dim=384)
    assert e.embed("foo") == e.embed("foo")
    assert e.embed("foo") != e.embed("bar")


@pytest.mark.unit
def test_mock_embedder_l2_normalized():
    """Vectors must be unit-norm so cosine == dot product."""
    import math
    from tradingagents.sensing.embeddings import MockEmbedder
    v = MockEmbedder(dim=384).embed("x")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.unit
def test_sentence_transformer_embedder_lazy_import(monkeypatch):
    """Constructor must not fail at import-time even if the model isn't downloaded."""
    from tradingagents.sensing.embeddings import SentenceTransformerEmbedder
    # Should construct without loading the model.
    emb = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    assert emb.dim == 384  # documented constant for that model
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_embeddings.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `embeddings.py`**

Create `tradingagents/sensing/embeddings.py`:

```python
"""Text embedder for Stage-2 dedupe.

The SQLite vec_index column is float[384], matching all-MiniLM-L6-v2.
Production uses ``SentenceTransformerEmbedder``; tests use ``MockEmbedder``
(deterministic L2-normalized vectors derived from SHA-256 of the input).
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import List, Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> List[float]: ...


class MockEmbedder:
    """Deterministic L2-normalized hash-vector for tests.

    Two identical inputs give identical vectors. Different inputs give
    cosine far below 0.92, so the test suite never crosses the dedupe
    threshold accidentally.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand the 32-byte seed into self.dim float chunks via repeated SHA-256.
        out: List[float] = []
        block = seed
        while len(out) < self.dim:
            block = hashlib.sha256(block).digest()
            for i in range(0, len(block), 4):
                if len(out) >= self.dim:
                    break
                # interpret 4 bytes as signed int → [-1, 1]
                (n,) = struct.unpack(">i", block[i:i+4])
                out.append(n / 2_147_483_648.0)
        norm = math.sqrt(sum(x * x for x in out)) or 1.0
        return [x / norm for x in out]


class SentenceTransformerEmbedder:
    """Production embedder. Model loads lazily on first .embed() call."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None  # lazy
        # all-MiniLM-L6-v2 is 384-dim; this is documented and stable.
        self.dim = 384

    def _ensure_loaded(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import
            self._model = SentenceTransformer(self._model_name)

    def embed(self, text: str) -> List[float]:
        self._ensure_loaded()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_embeddings.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/embeddings.py tests/sensing/test_embeddings.py
git commit -m "sensing: Embedder Protocol + SentenceTransformerEmbedder + MockEmbedder"
```

---


## Task 10: Stage-2 dedupe (semantic via sqlite-vec cosine)

**Files:**
- Modify: `tradingagents/sensing/dedupe.py` — add `DedupeStage2`
- Test: `tests/sensing/test_dedupe_stage2.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_dedupe_stage2.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import insert_event, insert_event_embedding


def _insert_with_vec(conn, *, event_id, vec, ingested_ts=None):
    ts = ingested_ts or datetime.now(timezone.utc).isoformat()
    insert_event(conn, event_id=event_id, source="rss", ingested_ts=ts,
                 salience=0.5, raw_path=f"data/events/{event_id}.json",
                 status="triaged", deduped_of=None)
    cur = conn.execute(
        "INSERT INTO vec_index (embedding) VALUES (?)",
        (bytes(__import__("struct").pack(f"{len(vec)}f", *vec)),),
    )
    insert_event_embedding(conn, event_id=event_id, vec_id=cur.lastrowid)
    return cur.lastrowid


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_stage2_no_neighbor_returns_none(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    ds2 = DedupeStage2(conn=conn, embedder=MockEmbedder(),
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("first item ever") is None


@pytest.mark.unit
def test_stage2_identical_text_is_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    emb = MockEmbedder()
    vec = emb.embed("Apple beats earnings")
    _insert_with_vec(conn, event_id="ev-1", vec=vec)
    ds2 = DedupeStage2(conn=conn, embedder=emb,
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("Apple beats earnings") == "ev-1"


@pytest.mark.unit
def test_stage2_dissimilar_text_is_not_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    emb = MockEmbedder()
    _insert_with_vec(conn, event_id="ev-1", vec=emb.embed("Apple beats"))
    ds2 = DedupeStage2(conn=conn, embedder=emb,
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("Federal Reserve raises rates 25 bps") is None


@pytest.mark.unit
def test_stage2_window_excludes_old_events(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    emb = MockEmbedder()
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    _insert_with_vec(conn, event_id="ev-old", vec=emb.embed("xyz"),
                     ingested_ts=old_ts)
    ds2 = DedupeStage2(conn=conn, embedder=emb,
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("xyz") is None  # outside 24h window


@pytest.mark.unit
def test_stage2_record_inserts_embedding_and_returns_vec_id(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    insert_event(conn, event_id="ev-new", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="p", status="triaged", deduped_of=None)
    ds2 = DedupeStage2(conn=conn, embedder=MockEmbedder(),
                       cosine_threshold=0.92, window_hours=24)
    vec_id = ds2.record(text="anything", event_id="ev-new")
    assert isinstance(vec_id, int)
    row = conn.execute(
        "SELECT vec_id FROM event_embeddings WHERE event_id='ev-new'"
    ).fetchone()
    assert row["vec_id"] == vec_id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_dedupe_stage2.py -v
```

Expected: ImportError on `DedupeStage2`.

- [ ] **Step 3: Append `DedupeStage2` to `tradingagents/sensing/dedupe.py`**

Append to `tradingagents/sensing/dedupe.py`:

```python
import struct
from typing import Optional


class DedupeStage2:
    """Semantic dedupe via sqlite-vec cosine over the last N hours.

    Embeds the candidate text, runs a K-NN MATCH against vec_index, then
    filters joined event_embeddings + events for the freshness window.
    Returns the matching event_id if cosine >= threshold, else None.
    """

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        embedder,                        # Embedder protocol
        cosine_threshold: float,
        window_hours: int,
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._threshold = cosine_threshold
        self._window_hours = window_hours

    def _pack(self, vec) -> bytes:
        return bytes(struct.pack(f"{len(vec)}f", *vec))

    def check(self, text: str) -> Optional[str]:
        vec = self._embedder.embed(text)
        # sqlite-vec returns distance (1 - cosine for normalized vectors).
        # We want the nearest neighbour whose event is inside the window.
        # The candidate list is small in practice; LIMIT 1 is enough.
        rows = self._conn.execute(
            """
            SELECT ev.event_id,
                   (1.0 - vi.distance) AS cosine
            FROM vec_index vi
            JOIN event_embeddings ee ON ee.vec_id = vi.rowid
            JOIN events ev ON ev.event_id = ee.event_id
            WHERE vi.embedding MATCH ?
              AND ev.ingested_ts > datetime('now', ?)
              AND ev.status != 'duplicate'
            ORDER BY vi.distance ASC
            LIMIT 1
            """,
            (self._pack(vec), f"-{self._window_hours} hours"),
        ).fetchall()
        if not rows:
            return None
        top = rows[0]
        return top["event_id"] if top["cosine"] >= self._threshold else None

    def record(self, *, text: str, event_id: str) -> int:
        """Insert vector into vec_index + event_embeddings; return vec_id."""
        from tradingagents.persistence.store import insert_event_embedding
        vec = self._embedder.embed(text)
        cur = self._conn.execute(
            "INSERT INTO vec_index (embedding) VALUES (?)", (self._pack(vec),),
        )
        vec_id = cur.lastrowid
        insert_event_embedding(self._conn, event_id=event_id, vec_id=vec_id)
        return vec_id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_dedupe_stage2.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/dedupe.py tests/sensing/test_dedupe_stage2.py
git commit -m "sensing: Stage-2 dedupe (sqlite-vec cosine over 24h window)"
```

---

## Task 11: Ticker validator

**Files:**
- Create: `tradingagents/sensing/ticker_validator.py`
- Test: `tests/sensing/test_ticker_validator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_ticker_validator.py`:

```python
import pytest
from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker


@pytest.fixture
def conn(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)
    upsert_ticker(conn, ticker="TSLA", exchange="NASDAQ",
                  name="Tesla Inc.", aliases=[], active=True)
    upsert_ticker(conn, ticker="DEAD", exchange="NYSE",
                  name="Defunct", aliases=[], active=False)
    return conn


@pytest.mark.unit
def test_validator_keeps_known_drops_unknown(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    kept = v.filter(["AAPL", "NOTREAL", "TSLA"])
    assert kept == ["AAPL", "TSLA"]


@pytest.mark.unit
def test_validator_drops_inactive(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    kept = v.filter(["AAPL", "DEAD"])
    assert kept == ["AAPL"]


@pytest.mark.unit
def test_validator_caches_set(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    _ = v.filter(["AAPL"])
    # Mutate underlying table; validator should not re-query within ttl.
    conn.execute("DELETE FROM tickers WHERE ticker = 'AAPL'")
    conn.commit()
    assert v.filter(["AAPL"]) == ["AAPL"]  # cache still has it


@pytest.mark.unit
def test_validator_refresh_re_reads(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    _ = v.filter(["AAPL"])
    conn.execute("DELETE FROM tickers WHERE ticker = 'AAPL'"); conn.commit()
    v.refresh()
    assert v.filter(["AAPL"]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_ticker_validator.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `ticker_validator.py`**

Create `tradingagents/sensing/ticker_validator.py`:

```python
"""Validate LLM-extracted tickers against the reference table.

Unknown / inactive symbols are dropped — this is the hallucination guard
for D5 of the spec. The reference set is cached in-process; call
`refresh()` to re-read after seeding.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, List, Set


class TickerValidator:
    def __init__(self, *, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cache: Set[str] | None = None

    def refresh(self) -> None:
        """Force re-read on next filter() call."""
        self._cache = None

    def _set(self) -> Set[str]:
        if self._cache is None:
            from tradingagents.persistence.store import get_tickers_set
            self._cache = get_tickers_set(self._conn)
        return self._cache

    def filter(self, tickers: Iterable[str]) -> List[str]:
        ref = self._set()
        # Preserve order; drop unknowns; de-dupe.
        seen: Set[str] = set()
        out: List[str] = []
        for t in tickers:
            t = t.upper().strip()
            if t in ref and t not in seen:
                out.append(t)
                seen.add(t)
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_ticker_validator.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/ticker_validator.py tests/sensing/test_ticker_validator.py
git commit -m "sensing: TickerValidator (reference-table hallucination guard)"
```

---

## Task 12: Salience prompt builder

**Files:**
- Create: `tradingagents/sensing/prompts.py`
- Test: `tests/sensing/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_prompts.py`:

```python
import pytest
from datetime import datetime, timezone

from tradingagents.sensing.envelope import Envelope


def _env(text="Apple beats", source_tags=None):
    return Envelope(
        source="polygon_news",
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id="x:1", text=text,
        source_tags=source_tags or {},
        raw_path="p",
    )


@pytest.mark.unit
def test_prompt_includes_watchlist_csv():
    from tradingagents.sensing.prompts import build_salience_prompt
    text = build_salience_prompt(env=_env(), watchlist=["AAPL", "TSLA"], macro_context="")
    assert "AAPL, TSLA" in text


@pytest.mark.unit
def test_prompt_empty_macro_substituted():
    from tradingagents.sensing.prompts import build_salience_prompt
    text = build_salience_prompt(env=_env(), watchlist=[], macro_context="")
    assert "(none)" in text or "may be empty" in text


@pytest.mark.unit
def test_prompt_truncates_text_to_800():
    from tradingagents.sensing.prompts import build_salience_prompt
    long_text = "x" * 5000
    text = build_salience_prompt(env=_env(text=long_text),
                                  watchlist=["AAPL"], macro_context="")
    # The 800-char clipped text must appear; the 5000-char original must not.
    assert "x" * 800 in text
    assert "x" * 5000 not in text


@pytest.mark.unit
def test_prompt_includes_source_tags_json():
    from tradingagents.sensing.prompts import build_salience_prompt
    env = _env(source_tags={"tickers": ["AAPL"], "category": "earnings"})
    text = build_salience_prompt(env=env, watchlist=[], macro_context="")
    assert '"tickers"' in text and '"AAPL"' in text


@pytest.mark.unit
def test_prompt_documents_anchors():
    from tradingagents.sensing.prompts import build_salience_prompt
    text = build_salience_prompt(env=_env(), watchlist=[], macro_context="")
    # The four anchor bands from §5 of the spec must appear verbatim.
    assert "0.0-0.3" in text
    assert "0.85-1.0" in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_prompts.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `prompts.py`**

Create `tradingagents/sensing/prompts.py`:

```python
"""Salience-LLM prompt construction.

The body matches §5 of the F3 design verbatim; only the substitutions
(watchlist, macro context, envelope fields) are dynamic.
"""

from __future__ import annotations

import json
from typing import Sequence

from .envelope import Envelope


_PROMPT_TEMPLATE = """You are scoring market-relevance for an investment watchlist.

ACTIVE WATCHLIST: {watchlist_csv}
RECENT MACRO CONTEXT (last 4h, may be empty): {macro_context}

EVENT SOURCE: {source}
EVENT TIMESTAMP: {ingested_ts}
EVENT TEXT (first 800 chars): {text}
SOURCE-PROVIDED TICKER TAGS (may be empty): {source_tags}

Return strictly JSON:
{{
  "salience": <float 0.0-1.0>,
  "matched_tickers": [<ticker from watchlist that this materially involves>],
  "mentioned_tickers": [{{"ticker": "<symbol>", "confidence": <float 0-1>}}],
  "reason": "<one sentence>"
}}

Salience anchors:
  0.0-0.3 : routine, no clear watchlist relevance
  0.3-0.6 : context relevant but unlikely to move prices alone
  0.6-0.85: directly relevant to a watchlist instrument
  0.85-1.0: high-impact, time-sensitive, watchlist-relevant
"""


def build_salience_prompt(
    *,
    env: Envelope,
    watchlist: Sequence[str],
    macro_context: str,
) -> str:
    return _PROMPT_TEMPLATE.format(
        watchlist_csv=", ".join(watchlist) if watchlist else "(none)",
        macro_context=macro_context or "(none)",
        source=env.source,
        ingested_ts=env.ingested_ts,
        text=env.text[:800],
        source_tags=json.dumps(env.source_tags),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_prompts.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/prompts.py tests/sensing/test_prompts.py
git commit -m "sensing: salience-LLM prompt builder"
```

---

## Task 13: Salience scorer — LLM call + Redis cache

**Files:**
- Create: `tradingagents/sensing/salience.py`
- Test: `tests/sensing/test_salience.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_salience.py`:

```python
import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.sensing.envelope import Envelope


def _env(text="Apple beats", source="polygon_news"):
    return Envelope(
        source=source,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id="x:1", text=text, source_tags={}, raw_path="p",
    )


@pytest.fixture
def llm_factory():
    """Returns a tuple (factory_callable, call_counter_dict)."""
    counter = {"n": 0}
    def factory(prompt: str) -> str:
        counter["n"] += 1
        return json.dumps({
            "salience": 0.85,
            "matched_tickers": ["AAPL"],
            "mentioned_tickers": [{"ticker": "AAPL", "confidence": 0.95}],
            "reason": "beats consensus",
        })
    return factory, counter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_salience_first_call_invokes_llm(llm_factory):
    from tradingagents.sensing.salience import SalienceScorer
    factory, counter = llm_factory
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = SalienceScorer(redis=r, llm_call=factory, cache_ttl_seconds=86400)
    result = await s.score(env=_env(), watchlist=["AAPL"], macro_context="")
    assert result.salience == pytest.approx(0.85)
    assert counter["n"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_salience_second_call_hits_cache(llm_factory):
    from tradingagents.sensing.salience import SalienceScorer
    factory, counter = llm_factory
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = SalienceScorer(redis=r, llm_call=factory, cache_ttl_seconds=86400)
    env = _env(text="Same text")
    await s.score(env=env, watchlist=["AAPL"], macro_context="")
    await s.score(env=env, watchlist=["AAPL"], macro_context="")
    assert counter["n"] == 1  # cached


@pytest.mark.unit
@pytest.mark.asyncio
async def test_salience_handles_malformed_llm_json():
    from tradingagents.sensing.salience import SalienceScorer
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = SalienceScorer(
        redis=r,
        llm_call=lambda _: "not valid json at all",
        cache_ttl_seconds=86400,
    )
    result = await s.score(env=_env(), watchlist=[], macro_context="")
    # Must not raise; must produce a low-confidence fallback.
    assert 0.0 <= result.salience <= 0.3
    assert result.mentioned_tickers == []
    assert "fallback" in result.reason.lower() or "parse" in result.reason.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_salience.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `salience.py`**

Create `tradingagents/sensing/salience.py`:

```python
"""Salience scoring: cheap-LLM call per event with Redis caching.

The cache key is ``salience:<source>:<sha256(text)[:32]>`` so identical text
across sources still hits separately (different prompts), but re-deliveries
of the exact same source+text envelope are free.

LLM responses are parsed leniently — malformed JSON degrades to a
low-confidence fallback so a flaky model never stalls the pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Sequence

import redis.asyncio as aioredis

from .envelope import Envelope
from .prompts import build_salience_prompt


@dataclass
class MentionedTicker:
    ticker: str
    confidence: float


@dataclass
class SalienceResult:
    salience: float
    matched_tickers: List[str] = field(default_factory=list)
    mentioned_tickers: List[MentionedTicker] = field(default_factory=list)
    reason: str = ""
    source: str = "llm"  # "llm" | "cache" | "fallback"


def _cache_key(env: Envelope) -> str:
    h = hashlib.sha256(env.text.encode("utf-8")).hexdigest()[:32]
    return f"salience:{env.source}:{h}"


def _parse(blob: str) -> SalienceResult:
    data = json.loads(blob)
    return SalienceResult(
        salience=float(data["salience"]),
        matched_tickers=list(data.get("matched_tickers", [])),
        mentioned_tickers=[
            MentionedTicker(ticker=m["ticker"], confidence=float(m["confidence"]))
            for m in data.get("mentioned_tickers", [])
        ],
        reason=str(data.get("reason", "")),
    )


def _serialize(r: SalienceResult) -> str:
    return json.dumps({
        "salience": r.salience,
        "matched_tickers": r.matched_tickers,
        "mentioned_tickers": [
            {"ticker": m.ticker, "confidence": m.confidence}
            for m in r.mentioned_tickers
        ],
        "reason": r.reason,
    })


class SalienceScorer:
    """Wraps any sync/async LLM call. Caches results in Redis."""

    def __init__(
        self,
        *,
        redis: aioredis.Redis,
        llm_call,  # Callable[[str], str | Awaitable[str]]
        cache_ttl_seconds: int,
    ) -> None:
        self._redis = redis
        self._llm = llm_call
        self._ttl = cache_ttl_seconds

    async def _invoke_llm(self, prompt: str) -> str:
        out = self._llm(prompt)
        if hasattr(out, "__await__"):
            out = await out
        return out

    async def score(
        self,
        *,
        env: Envelope,
        watchlist: Sequence[str],
        macro_context: str,
    ) -> SalienceResult:
        key = _cache_key(env)
        cached = await self._redis.get(key)
        if cached:
            result = _parse(cached)
            result.source = "cache"
            return result

        prompt = build_salience_prompt(env=env, watchlist=watchlist,
                                       macro_context=macro_context)
        try:
            raw = await self._invoke_llm(prompt)
            result = _parse(raw)
            result.source = "llm"
        except Exception as e:
            # Don't stall the pipeline — degrade to a fallback that flows through.
            result = SalienceResult(
                salience=0.1, matched_tickers=[], mentioned_tickers=[],
                reason=f"parse-fallback: {type(e).__name__}",
                source="fallback",
            )

        await self._redis.setex(key, self._ttl, _serialize(result))
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_salience.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/salience.py tests/sensing/test_salience.py
git commit -m "sensing: SalienceScorer (LLM + Redis-cached, lenient parsing)"
```

---

## Task 14: Watchlist write paths (user-add + auto-promote + sweep)

**Files:**
- Create: `tradingagents/sensing/watchlist.py`
- Test: `tests/sensing/test_watchlist.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_watchlist.py`:

```python
import json
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_add_user_never_expires(conn):
    from tradingagents.sensing.watchlist import add_user
    add_user(conn, ticker="AAPL")
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='AAPL'").fetchone()
    assert row["ttl_until"] is None
    assert "user" in json.loads(row["tags"])


@pytest.mark.unit
def test_auto_promote_below_threshold_no_op(conn):
    from tradingagents.sensing.watchlist import auto_promote
    n = auto_promote(conn, ticker="NVDA", event_id="e-1",
                     salience=0.5, confidence=0.95,
                     salience_threshold=0.7, confidence_threshold=0.8,
                     ttl_days=7)
    assert n == 0
    assert conn.execute("SELECT 1 FROM watchlist WHERE ticker='NVDA'").fetchone() is None


@pytest.mark.unit
def test_auto_promote_above_threshold_upserts(conn):
    from tradingagents.sensing.watchlist import auto_promote
    n = auto_promote(conn, ticker="NVDA", event_id="e-1",
                     salience=0.9, confidence=0.9,
                     salience_threshold=0.7, confidence_threshold=0.8,
                     ttl_days=7)
    assert n == 1
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='NVDA'").fetchone()
    tags = json.loads(row["tags"])
    assert "auto" in tags
    assert "event:e-1" in tags
    assert row["ttl_until"] is not None


@pytest.mark.unit
def test_auto_promote_does_not_overwrite_user_curated(conn):
    """User entry must remain ttl=None; auto must not steal control of it."""
    from tradingagents.sensing.watchlist import add_user, auto_promote
    add_user(conn, ticker="AAPL")
    auto_promote(conn, ticker="AAPL", event_id="e-2",
                 salience=0.95, confidence=0.95,
                 salience_threshold=0.7, confidence_threshold=0.8,
                 ttl_days=7)
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='AAPL'").fetchone()
    assert row["ttl_until"] is None  # still user-curated
    tags = set(json.loads(row["tags"]))
    assert "user" in tags  # user tag preserved


@pytest.mark.unit
def test_sweep_removes_only_expired_auto(conn):
    from tradingagents.sensing.watchlist import add_user, auto_promote, sweep_expired
    add_user(conn, ticker="AAPL")  # never expires
    auto_promote(conn, ticker="OLD", event_id="e-old",
                 salience=0.9, confidence=0.9,
                 salience_threshold=0.7, confidence_threshold=0.8,
                 ttl_days=7)
    # Manually backdate OLD's ttl_until.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE watchlist SET ttl_until = ? WHERE ticker='OLD'", (past,))
    conn.commit()
    auto_promote(conn, ticker="FRESH", event_id="e-fresh",
                 salience=0.9, confidence=0.9,
                 salience_threshold=0.7, confidence_threshold=0.8,
                 ttl_days=7)
    pruned = sweep_expired(conn)
    rows = [r["ticker"] for r in conn.execute("SELECT ticker FROM watchlist")]
    assert pruned == 1
    assert set(rows) == {"AAPL", "FRESH"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_watchlist.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `watchlist.py`**

Create `tradingagents/sensing/watchlist.py`:

```python
"""Watchlist write paths — user-curated, auto-promote, sweep.

User-curated entries (ttl_until IS NULL) are permanent. Auto-promoted
entries refresh their TTL on every triggering event. The hourly sweep
prunes rows whose TTL has passed *and* are not user-curated.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Iterable


def add_user(
    conn: sqlite3.Connection, *, ticker: str, extra_tags: Iterable[str] = (),
) -> None:
    """User-curated add via CLI. ttl_until=None means never expires."""
    from tradingagents.persistence.store import upsert_watchlist
    tags = ["user", *extra_tags]
    upsert_watchlist(conn, ticker=ticker, ttl_until=None, tags=tags)


def auto_promote(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    event_id: str,
    salience: float,
    confidence: float,
    salience_threshold: float,
    confidence_threshold: float,
    ttl_days: int,
) -> int:
    """Promote a ticker if it clears both thresholds. Returns 1 if upserted, 0 otherwise.

    A pre-existing user-curated entry is NOT overwritten — only its
    ``last_briefed`` timestamp advances (via the upsert helper).
    """
    if salience < salience_threshold or confidence < confidence_threshold:
        return 0

    from tradingagents.persistence.store import upsert_watchlist

    existing = conn.execute(
        "SELECT tags FROM watchlist WHERE ticker = ?", (ticker,)
    ).fetchone()
    user_curated = (
        existing is not None
        and "user" in (json.loads(existing["tags"]) if existing["tags"] else [])
    )
    if user_curated:
        # Refresh last_briefed only; keep ttl_until = NULL.
        upsert_watchlist(conn, ticker=ticker, ttl_until=None,
                         tags=["user", f"event:{event_id}"])
        return 0

    ttl_until = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    upsert_watchlist(
        conn, ticker=ticker, ttl_until=ttl_until,
        tags=["auto", f"event:{event_id}"],
    )
    return 1


def sweep_expired(conn: sqlite3.Connection) -> int:
    """Delete expired auto-rows. Returns the row count removed.

    User-curated entries (ttl_until IS NULL OR tags ∋ 'user') are preserved.
    """
    cur = conn.execute(
        "DELETE FROM watchlist "
        "WHERE ttl_until IS NOT NULL "
        "  AND ttl_until < datetime('now') "
        "  AND tags NOT LIKE '%\"user\"%'"
    )
    conn.commit()
    return cur.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_watchlist.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/watchlist.py tests/sensing/test_watchlist.py
git commit -m "sensing: watchlist add_user / auto_promote / sweep_expired"
```

---

## Task 15: Tickers seed — Polygon + crypto YAML

**Files:**
- Create: `tradingagents/sensing/seed_tickers.py`
- Create: `tradingagents/sensing/data/crypto_universe.yaml`
- Test: `tests/sensing/test_seed_tickers.py`

- [ ] **Step 1: Create the crypto YAML**

Create `tradingagents/sensing/data/crypto_universe.yaml`:

```yaml
# Top-20 crypto static reference. Maintained manually; re-evaluate quarterly.
# Format: list of {ticker, name, aliases}. Exchange is always "CRYPTO".
- ticker: BTC-USD
  name: Bitcoin
  aliases: [BTC, Bitcoin]
- ticker: ETH-USD
  name: Ethereum
  aliases: [ETH, Ether, Ethereum]
- ticker: USDT-USD
  name: Tether
  aliases: [USDT, Tether]
- ticker: BNB-USD
  name: BNB
  aliases: [BNB, Binance Coin]
- ticker: SOL-USD
  name: Solana
  aliases: [SOL, Solana]
- ticker: USDC-USD
  name: USD Coin
  aliases: [USDC]
- ticker: XRP-USD
  name: XRP
  aliases: [XRP, Ripple]
- ticker: DOGE-USD
  name: Dogecoin
  aliases: [DOGE, Dogecoin]
- ticker: ADA-USD
  name: Cardano
  aliases: [ADA, Cardano]
- ticker: TRX-USD
  name: TRON
  aliases: [TRX, TRON]
- ticker: AVAX-USD
  name: Avalanche
  aliases: [AVAX, Avalanche]
- ticker: TON-USD
  name: Toncoin
  aliases: [TON, Toncoin]
- ticker: SHIB-USD
  name: Shiba Inu
  aliases: [SHIB]
- ticker: LINK-USD
  name: Chainlink
  aliases: [LINK, Chainlink]
- ticker: DOT-USD
  name: Polkadot
  aliases: [DOT, Polkadot]
- ticker: BCH-USD
  name: Bitcoin Cash
  aliases: [BCH]
- ticker: MATIC-USD
  name: Polygon
  aliases: [MATIC, Polygon network]
- ticker: NEAR-USD
  name: NEAR Protocol
  aliases: [NEAR]
- ticker: LTC-USD
  name: Litecoin
  aliases: [LTC, Litecoin]
- ticker: UNI-USD
  name: Uniswap
  aliases: [UNI, Uniswap]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/sensing/test_seed_tickers.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_seed_crypto_universe(conn):
    from tradingagents.sensing.seed_tickers import seed_crypto
    n = seed_crypto(conn)
    assert n == 20
    btc = conn.execute("SELECT * FROM tickers WHERE ticker='BTC-USD'").fetchone()
    assert btc["exchange"] == "CRYPTO"
    assert btc["active"] == 1
    import json as _j
    assert "BTC" in _j.loads(btc["aliases"])


@pytest.mark.unit
def test_seed_polygon_paginated(conn, monkeypatch):
    from tradingagents.sensing import seed_tickers
    pages = [
        {"results": [
            {"ticker": "AAPL", "name": "Apple Inc.", "primary_exchange": "XNAS",
             "active": True}],
         "next_url": "https://api.polygon.io/v3/reference/tickers?cursor=2"},
        {"results": [
            {"ticker": "TSLA", "name": "Tesla Inc.", "primary_exchange": "XNAS",
             "active": True}],
         "next_url": None},
    ]
    calls = {"n": 0}
    def fake_get(url, **_):
        idx = calls["n"]
        calls["n"] += 1
        m = MagicMock(); m.json.return_value = pages[idx]; m.status_code = 200
        m.raise_for_status = lambda: None
        return m
    monkeypatch.setattr(seed_tickers.requests, "get", fake_get)
    monkeypatch.setenv("POLYGON_API_KEY", "fake")

    n = seed_tickers.seed_polygon(conn)
    assert n == 2
    rows = {r["ticker"] for r in conn.execute(
        "SELECT ticker FROM tickers WHERE exchange != 'CRYPTO'"
    )}
    assert rows == {"AAPL", "TSLA"}


@pytest.mark.unit
def test_seed_polygon_missing_key_raises(conn, monkeypatch):
    from tradingagents.sensing.seed_tickers import seed_polygon
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="POLYGON_API_KEY"):
        seed_polygon(conn)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/sensing/test_seed_tickers.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `seed_tickers.py`**

Create `tradingagents/sensing/seed_tickers.py`:

```python
"""Seed the `tickers` reference table.

Two sources:
  - Polygon /v3/reference/tickers (paginated, free on dev tier) for US equities.
  - tradingagents/sensing/data/crypto_universe.yaml for top-20 crypto.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

import requests
import yaml

from tradingagents.persistence.store import upsert_ticker


_POLYGON_BASE = "https://api.polygon.io/v3/reference/tickers"


# Polygon exchange mics → our short labels.
_EXCHANGE_MAP = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
    "ARCX": "ARCA",
    "BATS": "BATS",
}


def _crypto_path() -> Path:
    return Path(__file__).parent / "data" / "crypto_universe.yaml"


def seed_crypto(conn: sqlite3.Connection) -> int:
    """Upsert all crypto entries from the static YAML. Returns row count."""
    items = yaml.safe_load(_crypto_path().read_text())
    n = 0
    for item in items:
        upsert_ticker(
            conn,
            ticker=item["ticker"],
            exchange="CRYPTO",
            name=item["name"],
            aliases=item.get("aliases", []),
            active=True,
        )
        n += 1
    return n


def seed_polygon(conn: sqlite3.Connection, *, market: str = "stocks") -> int:
    """Walk the paginated Polygon reference endpoint. Returns row count."""
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY required for seed_polygon()")
    url = f"{_POLYGON_BASE}?market={market}&active=true&limit=1000"
    n = 0
    while url:
        r = requests.get(url, params={"apiKey": api_key}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("results", []):
            exch_mic = item.get("primary_exchange", "")
            upsert_ticker(
                conn,
                ticker=item["ticker"],
                exchange=_EXCHANGE_MAP.get(exch_mic, exch_mic or "UNKNOWN"),
                name=item.get("name", ""),
                aliases=[],
                active=bool(item.get("active", True)),
            )
            n += 1
        next_url = data.get("next_url")
        url = next_url if next_url else None
    return n


def seed_all(conn: sqlite3.Connection) -> dict:
    """Seed both. Returns {'crypto': n, 'polygon': n}."""
    return {
        "crypto": seed_crypto(conn),
        "polygon": seed_polygon(conn),
    }
```

- [ ] **Step 5: Verify `pyyaml` is in deps**

```bash
grep -n "pyyaml\|PyYAML" pyproject.toml
```

Expected: matches `pyyaml>=6.0` (already a core dep — confirmed in Task 2 inspection).

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/sensing/test_seed_tickers.py -v
```

Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/sensing/seed_tickers.py tradingagents/sensing/data/crypto_universe.yaml tests/sensing/test_seed_tickers.py
git commit -m "sensing: tickers seed (Polygon paginated + crypto YAML)"
```

---


## Task 16: IngestAdapter Protocol + EnvelopeWriter

**Files:**
- Create: `tradingagents/sensing/adapters/__init__.py`
- Create: `tradingagents/sensing/adapters/base.py`
- Test: `tests/sensing/test_adapter_base.py`

- [ ] **Step 1: Create the package marker**

Create `tradingagents/sensing/adapters/__init__.py` with:

```python
"""IIC-FORGE F3 ingestion adapters. One module per source."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/sensing/test_adapter_base.py`:

```python
import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.sensing.envelope import Envelope


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_envelope_writer_xadds_and_advances_cursor(conn, tmp_path):
    from tradingagents.sensing.adapters.base import EnvelopeWriter
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    w = EnvelopeWriter(source="polygon_news", redis=r, conn=conn,
                        stream="ingest:raw", staging_root=str(tmp_path / "staging"))
    env = Envelope(
        source="polygon_news",
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id="pn:1", text="Apple beats", source_tags={},
        raw_path="",  # writer fills this
    )
    await w.write(env, raw_payload={"foo": "bar"}, cursor="2026-05-26T00:00:00Z")
    entries = await r.xrange("ingest:raw")
    assert len(entries) == 1
    _, fields = entries[0]
    data = json.loads(fields["data"])
    assert data["source"] == "polygon_news"
    assert data["raw_path"].endswith(".json")
    # Cursor saved.
    row = conn.execute("SELECT cursor FROM ingest_cursor WHERE source='polygon_news'").fetchone()
    assert row["cursor"] == "2026-05-26T00:00:00Z"
    # Raw file on disk.
    from pathlib import Path
    assert Path(data["raw_path"]).exists()


@pytest.mark.unit
def test_ingest_adapter_protocol_has_name_and_stream():
    from tradingagents.sensing.adapters.base import IngestAdapter
    # Protocol must list `name: str` and `stream(...)` async method.
    annotations = IngestAdapter.__annotations__
    assert "name" in annotations
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_base.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `base.py`**

Create `tradingagents/sensing/adapters/base.py`:

```python
"""Adapter contract + shared envelope-writing helper.

All adapters import EnvelopeWriter; the Protocol exists for documentation
and type-checking but is not strictly enforced at runtime.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import redis.asyncio as aioredis

from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


class IngestAdapter(Protocol):
    name: str  # "polygon_news", "telegram", ...

    async def stream(self, redis: aioredis.Redis, conn: sqlite3.Connection) -> None:
        """Long-lived. Reads from the source, writes envelopes to Redis,
        persists cursor after every successful batch. Defensively retry-internal."""


@dataclass
class EnvelopeWriter:
    """Writes raw payload to disk, XADDs envelope, advances cursor — atomically enough.

    The order is: write raw file → XADD envelope → set cursor. A crash between
    XADD and set-cursor results in the next adapter run re-fetching from the
    old cursor; the dedup pipeline tolerates the resulting re-deliveries.
    """
    source: str
    redis: aioredis.Redis
    conn: sqlite3.Connection
    stream: str
    staging_root: str

    def __post_init__(self) -> None:
        self._cursor = CursorStore(self.conn)
        Path(self.staging_root).mkdir(parents=True, exist_ok=True)

    def _write_raw(self, payload: dict) -> str:
        from datetime import datetime, timezone
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_dir = Path(self.staging_root) / day
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    async def write(
        self,
        env: Envelope,
        *,
        raw_payload: dict,
        cursor: str,
    ) -> None:
        raw_path = self._write_raw(raw_payload)
        # Envelope dataclass is frozen — rebuild with the real raw_path.
        env_with_path = Envelope(
            source=env.source, ingested_ts=env.ingested_ts,
            external_id=env.external_id, text=env.text,
            source_tags=env.source_tags, raw_path=raw_path,
        )
        await self.redis.xadd(self.stream, env_with_path.to_redis_fields())
        self._cursor.set(self.source, cursor)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_base.py -v
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/sensing/adapters/__init__.py tradingagents/sensing/adapters/base.py tests/sensing/test_adapter_base.py
git commit -m "sensing(adapters): IngestAdapter Protocol + EnvelopeWriter helper"
```

---

## Task 17: Polygon news adapter

**Files:**
- Create: `tradingagents/sensing/adapters/polygon_news.py`
- Test: `tests/sensing/test_adapter_polygon_news.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_adapter_polygon_news.py`:

```python
import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_polygon_news_emits_envelope(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.polygon_news import PolygonNewsAdapter
    monkeypatch.setenv("POLYGON_API_KEY", "fake")
    payload = {
        "results": [{
            "id": "pn-1",
            "title": "Apple beats consensus",
            "description": "Q3 earnings strong",
            "tickers": ["AAPL"],
            "published_utc": "2026-05-26T14:30:00Z",
        }],
        "next_url": None,
    }
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.polygon_news.requests.get",
               return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = PolygonNewsAdapter(staging_root=str(tmp_path / "staging"),
                                stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
        assert n == 1

    entries = await r.xrange("ingest:raw")
    _, fields = entries[0]
    env = json.loads(fields["data"])
    assert env["source"] == "polygon_news"
    assert env["external_id"] == "pn:pn-1"
    assert "Apple beats" in env["text"]
    assert env["source_tags"]["tickers"] == ["AAPL"]
    # Cursor advanced.
    cur = conn.execute("SELECT cursor FROM ingest_cursor "
                       "WHERE source='polygon_news'").fetchone()
    assert cur["cursor"] == "2026-05-26T14:30:00Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_polygon_news_skips_when_cursor_unchanged(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.polygon_news import PolygonNewsAdapter
    from tradingagents.sensing.cursor import CursorStore
    CursorStore(conn).set("polygon_news", "2026-05-26T15:00:00Z")
    monkeypatch.setenv("POLYGON_API_KEY", "fake")
    payload = {"results": [{
        "id": "pn-1", "title": "old", "description": "older",
        "tickers": [], "published_utc": "2026-05-26T14:00:00Z",
    }], "next_url": None}
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.polygon_news.requests.get",
               return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = PolygonNewsAdapter(staging_root=str(tmp_path / "staging"),
                                stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n == 0  # older than cursor → skipped
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_polygon_news.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `polygon_news.py`**

Create `tradingagents/sensing/adapters/polygon_news.py`:

```python
"""Polygon news adapter — REST poll every 60s.

Cursor: last-seen ``published_utc`` (ISO-8601 string). On each poll we
request items > cursor; if a poll returns nothing newer we just sleep
for the next interval.

Defensive: catches all requests errors; never raises out of stream().
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict

import redis.asyncio as aioredis
import requests

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "polygon_news"
POLL_INTERVAL = 60  # seconds
MAX_CURSOR_LAG_HOURS = 6  # if last cursor older than this, resume from now-N


class PolygonNewsAdapter:
    name = NAME

    def __init__(self, *, staging_root: str, stream: str) -> None:
        self._staging = staging_root
        self._stream = stream

    def _api_key(self) -> str:
        k = os.environ.get("POLYGON_API_KEY")
        if not k:
            raise RuntimeError("POLYGON_API_KEY not set")
        return k

    def _resume_cursor(self, conn: sqlite3.Connection) -> str:
        cs = CursorStore(conn)
        existing = cs.get(NAME)
        if existing:
            return existing
        # Initial: backfill from "now minus 1 hour" to avoid a flood.
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        """One iteration of the loop. Returns # of envelopes emitted."""
        cursor = self._resume_cursor(conn)
        try:
            r = requests.get(
                "https://api.polygon.io/v2/reference/news",
                params={
                    "apiKey": self._api_key(),
                    "order": "asc",
                    "sort": "published_utc",
                    "published_utc.gt": cursor,
                    "limit": 100,
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("polygon poll failed (will retry): %s", e)
            return 0

        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        new_cursor = cursor
        for item in data.get("results", []):
            published = item.get("published_utc", "")
            if not published or published <= cursor:
                continue
            ext_id = f"pn:{item.get('id', '')}"
            text = " ".join(filter(None, [item.get("title", ""), item.get("description", "")]))
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=ext_id, text=text,
                source_tags={"tickers": item.get("tickers", []),
                             "publisher": (item.get("publisher") or {}).get("name", "")},
                raw_path="",
            )
            await writer.write(env, raw_payload=item, cursor=published)
            emitted += 1
            new_cursor = published
        return emitted

    async def stream(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn)
                backoff = 1
            except Exception:
                log.exception("polygon stream iteration crashed; backing off")
                backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    """Systemd entry point."""
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s adapter disabled by config; exiting 0", NAME)
        return
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = PolygonNewsAdapter(staging_root=staging, stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_polygon_news.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/adapters/polygon_news.py tests/sensing/test_adapter_polygon_news.py
git commit -m "sensing(adapters): polygon_news REST poller (60s, defensive)"
```

---

## Task 18: RSS adapter

**Files:**
- Create: `tradingagents/sensing/adapters/rss.py`
- Test: `tests/sensing/test_adapter_rss.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_adapter_rss.py`:

```python
import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


def _feed_with_entries(*titles):
    f = MagicMock()
    f.entries = []
    for i, t in enumerate(titles):
        e = MagicMock()
        e.id = f"rss:e:{i}"
        e.title = t
        e.summary = "body"
        e.link = f"https://x/{i}"
        e.published_parsed = (2026, 5, 26, 12, 0, i, 0, 0, 0)  # struct_time
        f.entries.append(e)
    return f


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rss_polls_each_feed(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters import rss as rss_mod
    parse_calls = []
    def fake_parse(url):
        parse_calls.append(url)
        return _feed_with_entries(f"entry from {url}")
    monkeypatch.setattr(rss_mod.feedparser, "parse", fake_parse)
    a = rss_mod.RssAdapter(
        feeds=["https://a/rss", "https://b/rss"],
        staging_root=str(tmp_path / "s"),
        stream="ingest:raw",
    )
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    n = await a.poll_once(redis=r, conn=conn)
    assert n == 2
    assert sorted(parse_calls) == ["https://a/rss", "https://b/rss"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rss_per_feed_cursor(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters import rss as rss_mod
    monkeypatch.setattr(rss_mod.feedparser, "parse",
                        lambda url: _feed_with_entries("only one"))
    a = rss_mod.RssAdapter(
        feeds=["https://feed-a/rss"],
        staging_root=str(tmp_path / "s"),
        stream="ingest:raw",
    )
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await a.poll_once(redis=r, conn=conn)
    row = conn.execute("SELECT cursor FROM ingest_cursor WHERE source='rss'").fetchone()
    # Per-feed cursors are stored as JSON keyed by feed URL.
    d = json.loads(row["cursor"])
    assert "https://feed-a/rss" in d


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rss_skips_entries_at_or_before_cursor(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters import rss as rss_mod
    monkeypatch.setattr(rss_mod.feedparser, "parse",
                        lambda url: _feed_with_entries("e1"))
    a = rss_mod.RssAdapter(
        feeds=["https://f/rss"],
        staging_root=str(tmp_path / "s"),
        stream="ingest:raw",
    )
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    n1 = await a.poll_once(redis=r, conn=conn)
    n2 = await a.poll_once(redis=r, conn=conn)
    assert n1 == 1 and n2 == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_rss.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `rss.py`**

Create `tradingagents/sensing/adapters/rss.py`:

```python
"""RSS adapter — feedparser per feed, 5-min interval, per-feed cursors.

Cursor format: JSON dict mapping feed_url → max published ISO timestamp.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import List

import feedparser
import redis.asyncio as aioredis

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "rss"
POLL_INTERVAL = 5 * 60


def _entry_ts(entry) -> str:
    if getattr(entry, "published_parsed", None):
        dt = datetime.fromtimestamp(time.mktime(entry.published_parsed),
                                     tz=timezone.utc)
        return dt.isoformat()
    return datetime.now(timezone.utc).isoformat()


class RssAdapter:
    name = NAME

    def __init__(self, *, feeds: List[str], staging_root: str, stream: str) -> None:
        self._feeds = list(feeds)
        self._staging = staging_root
        self._stream = stream

    def _load_cursor(self, conn) -> dict:
        cs = CursorStore(conn)
        raw = cs.get(NAME)
        return json.loads(raw) if raw else {}

    def _save_cursor(self, conn, d: dict) -> None:
        CursorStore(conn).set(NAME, json.dumps(d))

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        cursors = self._load_cursor(conn)
        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        for feed_url in self._feeds:
            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                log.warning("rss parse failed for %s: %s", feed_url, e)
                continue
            last = cursors.get(feed_url, "")
            new_last = last
            for entry in feed.entries:
                ts = _entry_ts(entry)
                if last and ts <= last:
                    continue
                ext_id = f"rss:{getattr(entry, 'id', getattr(entry, 'link', ''))}"
                text = " ".join(filter(None, [
                    getattr(entry, "title", ""),
                    getattr(entry, "summary", ""),
                ]))
                env = Envelope(
                    source=NAME,
                    ingested_ts=datetime.now(timezone.utc).isoformat(),
                    external_id=ext_id, text=text,
                    source_tags={"feed": feed_url,
                                 "link": getattr(entry, "link", "")},
                    raw_path="",
                )
                # Per-entry cursor is the feed-level dict, JSON-encoded.
                cursors[feed_url] = ts
                await writer.write(
                    env,
                    raw_payload={
                        "title": getattr(entry, "title", ""),
                        "summary": getattr(entry, "summary", ""),
                        "link": getattr(entry, "link", ""),
                        "published_ts": ts,
                    },
                    cursor=json.dumps(cursors),
                )
                emitted += 1
                new_last = ts
            cursors[feed_url] = max(new_last, last) if last else new_last
        self._save_cursor(conn, cursors)
        return emitted

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn)
                backoff = 1
            except Exception:
                log.exception("rss stream iteration crashed")
                backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    import os
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return
    feeds = [f.strip() for f in os.environ.get("RSS_FEEDS", "").split(",") if f.strip()]
    if not feeds:
        log.warning("RSS_FEEDS env var not set; no feeds to poll")
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = RssAdapter(feeds=feeds, staging_root=staging,
                    stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_rss.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/adapters/rss.py tests/sensing/test_adapter_rss.py
git commit -m "sensing(adapters): rss (feedparser, per-feed cursors)"
```

---

## Task 19: GDELT adapter

**Files:**
- Create: `tradingagents/sensing/adapters/gdelt.py`
- Test: `tests/sensing/test_adapter_gdelt.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_adapter_gdelt.py`:

```python
import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gdelt_emits_envelope(conn, tmp_path):
    from tradingagents.sensing.adapters.gdelt import GdeltAdapter
    payload = {
        "articles": [{
            "url": "https://news.example/g-1",
            "title": "Macro shock",
            "seendate": "20260526T140000Z",
            "domain": "news.example",
        }],
    }
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.gdelt.requests.get", return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = GdeltAdapter(query="earnings", staging_root=str(tmp_path / "s"),
                          stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n == 1
    entries = await r.xrange("ingest:raw")
    env = json.loads(entries[0][1]["data"])
    assert env["source"] == "gdelt"
    assert env["external_id"] == "gdelt:https://news.example/g-1"
    assert "Macro shock" in env["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_gdelt.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `gdelt.py`**

Create `tradingagents/sensing/adapters/gdelt.py`:

```python
"""GDELT 2.0 doc API adapter — 15-min poll."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
import requests

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "gdelt"
POLL_INTERVAL = 15 * 60


class GdeltAdapter:
    name = NAME

    def __init__(self, *, query: str, staging_root: str, stream: str) -> None:
        self._query = query
        self._staging = staging_root
        self._stream = stream

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        cs = CursorStore(conn)
        last_seen = cs.get(NAME) or ""
        try:
            r = requests.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": self._query,
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": 250,
                    "sort": "DateAsc",
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("gdelt poll failed: %s", e); return 0

        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        new_cursor = last_seen
        for art in data.get("articles", []):
            seen = art.get("seendate", "")
            if last_seen and seen <= last_seen:
                continue
            url = art.get("url", "")
            ext_id = f"gdelt:{url}"
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=ext_id,
                text=art.get("title", ""),
                source_tags={"domain": art.get("domain", ""), "url": url,
                             "seendate": seen},
                raw_path="",
            )
            await writer.write(env, raw_payload=art, cursor=seen)
            emitted += 1
            new_cursor = max(seen, new_cursor)
        return emitted

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn); backoff = 1
            except Exception:
                log.exception("gdelt iteration crashed"); backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    import os
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return
    query = os.environ.get("GDELT_QUERY", "earnings OR \"federal reserve\" OR M&A")
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = GdeltAdapter(query=query, staging_root=staging,
                      stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_gdelt.py -v
```

Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/adapters/gdelt.py tests/sensing/test_adapter_gdelt.py
git commit -m "sensing(adapters): gdelt doc API (15-min poll)"
```

---

## Task 20: Macro adapter (FRED + TradingEconomics)

**Files:**
- Create: `tradingagents/sensing/adapters/macro.py`
- Test: `tests/sensing/test_adapter_macro.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_adapter_macro.py`:

```python
import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_macro_fred_emits_release(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.macro import MacroAdapter
    monkeypatch.setenv("FRED_API_KEY", "fake")
    payload = {
        "releases": [{
            "id": 9, "name": "Employment Situation",
            "press_release": True, "link": "https://x",
            "realtime_start": "2026-05-26"}],
    }
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.macro.requests.get", return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = MacroAdapter(staging_root=str(tmp_path / "s"), stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n >= 1
    entries = await r.xrange("ingest:raw")
    env = json.loads(entries[0][1]["data"])
    assert env["source"] == "macro"
    assert "Employment Situation" in env["text"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_macro_skips_when_fred_key_missing(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.macro import MacroAdapter
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a = MacroAdapter(staging_root=str(tmp_path / "s"), stream="ingest:raw")
    n = await a.poll_once(redis=r, conn=conn)
    assert n == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_macro.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `macro.py`**

Create `tradingagents/sensing/adapters/macro.py`:

```python
"""Macro releases adapter — FRED releases (primary) + TradingEconomics calendar (secondary).

Open question O5 in the spec: default to FRED-primary; TE is skipped
unless TRADINGECONOMICS_KEY is set.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone

import redis.asyncio as aioredis
import requests

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "macro"
POLL_INTERVAL = 30 * 60


class MacroAdapter:
    name = NAME

    def __init__(self, *, staging_root: str, stream: str) -> None:
        self._staging = staging_root
        self._stream = stream

    async def _poll_fred(self, redis, conn, writer) -> int:
        key = os.environ.get("FRED_API_KEY")
        if not key:
            return 0
        try:
            r = requests.get(
                "https://api.stlouisfed.org/fred/releases",
                params={"api_key": key, "file_type": "json", "limit": 100,
                        "order_by": "release_id", "sort_order": "desc"},
                timeout=20,
            )
            r.raise_for_status(); data = r.json()
        except Exception as e:
            log.warning("FRED poll failed: %s", e); return 0
        cs = CursorStore(conn)
        last_id = int(cs.get(NAME) or "0")
        emitted = 0
        new_max = last_id
        for rel in data.get("releases", []):
            rid = int(rel.get("id", 0))
            if rid <= last_id:
                continue
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=f"fred:{rid}",
                text=rel.get("name", ""),
                source_tags={"provider": "fred", "release_id": rid,
                             "link": rel.get("link", "")},
                raw_path="",
            )
            await writer.write(env, raw_payload=rel, cursor=str(rid))
            emitted += 1
            new_max = max(new_max, rid)
        return emitted

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        n = await self._poll_fred(redis, conn, writer)
        # TE is intentionally a no-op until TRADINGECONOMICS_KEY ships.
        return n

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn); backoff = 1
            except Exception:
                log.exception("macro iteration crashed"); backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = MacroAdapter(staging_root=staging, stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_macro.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/adapters/macro.py tests/sensing/test_adapter_macro.py
git commit -m "sensing(adapters): macro (FRED releases primary; TE deferred)"
```

---

## Task 21: F0 telegram stub — real Telethon iter_messages

**Files:**
- Modify: `tradingagents/dataflows/telegram_osint.py`
- Test: `tests/test_telegram_osint_impl.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_telegram_osint_impl.py`:

```python
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_get_telegram_signals_raises_when_creds_missing(monkeypatch):
    from tradingagents.dataflows.telegram_osint import get_telegram_signals
    from tradingagents.dataflows.errors import DataVendorError
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    with pytest.raises(DataVendorError, match="creds"):
        get_telegram_signals("AAPL", "2026-05-01", "2026-05-26")


@pytest.mark.unit
def test_get_telegram_signals_uses_osint_session(monkeypatch):
    from tradingagents.dataflows import telegram_osint as mod
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "deadbeef")
    monkeypatch.setenv("TELEGRAM_OSINT_SESSION", "/tmp/iic_osint.session")

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.iter_messages.return_value = iter([])

    with patch.object(mod, "TelegramClient", return_value=fake_client) as ctor:
        out = mod.get_telegram_signals("AAPL", "2026-05-01", "2026-05-26")
    # Constructor called with the OSINT session path, not the SENSING session.
    args, kwargs = ctor.call_args
    assert "iic_osint.session" in args[0]
    # Output is a string digest (may be "(no matches)" when iter is empty).
    assert isinstance(out, str)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_telegram_osint_impl.py -v
```

Expected: FAIL — function still raises "implementation pending".

- [ ] **Step 3: Replace the stub body in `tradingagents/dataflows/telegram_osint.py`**

Replace the entire file with:

```python
"""Telegram OSINT vendor — sentiment/news source, pull-style.

Uses Telethon ``iter_messages`` against the configured ``telegram_channels``
list. F3's *streaming* adapter uses a separate session (TELEGRAM_SENSING_SESSION)
to avoid Telethon's "second connection on the same session" auth kick.

Required env: ``TELEGRAM_API_ID``, ``TELEGRAM_API_HASH``, optional
``TELEGRAM_OSINT_SESSION`` (default ``iic_osint.session``).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List

from .errors import DataVendorError

try:
    from telethon.sync import TelegramClient
except Exception:  # pragma: no cover — optional dep
    TelegramClient = None  # type: ignore


def _parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def get_telegram_signals(query: str, start_date: str, end_date: str) -> str:
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        raise DataVendorError(
            "Telegram API creds (TELEGRAM_API_ID/TELEGRAM_API_HASH) not set"
        )
    if TelegramClient is None:
        raise DataVendorError("telethon not installed; pip install -e .[osint]")
    session = os.environ.get("TELEGRAM_OSINT_SESSION", "iic_osint.session")

    from tradingagents.default_config import DEFAULT_CONFIG
    channels: List[str] = list(DEFAULT_CONFIG.get("telegram_channels") or [])
    if not channels:
        return f"(no telegram_channels configured for query={query!r})"

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    matches: List[str] = []
    with TelegramClient(session, int(api_id), api_hash) as client:
        for ch in channels:
            try:
                for msg in client.iter_messages(ch, limit=200):
                    if msg.date is None or not (start <= msg.date <= end):
                        continue
                    text = (msg.message or "").strip()
                    if not text:
                        continue
                    if query.lower() in text.lower():
                        matches.append(f"- [{ch} @ {msg.date.isoformat()}]: {text[:300]}")
            except Exception as e:
                matches.append(f"- ({ch} fetch failed: {e})")
    if not matches:
        return f"(no matches for {query!r} across {len(channels)} channels)"
    header = f"## Telegram OSINT — {query} [{start_date} … {end_date}]\n"
    return header + "\n".join(matches[:50])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_telegram_osint_impl.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/telegram_osint.py tests/test_telegram_osint_impl.py
git commit -m "dataflows(telegram_osint): real iter_messages impl; OSINT-session env"
```

---

## Task 22: Telegram sensing adapter (streaming, separate session)

**Files:**
- Create: `tradingagents/sensing/adapters/telegram.py`
- Test: `tests/sensing/test_adapter_telegram.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_adapter_telegram.py`:

```python
import json
import pytest
import fakeredis.aioredis
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_telegram_handler_emits_envelope(conn, tmp_path):
    from tradingagents.sensing.adapters.telegram import _on_message
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Fake Telethon NewMessage event.
    ev = MagicMock()
    ev.message.id = 42
    ev.message.message = "Apple breaks above resistance"
    ev.message.date.isoformat.return_value = "2026-05-26T12:00:00+00:00"
    ev.chat.username = "iic_signals"

    await _on_message(ev, redis=r, conn=conn,
                      stream="ingest:raw",
                      staging_root=str(tmp_path / "s"))

    entries = await r.xrange("ingest:raw")
    assert len(entries) == 1
    env = json.loads(entries[0][1]["data"])
    assert env["source"] == "telegram"
    assert env["external_id"] == "tg:iic_signals:42"
    assert "Apple breaks above resistance" in env["text"]
    # Cursor advanced for this channel.
    cur = conn.execute("SELECT cursor FROM ingest_cursor WHERE source='telegram'").fetchone()
    d = json.loads(cur["cursor"])
    assert d.get("iic_signals") == 42


@pytest.mark.unit
@pytest.mark.asyncio
async def test_telegram_handler_skips_empty_messages(conn, tmp_path):
    from tradingagents.sensing.adapters.telegram import _on_message
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ev = MagicMock()
    ev.message.id = 1
    ev.message.message = "   "  # whitespace-only
    ev.message.date.isoformat.return_value = "2026-05-26T12:00:00+00:00"
    ev.chat.username = "iic"
    await _on_message(ev, redis=r, conn=conn,
                      stream="ingest:raw",
                      staging_root=str(tmp_path / "s"))
    assert await r.xlen("ingest:raw") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_telegram.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `telegram.py`**

Create `tradingagents/sensing/adapters/telegram.py`:

```python
"""Telegram sensing adapter — Telethon NewMessage streaming.

Uses a SEPARATE session from the F0 OSINT pull path. Two session files
exist because Telethon kicks a second concurrent connection on the same
session.

Cursor: JSON dict mapping channel username → max message_id seen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import List

import redis.asyncio as aioredis

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "telegram"


async def _on_message(event, *, redis, conn, stream: str, staging_root: str) -> None:
    msg = event.message
    text = (msg.message or "").strip()
    if not text:
        return
    channel = getattr(event.chat, "username", None) or "unknown"
    cs = CursorStore(conn)
    cursors = json.loads(cs.get(NAME) or "{}")
    cursors[channel] = max(int(cursors.get(channel, 0)), int(msg.id))
    env = Envelope(
        source=NAME,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id=f"tg:{channel}:{msg.id}",
        text=text,
        source_tags={"channel": channel,
                     "msg_date": msg.date.isoformat()},
        raw_path="",
    )
    writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                             stream=stream, staging_root=staging_root)
    await writer.write(env, raw_payload={"channel": channel,
                                          "message_id": msg.id,
                                          "text": text},
                       cursor=json.dumps(cursors))


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        log.error("TELEGRAM_API_ID/HASH not set; exiting 1")
        raise SystemExit(1)
    session = os.environ.get("TELEGRAM_SENSING_SESSION", "iic_sensing.session")

    from telethon import TelegramClient, events  # lazy import

    channels: List[str] = list(C.get("telegram_channels") or [])
    if not channels:
        log.warning("telegram_channels config empty; nothing to listen to")

    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")

    client = TelegramClient(session, int(api_id), api_hash)

    @client.on(events.NewMessage(chats=channels))
    async def handler(event):
        try:
            await _on_message(event, redis=redis, conn=conn,
                              stream=C["sensing_ingest_stream"],
                              staging_root=staging)
        except Exception:
            log.exception("telegram handler crashed (event dropped, will continue)")

    log.info("telegram sensing adapter started; channels=%s", channels)
    client.start()  # interactive prompt only if session is brand-new
    client.run_until_disconnected()


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_telegram.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/adapters/telegram.py tests/sensing/test_adapter_telegram.py
git commit -m "sensing(adapters): telegram streaming (Telethon NewMessage, separate session)"
```

---

## Task 23: X (Twitter) adapter

**Files:**
- Create: `tradingagents/sensing/adapters/x.py`
- Test: `tests/sensing/test_adapter_x.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_adapter_x.py`:

```python
import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_x_emits_envelope_for_each_tweet(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.x import XAdapter
    monkeypatch.setenv("X_BEARER_TOKEN", "fake")

    # tweepy v4 Client.search_recent_tweets returns a Response object whose
    # .data is a list of Tweet objects. Mimic the shape with MagicMocks.
    tweet = MagicMock()
    tweet.id = 7777
    tweet.text = "$AAPL ripping on earnings"
    tweet.created_at.isoformat.return_value = "2026-05-26T12:00:00+00:00"
    tweet.author_id = 99
    response = MagicMock(); response.data = [tweet]

    fake_client = MagicMock()
    fake_client.search_recent_tweets.return_value = response
    with patch("tradingagents.sensing.adapters.x.tweepy.Client",
               return_value=fake_client):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = XAdapter(query="$AAPL OR $TSLA",
                      staging_root=str(tmp_path / "s"), stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n == 1
    env = json.loads((await r.xrange("ingest:raw"))[0][1]["data"])
    assert env["source"] == "x"
    assert env["external_id"] == "x:7777"


@pytest.mark.unit
def test_x_main_exits_zero_when_disabled(monkeypatch, capsys):
    """When the adapter is disabled, _main returns cleanly (exit 0)."""
    from tradingagents.sensing.adapters import x as xmod
    from tradingagents.default_config import DEFAULT_CONFIG
    monkeypatch.setitem(DEFAULT_CONFIG["sensing_adapters_enabled"], "x", False)
    # _main should return None (no SystemExit raised).
    assert xmod._main() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_adapter_x.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `x.py`**

Create `tradingagents/sensing/adapters/x.py`:

```python
"""X (Twitter) sensing adapter — polled recent search.

Behind `sensing_adapters_enabled.x` config gate (default False) because
API access is in flux (spec R-F3-3). Tier-dependent: filtered stream
requires elevated; recent_search works on basic.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone

import redis.asyncio as aioredis
import tweepy

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "x"
POLL_INTERVAL = 60


class XAdapter:
    name = NAME

    def __init__(self, *, query: str, staging_root: str, stream: str) -> None:
        self._query = query
        self._staging = staging_root
        self._stream = stream

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        token = os.environ.get("X_BEARER_TOKEN")
        if not token:
            log.warning("X_BEARER_TOKEN not set; skipping x poll"); return 0
        cs = CursorStore(conn)
        since_id = cs.get(NAME)
        try:
            client = tweepy.Client(bearer_token=token, wait_on_rate_limit=False)
            response = client.search_recent_tweets(
                query=self._query,
                since_id=int(since_id) if since_id else None,
                tweet_fields=["created_at", "author_id"],
                max_results=100,
            )
        except Exception as e:
            log.warning("x poll failed: %s", e); return 0
        tweets = response.data or []
        if not tweets:
            return 0
        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        new_max = int(since_id) if since_id else 0
        for tw in tweets:
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=f"x:{tw.id}",
                text=getattr(tw, "text", ""),
                source_tags={"author_id": getattr(tw, "author_id", None)},
                raw_path="",
            )
            await writer.write(env, raw_payload={"id": tw.id,
                                                  "text": getattr(tw, "text", "")},
                               cursor=str(tw.id))
            new_max = max(new_max, int(tw.id))
            emitted += 1
        return emitted

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn); backoff = 1
            except Exception:
                log.exception("x iteration crashed"); backoff = min(backoff * 2, 120)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main():
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return None
    query = os.environ.get("X_QUERY", "$AAPL OR $TSLA OR $NVDA -is:retweet lang:en")
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = XAdapter(query=query, staging_root=staging,
                  stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_adapter_x.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/adapters/x.py tests/sensing/test_adapter_x.py
git commit -m "sensing(adapters): x (tweepy recent_search; disabled by default)"
```

---


## Task 24: Triage `process_one` — single-envelope pipeline

**Files:**
- Create: `tradingagents/sensing/triage.py`
- Test: `tests/sensing/test_triage_process_one.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_triage_process_one.py`:

```python
import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker, get_active_watchlist
from tradingagents.sensing.envelope import Envelope


def _env(text="Apple reports a big beat on Q3 revenue", source="polygon_news",
         tags=None):
    return Envelope(
        source=source,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id=f"x:{text[:5]}",
        text=text, source_tags=tags or {}, raw_path="data/events/staging/x.json",
    )


@pytest.fixture
def conn(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)
    return conn


def _make_llm(salience=0.9, conf=0.95, ticker="AAPL"):
    def call(_prompt):
        return json.dumps({
            "salience": salience,
            "matched_tickers": [ticker],
            "mentioned_tickers": [{"ticker": ticker, "confidence": conf}],
            "reason": "test",
        })
    return call


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_one_writes_event_and_promotes(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(),
               data_dir=str(tmp_path / "data"))
    res = await t.process_one(_env())
    assert res.status == "triaged"
    # events row present
    row = conn.execute(
        "SELECT * FROM events WHERE event_id = ?", (res.event_id,)
    ).fetchone()
    assert row["salience"] == pytest.approx(0.9)
    # event_ticker row present
    et = conn.execute(
        "SELECT * FROM event_ticker WHERE event_id = ?", (res.event_id,)
    ).fetchone()
    assert et["ticker"] == "AAPL"
    # watchlist auto-promoted
    assert "AAPL" in get_active_watchlist(conn)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_one_duplicate_does_not_promote(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(),
               data_dir=str(tmp_path / "data"))
    env = _env(text="Same exact text", source="rss")
    res1 = await t.process_one(env)
    res2 = await t.process_one(env)  # exact replay
    assert res2.status == "duplicate"
    assert res2.deduped_of == res1.event_id
    # No second event_ticker row for AAPL on the duplicate.
    n = conn.execute(
        "SELECT COUNT(*) FROM event_ticker WHERE event_id = ?", (res2.event_id,)
    ).fetchone()[0]
    assert n == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_one_drops_unknown_tickers(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(ticker="NOTREAL"),
               data_dir=str(tmp_path / "data"))
    res = await t.process_one(_env())
    # NOTREAL is filtered out by validator; AAPL not in this envelope's tickers
    # either, so the event has no event_ticker rows.
    rows = conn.execute(
        "SELECT * FROM event_ticker WHERE event_id = ?", (res.event_id,)
    ).fetchall()
    assert rows == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_one_below_threshold_no_promote(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(salience=0.5),
               data_dir=str(tmp_path / "data"))
    res = await t.process_one(_env())
    assert res.status == "triaged"
    assert "AAPL" not in get_active_watchlist(conn)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_triage_process_one.py -v
```

Expected: ImportError on `Triage`.

- [ ] **Step 3: Implement `triage.py` (process_one only — consume loop in next task)**

Create `tradingagents/sensing/triage.py`:

```python
"""F3 triage consumer — pulls from Redis, dedupes, scores, persists.

This module exposes:
  - ``Triage``: the per-envelope pipeline (``process_one``) and consumer loop.
  - ``main()``: systemd entry point.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional, Sequence

import redis.asyncio as aioredis

from tradingagents.persistence.store import (
    insert_event, insert_event_ticker,
)
from tradingagents.sensing.dedupe import DedupeStage1, DedupeStage2
from tradingagents.sensing.envelope import Envelope
from tradingagents.sensing.salience import SalienceScorer, SalienceResult
from tradingagents.sensing.ticker_validator import TickerValidator
from tradingagents.sensing.watchlist import auto_promote


log = logging.getLogger(__name__)


@dataclass
class TriageResult:
    event_id: str
    status: str               # "triaged" | "duplicate"
    salience: Optional[float] = None
    deduped_of: Optional[str] = None
    matched_tickers: Sequence[str] = ()


class Triage:
    """Owns the per-envelope pipeline and the consume loop.

    Constructed once per triage process; one instance is shared across
    all asyncio consumers.
    """

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        redis: aioredis.Redis,
        embedder,                                          # Embedder
        llm_call: Callable[[str], "str | Awaitable[str]"],
        data_dir: str,
        cosine_threshold: float = 0.92,
        window_hours: int = 24,
        fingerprint_ttl_hours: int = 72,
        salience_threshold: float = 0.7,
        confidence_threshold: float = 0.8,
        salience_cache_ttl_seconds: int = 86400,
        ttl_days: int = 7,
    ) -> None:
        self._conn = conn
        self._redis = redis
        self._data_dir = data_dir
        self._ds1 = DedupeStage1(conn=conn, redis=redis,
                                  fingerprint_ttl_hours=fingerprint_ttl_hours)
        self._ds2 = DedupeStage2(conn=conn, embedder=embedder,
                                  cosine_threshold=cosine_threshold,
                                  window_hours=window_hours)
        self._scorer = SalienceScorer(redis=redis, llm_call=llm_call,
                                       cache_ttl_seconds=salience_cache_ttl_seconds)
        self._validator = TickerValidator(conn=conn)
        self._salience_threshold = salience_threshold
        self._confidence_threshold = confidence_threshold
        self._ttl_days = ttl_days
        # In-process cached active watchlist; refreshed by the loop every N s.
        self._watchlist: list[str] = []

    # ------------------------------------------------------------------
    def _new_event_id(self) -> str:
        return uuid.uuid4().hex

    def _canonical_raw_path(self, event_id: str, src_staging_path: str) -> str:
        canonical_dir = Path(self._data_dir) / "events"
        canonical_dir.mkdir(parents=True, exist_ok=True)
        dst = canonical_dir / f"{event_id}.json"
        try:
            shutil.move(src_staging_path, dst)
        except FileNotFoundError:
            # Staging file gone (test envelopes may not write one); leave path absent.
            return ""
        return str(dst)

    def set_active_watchlist(self, tickers: Sequence[str]) -> None:
        self._watchlist = list(tickers)

    # ------------------------------------------------------------------
    async def process_one(self, env: Envelope) -> TriageResult:
        """Run the full pipeline on one envelope. Always writes a row."""
        # Stage 1: hash / external_id dedupe.
        hit1 = await self._ds1.check(env)
        if hit1:
            ev_id = self._new_event_id()
            insert_event(
                self._conn, event_id=ev_id, source=env.source,
                ingested_ts=env.ingested_ts, salience=None,
                raw_path=self._canonical_raw_path(ev_id, env.raw_path),
                status="duplicate", deduped_of=hit1,
            )
            return TriageResult(event_id=ev_id, status="duplicate",
                                deduped_of=hit1)

        # Stage 2: embedding cosine.
        hit2 = self._ds2.check(env.text)
        if hit2:
            ev_id = self._new_event_id()
            insert_event(
                self._conn, event_id=ev_id, source=env.source,
                ingested_ts=env.ingested_ts, salience=None,
                raw_path=self._canonical_raw_path(ev_id, env.raw_path),
                status="duplicate", deduped_of=hit2,
            )
            return TriageResult(event_id=ev_id, status="duplicate",
                                deduped_of=hit2)

        # Score salience.
        score: SalienceResult = await self._scorer.score(
            env=env, watchlist=self._watchlist, macro_context="",
        )

        # Resolve tickers: union(source_tags.tickers, mentioned_tickers) → validate.
        candidate = list(env.source_tags.get("tickers", [])) + \
                    [m.ticker for m in score.mentioned_tickers]
        validated = self._validator.filter(candidate)

        # Write event.
        ev_id = self._new_event_id()
        insert_event(
            self._conn, event_id=ev_id, source=env.source,
            ingested_ts=env.ingested_ts, salience=score.salience,
            raw_path=self._canonical_raw_path(ev_id, env.raw_path),
            status="triaged", deduped_of=None,
        )
        # Record fingerprints + embedding (only on non-duplicates).
        await self._ds1.record(env, event_id=ev_id)
        self._ds2.record(text=env.text, event_id=ev_id)

        # Per-ticker rows + watchlist gate.
        conf_by_ticker = {m.ticker: m.confidence for m in score.mentioned_tickers}
        for t in validated:
            conf = conf_by_ticker.get(t, 0.5)  # source-tag tickers default to 0.5
            insert_event_ticker(self._conn, event_id=ev_id, ticker=t,
                                 confidence=conf)
            auto_promote(
                self._conn, ticker=t, event_id=ev_id,
                salience=score.salience, confidence=conf,
                salience_threshold=self._salience_threshold,
                confidence_threshold=self._confidence_threshold,
                ttl_days=self._ttl_days,
            )

        return TriageResult(event_id=ev_id, status="triaged",
                            salience=score.salience,
                            matched_tickers=score.matched_tickers)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_triage_process_one.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/triage.py tests/sensing/test_triage_process_one.py
git commit -m "sensing(triage): process_one — dedupe -> salience -> validate -> persist"
```

---

## Task 25: Triage consume loop + dead-letter sweep

**Files:**
- Modify: `tradingagents/sensing/triage.py` — add `consume()` + `dead_letter_sweep()` + `main()`
- Test: `tests/sensing/test_triage_loop.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_triage_loop.py`:

```python
import asyncio
import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker
from tradingagents.sensing.envelope import Envelope
from tradingagents.sensing.redis_client import ensure_consumer_group


@pytest.fixture
def conn(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)
    return conn


def _llm():
    def call(_p):
        return json.dumps({"salience": 0.5, "matched_tickers": [],
                            "mentioned_tickers": [], "reason": "ok"})
    return call


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consume_processes_one_envelope_then_acks(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="ingest:raw", group="triage")
    env = Envelope(source="rss",
                   ingested_ts=datetime.now(timezone.utc).isoformat(),
                   external_id="x:1", text="hello", source_tags={}, raw_path="")
    await r.xadd("ingest:raw", env.to_redis_fields())

    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(), llm_call=_llm(),
                data_dir=str(tmp_path / "data"))
    # One iteration, short block.
    await t.consume_once(group="triage", consumer="c1",
                          stream="ingest:raw", block_ms=10, batch=10)

    # Event written.
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert n == 1
    # No pending entries (acked).
    pending = await r.xpending("ingest:raw", "triage")
    assert pending["pending"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dead_letter_after_max_failures(conn, tmp_path):
    """A consistently-failing envelope ends up on ingest:dead after N tries."""
    from tradingagents.sensing.triage import Triage, dead_letter_sweep
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="ingest:raw", group="triage")

    # Inject an unparseable envelope by writing a bad payload.
    await r.xadd("ingest:raw", {"data": "not-json-at-all"})

    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(), llm_call=_llm(),
                data_dir=str(tmp_path / "data"))
    # Trigger 5 read attempts that fail (no ack on parse-error).
    for _ in range(5):
        await t.consume_once(group="triage", consumer="c1",
                              stream="ingest:raw", block_ms=10, batch=10)

    moved = await dead_letter_sweep(
        r, src_stream="ingest:raw", group="triage",
        dead_stream="ingest:dead", max_deliveries=5,
    )
    assert moved == 1
    dead = await r.xrange("ingest:dead")
    assert len(dead) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_triage_loop.py -v
```

Expected: AttributeError on `consume_once` / `dead_letter_sweep`.

- [ ] **Step 3: Append `consume_once`, `dead_letter_sweep`, `main` to `tradingagents/sensing/triage.py`**

Append to `tradingagents/sensing/triage.py`:

```python
# ----------------------------------------------------------------------
# Consume loop + dead-letter sweep + systemd entry point
# ----------------------------------------------------------------------

async def dead_letter_sweep(
    r: aioredis.Redis,
    *,
    src_stream: str,
    group: str,
    dead_stream: str,
    max_deliveries: int,
) -> int:
    """Move PEL entries with delivery_count > max_deliveries to ``dead_stream``.

    Returns # of messages moved. Safe to call repeatedly.
    """
    pending = await r.xpending_range(src_stream, group,
                                      min="-", max="+", count=200)
    moved = 0
    for p in pending:
        # max_deliveries is the threshold "this many failed attempts means dead";
        # so times_delivered < max_deliveries → keep trying, otherwise → move.
        if int(p["times_delivered"]) < max_deliveries:
            continue
        msg_id = p["message_id"]
        # Read the message to copy it.
        items = await r.xrange(src_stream, min=msg_id, max=msg_id)
        if not items:
            await r.xack(src_stream, group, msg_id)
            continue
        _, fields = items[0]
        await r.xadd(dead_stream, fields)
        await r.xack(src_stream, group, msg_id)
        moved += 1
    return moved


def _decode_fields(raw_fields):
    """Normalize bytes-or-str fields to a flat str dict."""
    out = {}
    for k, v in raw_fields.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8")
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        out[k] = v
    return out


# Attach to Triage as methods.
async def _consume_once(self, *, group: str, consumer: str, stream: str,
                         block_ms: int, batch: int) -> int:
    """Read one XREADGROUP batch and process each envelope.

    Successful envelopes are XACKed. Failures leave the message on the
    Pending Entries List, where dead_letter_sweep picks them up after
    max_deliveries retries.
    """
    try:
        result = await self._redis.xreadgroup(
            groupname=group, consumername=consumer,
            streams={stream: ">"}, count=batch, block=block_ms,
        )
    except Exception:
        log.exception("XREADGROUP failed"); return 0
    if not result:
        return 0
    handled = 0
    for _stream_name, entries in result:
        for env_id, raw_fields in entries:
            try:
                fields = _decode_fields(raw_fields)
                env = Envelope.from_redis_fields(fields)
                await self.process_one(env)
                await self._redis.xack(stream, group, env_id)
                handled += 1
            except Exception:
                log.exception("triage failed for %s; leaving on PEL", env_id)
    return handled


async def _consume_forever(self, *, group: str, consumer: str, stream: str,
                            block_ms: int, batch: int) -> None:
    while True:
        try:
            await self.consume_once(group=group, consumer=consumer,
                                     stream=stream, block_ms=block_ms,
                                     batch=batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("consume_forever iteration crashed")
            await asyncio.sleep(1)


Triage.consume_once = _consume_once             # type: ignore[attr-defined]
Triage.consume_forever = _consume_forever       # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Systemd entry point
# ----------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.persistence.store import get_active_watchlist
    from tradingagents.sensing.embeddings import SentenceTransformerEmbedder
    from tradingagents.sensing.redis_client import make_redis, ensure_consumer_group

    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])

    # Build the LLM caller from the existing factory.
    from tradingagents.llm_clients.factory import create_llm_client
    quick_client = create_llm_client(
        provider=C["llm_provider"], model=C["quick_think_llm"],
        base_url=C.get("backend_url"),
    )
    llm = quick_client.get_llm()
    def call_llm(prompt: str) -> str:
        # LangChain chat models expose .invoke for str-or-message input.
        out = llm.invoke(prompt)
        return getattr(out, "content", str(out))

    t = Triage(
        conn=conn, redis=redis,
        embedder=SentenceTransformerEmbedder(C["sensing_embedder_model"]),
        llm_call=call_llm,
        data_dir=C["iic_data_dir"],
        cosine_threshold=C["sensing_dedupe_cosine_threshold"],
        window_hours=C["sensing_dedupe_window_hours"],
        fingerprint_ttl_hours=C["sensing_fingerprint_ttl_hours"],
        salience_threshold=C["sensing_watchlist_salience_threshold"],
        confidence_threshold=C["sensing_watchlist_confidence_threshold"],
        salience_cache_ttl_seconds=C["sensing_salience_cache_ttl_seconds"],
        ttl_days=C["sensing_watchlist_ttl_days"],
    )

    async def run() -> None:
        await ensure_consumer_group(
            redis, stream=C["sensing_ingest_stream"], group=C["sensing_consumer_group"],
        )
        # Watchlist refresher: every N seconds, refresh in-process cache.
        async def refresher():
            while True:
                try:
                    t.set_active_watchlist(get_active_watchlist(conn))
                except Exception:
                    log.exception("watchlist refresh failed")
                await asyncio.sleep(C["sensing_watchlist_refresh_seconds"])

        # Dead-letter sweep every minute.
        async def reaper():
            while True:
                try:
                    await dead_letter_sweep(
                        redis,
                        src_stream=C["sensing_ingest_stream"],
                        group=C["sensing_consumer_group"],
                        dead_stream=C["sensing_dead_stream"],
                        max_deliveries=C["sensing_triage_max_failures"],
                    )
                except Exception:
                    log.exception("dead-letter sweep failed")
                await asyncio.sleep(60)

        # N consumers + refresher + reaper.
        tasks = [refresher(), reaper()]
        for i in range(C["sensing_triage_consumers"]):
            tasks.append(t.consume_forever(
                group=C["sensing_consumer_group"],
                consumer=f"c{i}",
                stream=C["sensing_ingest_stream"],
                block_ms=5000, batch=10,
            ))
        await asyncio.gather(*tasks)

    asyncio.run(run())


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_triage_loop.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/sensing/triage.py tests/sensing/test_triage_loop.py
git commit -m "sensing(triage): consume_once + dead_letter_sweep + systemd entry point"
```

---

## Task 26: CLI — `forge watchlist add/list/remove`

**Files:**
- Create or modify: `cli/forge.py` (create if F2 plan hasn't yet)
- Modify: `cli/main.py` to register the sub-app (idempotent)
- Test: `tests/cli/test_forge_watchlist.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/cli/test_forge_watchlist.py`:

```python
import json
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "iic.db"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(p))
    return str(p)


@pytest.mark.unit
def test_forge_watchlist_add_then_list(runner, db_path):
    from cli.forge import app
    r = runner.invoke(app, ["watchlist", "add", "AAPL"])
    assert r.exit_code == 0, r.output
    r2 = runner.invoke(app, ["watchlist", "list"])
    assert r2.exit_code == 0
    assert "AAPL" in r2.output


@pytest.mark.unit
def test_forge_watchlist_remove(runner, db_path):
    from cli.forge import app
    runner.invoke(app, ["watchlist", "add", "TSLA"])
    r = runner.invoke(app, ["watchlist", "remove", "TSLA"])
    assert r.exit_code == 0
    out = runner.invoke(app, ["watchlist", "list"]).output
    assert "TSLA" not in out


@pytest.mark.unit
def test_forge_watchlist_list_empty(runner, db_path):
    from cli.forge import app
    r = runner.invoke(app, ["watchlist", "list"])
    assert r.exit_code == 0
    assert "watchlist is empty" in r.output.lower() or r.output.strip() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_forge_watchlist.py -v
```

Expected: ImportError on `cli.forge`.

- [ ] **Step 3: Implement `cli/forge.py`**

If `cli/forge.py` does not exist (F2 plan not landed first), create it; if it does, append the `watchlist` and `sense` sub-apps to it. Below assumes a fresh create:

Create `cli/forge.py`:

```python
"""IIC-FORGE operational CLI.

Sub-apps:
  - watchlist : manage the curated watchlist (add / list / remove)
  - sense     : sensing-related ops (seed tickers, status, force sweep)

Wired into the main `tradingagents` CLI by ``cli/main.py``.
"""

from __future__ import annotations

import json
import typer
from rich.console import Console
from rich.table import Table

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect


app = typer.Typer(name="forge", help="IIC-FORGE operational commands")
console = Console()


# ---------------------------------------------------------------------
# watchlist sub-app
# ---------------------------------------------------------------------

watchlist_app = typer.Typer(name="watchlist", help="Manage the curated watchlist")
app.add_typer(watchlist_app, name="watchlist")


def _conn():
    # Re-read the env var rather than relying solely on DEFAULT_CONFIG —
    # DEFAULT_CONFIG fixes its values at import time, so tests that set
    # TRADINGAGENTS_IIC_DB_PATH after the first import need a live lookup.
    import os
    db_path = os.environ.get("TRADINGAGENTS_IIC_DB_PATH") or DEFAULT_CONFIG["iic_db_path"]
    return connect(db_path)


@watchlist_app.command("add")
def watchlist_add(ticker: str) -> None:
    """Add a ticker to the user-curated watchlist (never expires)."""
    from tradingagents.sensing.watchlist import add_user
    add_user(_conn(), ticker=ticker.upper())
    console.print(f"[green]added[/green] {ticker.upper()} (user-curated, no TTL)")


@watchlist_app.command("list")
def watchlist_list() -> None:
    """Print the current watchlist."""
    conn = _conn()
    rows = list(conn.execute(
        "SELECT ticker, added_ts, last_briefed, ttl_until, tags "
        "FROM watchlist ORDER BY ticker"
    ))
    if not rows:
        console.print("(watchlist is empty)")
        return
    t = Table("ticker", "added", "last_briefed", "ttl_until", "tags")
    for r in rows:
        tags = ", ".join(json.loads(r["tags"]) if r["tags"] else [])
        t.add_row(r["ticker"], r["added_ts"] or "",
                  r["last_briefed"] or "", r["ttl_until"] or "", tags)
    console.print(t)


@watchlist_app.command("remove")
def watchlist_remove(ticker: str) -> None:
    """Remove a ticker from the watchlist (works for user or auto rows)."""
    conn = _conn()
    n = conn.execute("DELETE FROM watchlist WHERE ticker = ?",
                      (ticker.upper(),)).rowcount
    conn.commit()
    if n:
        console.print(f"[yellow]removed[/yellow] {ticker.upper()}")
    else:
        console.print(f"[dim]{ticker.upper()} not on watchlist[/dim]")
```

- [ ] **Step 4: Register the sub-app in `cli/main.py` (idempotent)**

In `cli/main.py`, find the existing `app = typer.Typer(...)` block (around line 38) and add — after the block but before the existing `@app.command(...)` definitions:

```python
# IIC-FORGE F2/F3 ops sub-app. The import is guarded so failures inside
# cli/forge.py don't break the main CLI.
try:
    from cli.forge import app as _forge_app
    app.add_typer(_forge_app, name="forge")
except ImportError:
    pass
```

(If the F2 plan has already added this block, leave it.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/cli/test_forge_watchlist.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add cli/forge.py cli/main.py tests/cli/test_forge_watchlist.py
git commit -m "cli(forge): watchlist add/list/remove sub-app"
```

---

## Task 27: CLI — `forge sense reseed-tickers` + `sweep-watchlist`

**Files:**
- Modify: `cli/forge.py` — add `sense` sub-app with `reseed-tickers` and `sweep-watchlist`
- Test: `tests/cli/test_forge_sense.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/cli/test_forge_sense.py`:

```python
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "iic.db"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(p))
    return str(p)


@pytest.mark.unit
def test_forge_sense_reseed_calls_seed_all(runner, db_path, monkeypatch):
    from cli import forge as fmod
    calls = {"n": 0}
    def fake(conn):
        calls["n"] += 1
        return {"crypto": 20, "polygon": 0}
    monkeypatch.setattr(fmod, "seed_all", fake)
    r = runner.invoke(fmod.app, ["sense", "reseed-tickers", "--no-polygon"])
    assert r.exit_code == 0, r.output
    assert calls["n"] == 0  # --no-polygon → seed_crypto only
    # And the no-flag path calls full seed.
    monkeypatch.setattr(fmod, "seed_all", fake)
    r2 = runner.invoke(fmod.app, ["sense", "reseed-tickers"])
    assert calls["n"] >= 1


@pytest.mark.unit
def test_forge_sense_sweep_watchlist(runner, db_path):
    from cli.forge import app
    r = runner.invoke(app, ["sense", "sweep-watchlist"])
    assert r.exit_code == 0
    assert "pruned" in r.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_forge_sense.py -v
```

Expected: command not found.

- [ ] **Step 3: Append the `sense` sub-app to `cli/forge.py`**

Append to `cli/forge.py`:

```python
# ---------------------------------------------------------------------
# sense sub-app
# ---------------------------------------------------------------------

from tradingagents.sensing.seed_tickers import seed_all, seed_crypto
from tradingagents.sensing.watchlist import sweep_expired


sense_app = typer.Typer(name="sense", help="Sensing operational commands")
app.add_typer(sense_app, name="sense")


@sense_app.command("reseed-tickers")
def sense_reseed_tickers(
    no_polygon: bool = typer.Option(False, "--no-polygon",
                                     help="Skip Polygon equity seed (crypto only)"),
) -> None:
    """Repopulate the `tickers` reference table.

    Without `--no-polygon`, calls Polygon `/v3/reference/tickers` (requires
    POLYGON_API_KEY). With `--no-polygon`, only seeds the crypto static list.
    """
    conn = _conn()
    if no_polygon:
        n = seed_crypto(conn)
        console.print(f"crypto: {n} rows")
    else:
        result = seed_all(conn)
        console.print(f"crypto: {result['crypto']} rows; polygon: {result['polygon']} rows")


@sense_app.command("sweep-watchlist")
def sense_sweep_watchlist() -> None:
    """One-shot prune of expired auto-watchlist entries."""
    conn = _conn()
    n = sweep_expired(conn)
    console.print(f"pruned {n} expired watchlist row(s)")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_forge_sense.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/forge.py tests/cli/test_forge_sense.py
git commit -m "cli(forge): sense reseed-tickers + sweep-watchlist"
```

---

## Task 28: ops/redis/redis.conf + ops/backup.sh

**Files:**
- Create: `ops/redis/redis.conf`
- Create: `ops/backup.sh`
- Test: `tests/sensing/test_ops_redis_conf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_ops_redis_conf.py`:

```python
import pytest
from pathlib import Path


@pytest.mark.unit
def test_redis_conf_has_required_settings():
    text = Path("ops/redis/redis.conf").read_text()
    assert "appendonly yes" in text
    assert "appendfsync everysec" in text
    assert "maxmemory-policy noeviction" in text
    assert "maxmemory 256mb" in text
    # RDB snapshots explicitly disabled — AOF is the source of durability.
    assert "save \"\"" in text


@pytest.mark.unit
def test_backup_script_is_executable_and_handles_both_stores():
    import os, stat
    path = Path("ops/backup.sh")
    text = path.read_text()
    assert ".backup" in text                     # SQLite
    assert "BGREWRITEAOF" in text                # Redis
    assert "appendonly.aof" in text              # the artifact being copied
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
mkdir -p ops/redis
pytest tests/sensing/test_ops_redis_conf.py -v
```

Expected: FileNotFoundError on ops/redis/redis.conf.

- [ ] **Step 3: Create `ops/redis/redis.conf`**

```conf
# IIC F3 Redis configuration.
# Mounted via systemd EnvironmentFile or redis-server --include path.
#
# Durability: AOF every 1s — at most 1s of in-flight envelopes lost on crash.
# Eviction:   none — we never silently drop sensed events.

appendonly yes
appendfsync everysec
maxmemory 256mb
maxmemory-policy noeviction
save ""
dir /var/lib/redis
```

- [ ] **Step 4: Create `ops/backup.sh`**

```bash
#!/usr/bin/env bash
# IIC daily backup — SQLite + Redis AOF.
#
# Cron entry (root):
#   0 3 * * *  /opt/iic/ops/backup.sh >> /var/log/iic/backup.log 2>&1
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_ROOT=${BACKUP_ROOT:-/var/backups/iic}
SQLITE_DB=${IIC_DB_PATH:-$HOME/.tradingagents/iic.db}
REDIS_AOF=${REDIS_AOF:-/var/lib/redis/appendonly.aof}

mkdir -p "$BACKUP_ROOT/sqlite" "$BACKUP_ROOT/redis"

# SQLite: use the dedicated .backup pragma; safe under concurrent writers.
sqlite3 "$SQLITE_DB" ".backup '$BACKUP_ROOT/sqlite/iic-$STAMP.db'"

# Redis: ask the server to rewrite its AOF, then snapshot the file.
redis-cli BGREWRITEAOF
sleep 5
cp "$REDIS_AOF" "$BACKUP_ROOT/redis/appendonly-$STAMP.aof"

# Retain last 14 days.
find "$BACKUP_ROOT/sqlite" -name 'iic-*.db' -mtime +14 -delete
find "$BACKUP_ROOT/redis"  -name 'appendonly-*.aof' -mtime +14 -delete

echo "backup complete: $STAMP"
```

Then `chmod +x ops/backup.sh`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
chmod +x ops/backup.sh
pytest tests/sensing/test_ops_redis_conf.py -v
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add ops/redis/redis.conf ops/backup.sh tests/sensing/test_ops_redis_conf.py
git commit -m "ops: redis.conf (AOF=everysec, noeviction) + daily backup script"
```

---

## Task 29: ops/systemd unit files (six adapters + triage)

**Files:**
- Create: `ops/systemd/iic-sense-polygon.service`
- Create: `ops/systemd/iic-sense-telegram.service`
- Create: `ops/systemd/iic-sense-x.service`
- Create: `ops/systemd/iic-sense-rss.service`
- Create: `ops/systemd/iic-sense-gdelt.service`
- Create: `ops/systemd/iic-sense-macro.service`
- Create: `ops/systemd/iic-triage.service`
- Test: `tests/sensing/test_systemd_units.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_systemd_units.py`:

```python
import pytest
from pathlib import Path


_SENSE_UNITS = [
    "iic-sense-polygon", "iic-sense-telegram", "iic-sense-x",
    "iic-sense-rss", "iic-sense-gdelt", "iic-sense-macro",
]


@pytest.mark.unit
@pytest.mark.parametrize("name", _SENSE_UNITS)
def test_sense_unit_files_exist(name):
    p = Path(f"ops/systemd/{name}.service")
    assert p.exists(), f"missing {p}"
    text = p.read_text()
    assert "Requires=redis-server.service" in text
    assert "After=network-online.target redis-server.service" in text
    assert "Restart=on-failure" in text
    assert "RestartSec=30" in text
    assert "MemoryMax=512M" in text
    assert "CPUQuota=50%" in text
    assert "tradingagents.sensing.adapters" in text


@pytest.mark.unit
def test_triage_unit_file():
    p = Path("ops/systemd/iic-triage.service")
    assert p.exists()
    text = p.read_text()
    assert "Requires=redis-server.service" in text
    assert "tradingagents.sensing.triage" in text
    assert "MemoryMax=" in text


@pytest.mark.unit
@pytest.mark.parametrize("name", _SENSE_UNITS + ["iic-triage"])
def test_unit_files_reference_env_file(name):
    """Every service must read .env so creds are available without exposing them in unit files."""
    p = Path(f"ops/systemd/{name}.service")
    text = p.read_text()
    assert "EnvironmentFile=" in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
mkdir -p ops/systemd
pytest tests/sensing/test_systemd_units.py -v
```

Expected: FileNotFoundError on every unit.

- [ ] **Step 3: Create the unit files**

Create six adapter units with a common template. Each one varies only in
the `Description`, the `ExecStart` module path, and the log file name.

For `ops/systemd/iic-sense-polygon.service`:

```ini
[Unit]
Description=IIC sensing — Polygon news adapter
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.adapters.polygon_news
Restart=on-failure
RestartSec=30
MemoryMax=512M
CPUQuota=50%
StandardOutput=append:/var/log/iic/sense-polygon.log
StandardError=append:/var/log/iic/sense-polygon.log

[Install]
WantedBy=multi-user.target
```

Create the other five adapter units by changing the four varying lines.

`ops/systemd/iic-sense-telegram.service`:

```ini
[Unit]
Description=IIC sensing — Telegram streaming adapter
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.adapters.telegram
Restart=on-failure
RestartSec=30
MemoryMax=512M
CPUQuota=50%
StandardOutput=append:/var/log/iic/sense-telegram.log
StandardError=append:/var/log/iic/sense-telegram.log

[Install]
WantedBy=multi-user.target
```

`ops/systemd/iic-sense-x.service`:

```ini
[Unit]
Description=IIC sensing — X/Twitter adapter
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.adapters.x
Restart=on-failure
RestartSec=30
MemoryMax=512M
CPUQuota=50%
StandardOutput=append:/var/log/iic/sense-x.log
StandardError=append:/var/log/iic/sense-x.log

[Install]
WantedBy=multi-user.target
```

`ops/systemd/iic-sense-rss.service`:

```ini
[Unit]
Description=IIC sensing — RSS adapter
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.adapters.rss
Restart=on-failure
RestartSec=30
MemoryMax=512M
CPUQuota=50%
StandardOutput=append:/var/log/iic/sense-rss.log
StandardError=append:/var/log/iic/sense-rss.log

[Install]
WantedBy=multi-user.target
```

`ops/systemd/iic-sense-gdelt.service`:

```ini
[Unit]
Description=IIC sensing — GDELT adapter
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.adapters.gdelt
Restart=on-failure
RestartSec=30
MemoryMax=512M
CPUQuota=50%
StandardOutput=append:/var/log/iic/sense-gdelt.log
StandardError=append:/var/log/iic/sense-gdelt.log

[Install]
WantedBy=multi-user.target
```

`ops/systemd/iic-sense-macro.service`:

```ini
[Unit]
Description=IIC sensing — Macro (FRED + TE) adapter
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.adapters.macro
Restart=on-failure
RestartSec=30
MemoryMax=512M
CPUQuota=50%
StandardOutput=append:/var/log/iic/sense-macro.log
StandardError=append:/var/log/iic/sense-macro.log

[Install]
WantedBy=multi-user.target
```

`ops/systemd/iic-triage.service`:

```ini
[Unit]
Description=IIC triage consumer — dedupe + salience + persistence
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m tradingagents.sensing.triage
Restart=on-failure
RestartSec=30
MemoryMax=2G
CPUQuota=100%
StandardOutput=append:/var/log/iic/triage.log
StandardError=append:/var/log/iic/triage.log

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_systemd_units.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ops/systemd/iic-sense-*.service ops/systemd/iic-triage.service tests/sensing/test_systemd_units.py
git commit -m "ops(systemd): adapter + triage unit files (memory/CPU caps, on-failure restart)"
```

---

## Task 30: watchlist sweep service + timer

**Files:**
- Create: `ops/systemd/iic-watchlist-sweep.service`
- Create: `ops/systemd/iic-watchlist-sweep.timer`
- Test: `tests/sensing/test_systemd_sweep.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sensing/test_systemd_sweep.py`:

```python
import pytest
from pathlib import Path


@pytest.mark.unit
def test_sweep_service_runs_cli_subcommand():
    p = Path("ops/systemd/iic-watchlist-sweep.service")
    assert p.exists()
    text = p.read_text()
    assert "Type=oneshot" in text
    assert "forge sense sweep-watchlist" in text


@pytest.mark.unit
def test_sweep_timer_hourly():
    p = Path("ops/systemd/iic-watchlist-sweep.timer")
    assert p.exists()
    text = p.read_text()
    assert "OnCalendar=hourly" in text
    assert "Persistent=true" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/sensing/test_systemd_sweep.py -v
```

Expected: FileNotFoundError.

- [ ] **Step 3: Create the unit files**

`ops/systemd/iic-watchlist-sweep.service`:

```ini
[Unit]
Description=IIC watchlist TTL sweep
After=network-online.target

[Service]
Type=oneshot
User=iic
WorkingDirectory=/home/iic/TradingAgents/TradingAgents
EnvironmentFile=/home/iic/TradingAgents/TradingAgents/.env
ExecStart=/home/iic/TradingAgents/TradingAgents/.venv/bin/python -m cli.main forge sense sweep-watchlist
StandardOutput=append:/var/log/iic/watchlist-sweep.log
StandardError=append:/var/log/iic/watchlist-sweep.log
```

`ops/systemd/iic-watchlist-sweep.timer`:

```ini
[Unit]
Description=Hourly watchlist TTL prune

[Timer]
OnCalendar=hourly
Persistent=true
Unit=iic-watchlist-sweep.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/sensing/test_systemd_sweep.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add ops/systemd/iic-watchlist-sweep.* tests/sensing/test_systemd_sweep.py
git commit -m "ops(systemd): hourly watchlist TTL sweep service + timer"
```

---


## Task 31: `.env.example` — document F3 env vars

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Append F3 sensing block to `.env.example`**

Append to `.env.example`:

```bash

# ============================================================
# IIC-FORGE F3 sensing/triage env vars
# ============================================================

# Polygon news adapter (re-uses POLYGON_API_KEY from above).

# Telegram OSINT pull path (F0). Defaults to ./iic_osint.session.
#TELEGRAM_OSINT_SESSION=iic_osint.session

# Telegram F3 streaming adapter (SEPARATE session from OSINT — Telethon
# kicks a second concurrent connection on the same session).
#TELEGRAM_SENSING_SESSION=iic_sensing.session

# RSS adapter (comma-separated feed URLs).
#RSS_FEEDS=https://feeds.bloomberg.com/markets/news.rss,https://feeds.reuters.com/reuters/businessNews

# GDELT doc API query (any GDELT-supported boolean string).
#GDELT_QUERY=earnings OR "federal reserve" OR M&A

# Macro adapter — FRED is primary, TE is optional.
#FRED_API_KEY=
#TRADINGECONOMICS_KEY=

# X / Twitter adapter — disabled by default in DEFAULT_CONFIG; enable per-source.
#X_BEARER_TOKEN=
#X_QUERY=$AAPL OR $TSLA OR $NVDA -is:retweet lang:en

# Redis URL (override the default redis://127.0.0.1:6379/0).
#TRADINGAGENTS_SENSING_REDIS_URL=redis://127.0.0.1:6379/0
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "env: document F3 sensing vars (telegram sessions, RSS, GDELT, FRED, X)"
```

---

## Task 32: ops/runbooks/f3-exit-gate.md — pre-flight checklist

**Files:**
- Create: `ops/runbooks/f3-exit-gate.md`

- [ ] **Step 1: Create the runbook**

Create `ops/runbooks/f3-exit-gate.md`:

```markdown
# F3 24h Exit-Gate Runbook

The F3 exit gate is **one contiguous 24-hour run** with **no process restarts
allowed**. A single `systemctl restart` of any sensing or triage unit during
the window invalidates the gate. Plan the start time around your day.

## Pre-flight checklist

Run through this list in order; do not skip. Each item is a `pass/fail` —
fix before continuing.

- [ ] Dev machine on AC power. Battery-only is not acceptable.
- [ ] `systemd-inhibit --what=sleep --who="F3 exit gate" --why="24h sensing soak" sleep infinity &` running.
- [ ] Screen lock disabled for the window (`gsettings set org.gnome.desktop.screensaver lock-enabled false`).
- [ ] Display sleep disabled (`gsettings set org.gnome.desktop.session idle-delay 0`).
- [ ] Unattended-upgrades disabled for the window (`sudo systemctl mask unattended-upgrades.service`). Re-enable after the gate.
- [ ] All six adapters' env vars set: POLYGON_API_KEY, TELEGRAM_API_ID/HASH/SESSION (sensing), X_BEARER_TOKEN (if enabling x), FRED_API_KEY, RSS_FEEDS, GDELT_QUERY.
- [ ] Telegram **sensing** session pre-authenticated: `python -m tradingagents.sensing.adapters.telegram` once, complete any 2FA prompts, Ctrl+C, then start under systemd.
- [ ] Redis running (`systemctl status redis-server`), AOF on (`redis-cli config get appendonly` → `yes`).
- [ ] `tickers` table seeded: `python -m cli.main forge sense reseed-tickers` → at least 8000 rows in `tickers` (or skip the gate and re-seed).
- [ ] Baseline watchlist set: `forge watchlist add` for each of the user's standing tickers.
- [ ] **Pre-soak**: each adapter individually for 1 hour. Each must produce ≥1 event with `NRestarts=0`:
  ```bash
  for unit in iic-sense-{polygon,telegram,rss,gdelt,macro}; do
      sudo systemctl start "$unit.service"
      sleep 3600
      systemctl show "$unit.service" --property=NRestarts  # expect NRestarts=0
      sudo systemctl stop "$unit.service"
  done
  ```
- [ ] No pending reboot: `[ -f /var/run/reboot-required ] && echo NEEDS REBOOT || echo OK`.

## Start

```bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "START=$START" | tee /tmp/f3-gate-start.txt

# Enable all systemd units.
sudo systemctl start \
  iic-sense-polygon iic-sense-telegram iic-sense-rss \
  iic-sense-gdelt iic-sense-macro \
  iic-triage iic-watchlist-sweep.timer

# x adapter is optional (per R-F3-3); enable only if X_BEARER_TOKEN works.
# sudo systemctl start iic-sense-x

# Confirm everything is "active (running)".
systemctl status iic-sense-* iic-triage
```

## During the run

- Do not touch any service unit. Do not run `systemctl restart`.
- Spot-check log volume every few hours: `tail /var/log/iic/sense-*.log`.
- If a service dies, the gate is invalidated. Note the time; the evaluator
  will flag it. Fix the root cause before re-attempting.

## Stop and evaluate

```bash
START=$(cat /tmp/f3-gate-start.txt | cut -d= -f2)
python scripts/f3_exit_gate.py --since "$START"
# Output: docs/superpowers/artifacts/2026-MM-DD-f3-exit-gate-report.md
```

Review the artifact:
- Auto criteria (events ≥100, no restarts, ≥1 auto-promoted watchlist row) must all be true.
- Spot-check the 30-row dedupe sample. Sign off in the artifact with **YES** or **NO**.

## Tear-down

```bash
sudo systemctl stop iic-sense-* iic-triage
sudo systemctl stop iic-watchlist-sweep.timer
sudo systemctl unmask unattended-upgrades.service
kill %1  # systemd-inhibit
```
```

- [ ] **Step 2: Commit**

```bash
mkdir -p ops/runbooks docs/superpowers/artifacts
git add ops/runbooks/f3-exit-gate.md
git commit -m "ops(runbook): F3 24h exit-gate pre-flight + start/stop procedure"
```

---

## Task 33: Exit-gate evaluator script

**Files:**
- Create: `scripts/f3_exit_gate.py`
- Test: `tests/sensing/test_exit_gate_evaluator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sensing/test_exit_gate_evaluator.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import (
    insert_event, insert_event_ticker, upsert_watchlist,
)


def _seed_events(conn, n_active: int, n_dup: int, base_ts):
    for i in range(n_active):
        insert_event(conn, event_id=f"a-{i}", source="polygon_news",
                     ingested_ts=(base_ts + timedelta(minutes=i)).isoformat(),
                     salience=0.7, raw_path=f"p/{i}",
                     status="triaged", deduped_of=None)
    for j in range(n_dup):
        insert_event(conn, event_id=f"d-{j}", source="rss",
                     ingested_ts=(base_ts + timedelta(minutes=j)).isoformat(),
                     salience=None, raw_path=f"p/d-{j}",
                     status="duplicate", deduped_of=f"a-{j % max(n_active, 1)}")


@pytest.mark.unit
def test_evaluator_counts_events_and_dups(tmp_path):
    from scripts import f3_exit_gate
    db = tmp_path / "iic.db"
    conn = connect(str(db))
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    _seed_events(conn, n_active=120, n_dup=80, base_ts=since)
    upsert_watchlist(conn, ticker="AAPL",
                     ttl_until=(datetime.now(timezone.utc)
                                + timedelta(days=7)).isoformat(),
                     tags=["auto", "event:a-0"])
    res = f3_exit_gate.evaluate(
        db_path=str(db), since=since,
        services=[], check_systemd=False,
    )
    assert res.events_total == 200
    assert res.duplicates == 80
    assert res.autos >= 1
    assert res.crit_events is True
    assert res.crit_autos is True


@pytest.mark.unit
def test_evaluator_fails_when_no_autos(tmp_path):
    from scripts import f3_exit_gate
    db = tmp_path / "iic.db"
    conn = connect(str(db))
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    _seed_events(conn, n_active=120, n_dup=0, base_ts=since)
    res = f3_exit_gate.evaluate(
        db_path=str(db), since=since, services=[], check_systemd=False,
    )
    assert res.crit_autos is False
    assert res.passed_auto is False


@pytest.mark.unit
def test_evaluator_renders_artifact(tmp_path):
    from scripts import f3_exit_gate
    db = tmp_path / "iic.db"
    conn = connect(str(db))
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    _seed_events(conn, n_active=2, n_dup=2, base_ts=since)
    res = f3_exit_gate.evaluate(
        db_path=str(db), since=since, services=[], check_systemd=False,
    )
    md = f3_exit_gate.render_report(res)
    assert "Spot-check" in md
    assert "events" in md.lower()
    assert "duplicates" in md.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sensing/test_exit_gate_evaluator.py -v
```

Expected: ImportError on scripts.f3_exit_gate.

- [ ] **Step 3: Implement the evaluator**

Create `scripts/f3_exit_gate.py`:

```python
"""F3 exit-gate evaluator.

Usage:
    python scripts/f3_exit_gate.py --since "2026-05-26T14:00:00Z"

Writes an artifact under docs/superpowers/artifacts/<date>-f3-exit-gate-report.md
and exits 0 if every *automatic* criterion passed (spot-check is a separate
human sign-off in the artifact). Exits 1 on automatic-criterion failure.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Sequence

from tradingagents.persistence.db import connect


_DEFAULT_SERVICES = [
    "iic-sense-polygon", "iic-sense-telegram", "iic-sense-x",
    "iic-sense-rss", "iic-sense-gdelt", "iic-sense-macro",
    "iic-triage",
]


@dataclass
class ExitGateResult:
    since: datetime
    until: datetime
    events_total: int
    duplicates: int
    active: int
    autos: int
    restarts: Dict[str, int] = field(default_factory=dict)
    spot_sample: List[dict] = field(default_factory=list)
    crit_events: bool = False
    crit_autos: bool = False
    crit_restarts: bool = False
    passed_auto: bool = False


def _check_systemctl_restarts(services: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for svc in services:
        try:
            r = subprocess.run(
                ["systemctl", "show", f"{svc}.service",
                 "--property=NRestarts", "--value"],
                check=True, capture_output=True, text=True, timeout=5,
            )
            out[svc] = int((r.stdout or "0").strip() or 0)
        except Exception:
            out[svc] = -1  # unknown — treat as failure
    return out


def evaluate(
    *,
    db_path: str,
    since: datetime,
    services: Sequence[str] | None = None,
    check_systemd: bool = True,
) -> ExitGateResult:
    services = list(services) if services is not None else _DEFAULT_SERVICES
    conn = connect(db_path)
    until = since + timedelta(hours=24)
    events = list(conn.execute(
        "SELECT event_id, source, status, deduped_of, ingested_ts "
        "FROM events WHERE ingested_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))
    duplicates = [e for e in events if e["status"] == "duplicate"]
    active = [e for e in events if e["status"] == "triaged"]
    autos = list(conn.execute(
        "SELECT ticker, added_ts, tags FROM watchlist "
        "WHERE added_ts BETWEEN ? AND ? AND tags LIKE '%\"auto\"%'",
        (since.isoformat(), until.isoformat()),
    ))

    restarts: Dict[str, int] = {}
    if check_systemd:
        restarts = _check_systemctl_restarts(services)
    crit_restarts = (not restarts) or all(n == 0 for n in restarts.values())

    sample = random.sample(duplicates, min(30, len(duplicates))) if duplicates else []
    spot_sample: List[dict] = []
    for d in sample:
        orig = conn.execute(
            "SELECT event_id, source, ingested_ts FROM events WHERE event_id = ?",
            (d["deduped_of"],),
        ).fetchone()
        spot_sample.append({
            "dup": dict(d),
            "orig": dict(orig) if orig else None,
        })

    res = ExitGateResult(
        since=since, until=until,
        events_total=len(events), duplicates=len(duplicates),
        active=len(active), autos=len(autos),
        restarts=restarts, spot_sample=spot_sample,
        crit_events=(len(events) >= 100),
        crit_autos=(len(autos) >= 1),
        crit_restarts=crit_restarts,
    )
    res.passed_auto = res.crit_events and res.crit_autos and res.crit_restarts
    return res


def render_report(r: ExitGateResult) -> str:
    lines = [
        f"# F3 Exit-Gate Report — {r.since.date().isoformat()}",
        "",
        f"Window: `{r.since.isoformat()}` → `{r.until.isoformat()}`",
        "",
        "## Auto-criteria",
        "",
        f"- events ≥ 100: **{r.crit_events}** ({r.events_total} events)",
        f"- auto-promoted watchlist rows ≥ 1: **{r.crit_autos}** ({r.autos})",
        f"- no adapter restarts: **{r.crit_restarts}**",
        "",
        "## Per-adapter NRestarts",
        "",
    ]
    if r.restarts:
        for svc, n in sorted(r.restarts.items()):
            badge = "OK" if n == 0 else ("UNKNOWN" if n < 0 else f"FAIL ({n})")
            lines.append(f"- `{svc}.service`: {badge}")
    else:
        lines.append("(systemd check skipped — running outside the host)")
    lines += [
        "",
        "## Counts",
        "",
        f"- total events: {r.events_total}",
        f"- triaged: {r.active}",
        f"- duplicates: {r.duplicates}",
        f"- duplicates / total: "
        f"{(r.duplicates / r.events_total * 100):.1f}%" if r.events_total else "n/a",
        "",
        "## Dedup spot-check sample (30 rows)",
        "",
    ]
    for i, s in enumerate(r.spot_sample, 1):
        dup = s["dup"]; orig = s["orig"]
        lines.append(f"### sample {i}")
        lines.append(f"- duplicate: `{dup['event_id']}` ({dup['source']}, {dup['ingested_ts']})")
        if orig:
            lines.append(f"- original: `{orig['event_id']}` ({orig['source']}, {orig['ingested_ts']})")
        lines.append("")
    lines += [
        "## Sign-off",
        "",
        "Spot-check pass (≥24/30 are genuine duplicates): **YES / NO** — _reviewer notes here_",
        "",
        f"Overall auto-pass: **{r.passed_auto}**",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", required=True,
                   help="UTC ISO-8601 start of the 24h window")
    p.add_argument("--db", default=None,
                   help="Path to iic.db (defaults to DEFAULT_CONFIG)")
    p.add_argument("--no-systemd", action="store_true",
                   help="Skip systemctl restart checks")
    args = p.parse_args(argv)

    from tradingagents.default_config import DEFAULT_CONFIG as C
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    res = evaluate(db_path=args.db or C["iic_db_path"],
                   since=since, check_systemd=not args.no_systemd)
    out_dir = Path("docs/superpowers/artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{since.date().isoformat()}-f3-exit-gate-report.md"
    out_path.write_text(render_report(res))
    print(f"wrote {out_path}")
    print(f"events={res.events_total}  duplicates={res.duplicates}  "
          f"autos={res.autos}  passed_auto={res.passed_auto}")
    return 0 if res.passed_auto else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Ensure `scripts/__init__.py` exists so tests can import it**

```bash
test -f scripts/__init__.py || touch scripts/__init__.py
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/sensing/test_exit_gate_evaluator.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/f3_exit_gate.py scripts/__init__.py tests/sensing/test_exit_gate_evaluator.py
git commit -m "scripts: F3 exit-gate evaluator (events/dups/autos/restarts + spot-check)"
```

---

## Task 34: Boundary smoke test for F3 exit gate

**Files:**
- Test: `tests/smoke/test_f3_exit_gate.py`

This test runs without systemd and exercises the evaluator on a synthetic
SQLite store. It is the equivalent of `test_f1_exit_gate.py` — the
boundary that lets CI fail loudly if the schema or evaluator drifts.

- [ ] **Step 1: Write the test**

Create `tests/smoke/test_f3_exit_gate.py`:

```python
"""F3 exit-gate smoke — synthetic data through the evaluator end-to-end."""

import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker
from tradingagents.sensing.envelope import Envelope


pytestmark = pytest.mark.smoke


def _llm():
    def call(_p):
        return json.dumps({"salience": 0.9, "matched_tickers": ["AAPL"],
                            "mentioned_tickers": [{"ticker": "AAPL",
                                                    "confidence": 0.95}],
                            "reason": "test"})
    return call


@pytest.mark.asyncio
async def test_f3_smoke_synthetic_24h_window(tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    from scripts.f3_exit_gate import evaluate

    db = tmp_path / "iic.db"
    conn = connect(str(db))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=redis, embedder=MockEmbedder(),
               llm_call=_llm(),
               data_dir=str(tmp_path / "data"))

    # Push 120 unique events + 80 duplicates of the first 80 of them.
    base = datetime.now(timezone.utc) - timedelta(hours=12)
    uniques = []
    for i in range(120):
        env = Envelope(
            source="polygon_news",
            ingested_ts=(base + timedelta(seconds=i)).isoformat(),
            external_id=f"pn:{i}", text=f"Apple update #{i} unique content body",
            source_tags={}, raw_path="",
        )
        uniques.append(env)
        await t.process_one(env)
    for i in range(80):
        await t.process_one(uniques[i])  # exact replay → duplicate

    res = evaluate(db_path=str(db), since=base - timedelta(minutes=1),
                   check_systemd=False)
    assert res.events_total == 200
    assert res.duplicates == 80
    assert res.active == 120
    assert res.autos >= 1
    assert res.passed_auto is True
```

- [ ] **Step 2: Run the smoke test**

```bash
pytest tests/smoke/test_f3_exit_gate.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/test_f3_exit_gate.py
git commit -m "test(smoke): F3 exit-gate end-to-end on synthetic events"
```

---

## Task 35: Full F3 test suite verification

**Files:**
- (no new files — verification only)

- [ ] **Step 1: Run the unit suite**

```bash
pytest tests/sensing/ tests/persistence/test_schema_f3.py tests/persistence/test_store_f3.py \
       tests/test_default_config_f3.py tests/cli/test_forge_watchlist.py \
       tests/cli/test_forge_sense.py tests/test_telegram_osint_impl.py -v
```

Expected: every test PASS. Investigate any failure before declaring F3 done.

- [ ] **Step 2: Run the smoke suite**

```bash
pytest tests/smoke/test_f3_exit_gate.py -v
```

Expected: PASS.

- [ ] **Step 3: Run the full default test pass to confirm no regressions**

```bash
pytest -q
```

Expected: all `unit` and `smoke` tests PASS; `integration`-marked tests skipped where the env vars are placeholder.

- [ ] **Step 4: Verify nothing leaked**

```bash
# No leftover stub files; no TODOs/placeholders in shipped code.
grep -rn "TODO\|implementation pending\|FIXME" tradingagents/sensing/ scripts/ ops/ \
    && echo "WARN: stub strings present" || echo "clean"
```

Expected: "clean" (or only annotated TODOs that document deferred work).

- [ ] **Step 5: Confirm the working tree**

```bash
git status
git log --oneline -50
```

Expected: working tree clean; ~30+ commits since the F2 plan branch point.

- [ ] **Step 6: (Optional) Run the 24h soak**

Per `ops/runbooks/f3-exit-gate.md`:

```bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# follow the runbook step by step
# 24 hours later:
python scripts/f3_exit_gate.py --since "$START"
```

When the artifact's spot-check sign-off is **YES** and `passed_auto` is `True`,
F3 is complete.

- [ ] **Step 7: Final commit (if any verification turned up nits)**

```bash
git status
# If clean, F3 is done. If not, fix and one final commit.
```

---

## Summary

Total: 35 tasks, expected ~30 commits (some tasks have multiple files but a single commit). Each commit is small enough to bisect.

What you have when this plan is done:

- A SQLite-backed continuous sensing pipeline ingesting from up to six external sources.
- Redis-buffered triage with two-stage dedupe (hash + embedding) and Redis-cached salience scoring.
- Watchlist with user-curated + auto-promoted entries and a TTL sweep.
- Operational systemd units, Redis config, backup script, runbook.
- An exit-gate evaluator that writes an auditable artifact and a smoke test that exercises it end-to-end without systemd.

Anything deferred lives in §12 ("Out of scope") of the design — F4 picks it up.

