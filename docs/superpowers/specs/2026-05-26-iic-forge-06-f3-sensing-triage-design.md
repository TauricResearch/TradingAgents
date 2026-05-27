# IIC-FORGE-06 — F3 Always-on Sensing + Triage — Design

| Field | Value |
|---|---|
| **Track** | IIC-FORGE |
| **Document** | 06 |
| **Scope** | Per-phase design for F3 (Always-on sensing + triage). One level deeper than [the program-level spec §7-F3](2026-05-25-iic-forge-program-design.md). |
| **Base engine** | TauricResearch/TradingAgents v0.2.5 (F1 + F2 shipped to `main`) |
| **Owner** | Ziwei |
| **Date** | 2026-05-26 |
| **Status** | Ready for implementation planning |
| **Supersedes** | — |
| **Amends** | — (operates within the program design's existing schema and risk register; adds two append-only tables) |
| **Relates to** | [IIC-FORGE-03 program design](2026-05-25-iic-forge-program-design.md) §3 architecture, §6 state schema, §7-F3 exit gate, §8 R5; [IIC-FORGE-04 F1 plan](../plans/2026-05-25-iic-forge-04-f1-decision-core.md); [IIC-FORGE-05 F2 plan](../plans/2026-05-26-iic-forge-05-f2-backtest-benchmark.md) |
| **Companion plan (next)** | `docs/superpowers/plans/2026-05-26-iic-forge-06-f3-sensing-triage.md` (output of `superpowers:writing-plans`) |

## Quick links

- §1 Executive summary
- §2 Anchoring decisions
- §3 Architecture
- §4 Ingestion adapters
- §5 Triage pipeline
- §6 Watchlist update logic
- §7 Schema additions (append-only)
- §8 systemd units and Redis configuration
- §9 Boundary tests and exit-gate evaluator
- §10 Cost and operational notes
- §11 Risks (F3 additions to the program register)
- §12 Out of scope
- §13 Open questions deferred to implementation

---

## 1 · Executive summary

F3 ships a **continuous ingestion service** that pulls from six external sources, **deduplicates and scores** every incoming item, and **maintains a watchlist** that auto-promotes tickers in response to high-salience events. All artifacts land in F1's existing SQLite store; the only schema changes are four new append-only tables (`ingest_cursor`, `tickers`, `event_fingerprints`, `event_embeddings`) plus a documentation update to the `events.status` enum comment to add `'duplicate'`.

Four shape changes vs. the program-spec sketch:

1. **Redis becomes a first-class operational dependency.** ADR-F2's "Redis as the buffer" lands for real in F3 — installed as a systemd unit with AOF=`everysec`, used both as the sense → triage stream (`ingest:raw`) and as a 24h-TTL cache for salience scores and dedupe fingerprints. The Python `redis>=6.2.0` dep was already declared in `pyproject.toml` but never imported; F3 is its first use.
2. **Adapters are isolated at the process level, not the task level.** Each of the six sources runs as its own systemd unit (`iic-sense-polygon.service`, `iic-sense-telegram.service`, …). One source's crash, hang, or memory leak cannot take down the others. The cost is six unit files and six Python processes; the gain is per-source operability (enable / disable / restart / resource-cap each independently).
3. **Salience scoring is an every-event LLM call**, not a rule engine. A `quick_think_llm` call receives the active watchlist as context, returns JSON with `salience`, `matched_tickers` (watchlist intersection), `mentioned_tickers` (open universe), and `reason`. Cost ≈ $0.05/day at exit-gate volume. Cached in Redis by `source+fingerprint` with 24h TTL to absorb near-duplicate retries.
4. **Dedupe is two-stage hybrid**: a fast SHA-256 + external-id pass against a Redis fingerprint set catches re-deliveries and republishes; a `sqlite-vec` cosine-similarity pass against the last 24h of events catches semantic duplicates across sources. Duplicates are recorded with `status='duplicate'` and `deduped_of`, not dropped — so the exit-gate "80% deduped" check has evidence.

The exit gate is a single contiguous 24-hour run with **no process restarts allowed**. That tightens engineering requirements (defensive retry-internal in every adapter, per-iteration timeouts, bounded memory) but produces the strongest possible signal that the system is operationally stable before F4 starts auto-triggering work off its output. The user runs it on the dev machine with `systemd-inhibit` holding sleep off.

## 2 · Anchoring decisions

Settled during brainstorming. Each one rules out alternatives that would have changed the design materially.

### D1 — Buffer: Redis streams + consumer groups (honor ADR-F2)

The alternative considered was a SQLite `ingest_buffer` table with a lease pattern — strictly fewer moving parts, reuses F1 plumbing, and survives crashes by default. The case against it that won was operational: the program spec's R5 explicitly calls out SQLite single-writer contention, and adding a continuous ingestion writer to that queue narrows headroom in the system's central bottleneck. Redis `XADD` + `XREADGROUP` removes that pressure and gives true parallel consumers with built-in at-least-once semantics. The cost is a second persistent store to operate (systemd unit, AOF configuration, separate backup) — accepted because Redis was already in `pyproject.toml` and ADR-F2 had already named it.

Trade-offs:

- Mid-flight messages live in Redis, not SQLite. With AOF=`everysec` we lose at most one second of in-flight data on host crash.
- Backups now span two systems. Operational note in §10.

### D2 — Adapter isolation: one systemd unit per adapter

The alternative was a single async supervisor process holding all six adapters as `asyncio.Task`s — lighter footprint, one connection pool, simpler deploy. The case against it that won was fault isolation: a noisy or memory-leaky source under the supervisor degrades all sources; with per-process units, one bad source is one `systemctl restart`. Per-source `MemoryMax` / `CPUQuota` / `Restart=on-failure` are systemd-native, no app-level supervisor to maintain.

Combined with D8's strict no-restart exit gate: each adapter must be **defensively retry-internal** — catch transient errors in the polling loop with exponential backoff, re-establish connections rather than exit, never raise out of `stream()` except on configuration errors that require operator intervention. Crash-and-restart is acceptable in normal operation (systemd handles it) but invalidates the exit gate.

### D3 — Salience: every-event cheap-LLM call with watchlist context

The alternatives were rule-based features with an LLM tiebreak (cheaper but rules without backtest data are guesses) and embedding novelty as a salience proxy (cheapest but conflates "novel" with "important" — the wrong signal). The winning case: F3 ships *before* we have any backtest data on what predicts moves, so a context-aware LLM with a clear scoring prompt is a better-calibrated prior than hand-tuned rules. ~$0.05/day at exit-gate volume is well inside the cost-guards-disabled regime.

The prompt asks for both watchlist-relevance (`matched_tickers`) and open-universe ticker extraction (`mentioned_tickers`) in one call, so D5's ticker mapping comes free with the salience score. The response is cached in Redis by `source+fingerprint` with 24h TTL.

### D4 — Dedupe: hybrid two-stage, duplicates marked not dropped

Stage 1 is cheap and catches the common cases: Redis re-deliveries, RSS feed re-publishes, retweets — anything with an exact `external_id` match or SHA-256 hash match against the last 72h of fingerprints. Stage 2 catches the interesting case: the same story from three news outlets with different wording. Stage 2 embeds the text and queries `sqlite-vec` for the nearest neighbour in the last 24h; cosine ≥ 0.92 flags it as a semantic duplicate.

Critically, **duplicates are written** to `events` with `status='duplicate'` and `deduped_of=<original_event_id>`. The F1 schema documents `status` as `"new" | "triaged" | "discarded"`; F3 extends the documented enum to add `'duplicate'`. There is no CHECK constraint on the column, so this is a comment-only change to `schema.sql`, not DDL. Duplicates don't fire downstream actions, but the exit-gate evaluator queries them to score the 80% criterion.

### D5 — Ticker mapping: hybrid (source tags + LLM extract + reference validation)

Polygon news ships with a structured `tickers` field; we trust those at high confidence. For all sources, the salience LLM call also returns `mentioned_tickers` (open universe, with per-ticker confidence). Both sets are unioned and **validated against a `tickers` reference table** (US equities from NASDAQ/NYSE/ARCA + top-20 crypto). Symbols not in the reference table are dropped — this is the LLM-hallucination guard.

`event_ticker` rows carry a `source` tag in `tags JSON` (`polygon_tag`, `llm_extract`, `body_match`) so any auto-promoted ticker is auditable: "why is BAYRY on my watchlist?" → one query.

### D6 — Watchlist: user-curated base + auto-add with TTL

Two flows coexist:

- **User-curated**: CLI `forge watchlist add AAPL`. `ttl_until = NULL`, `tags = ["user"]`. Never expires. The user's primary holdings stay on the watchlist even during quiet news weeks.
- **Auto-promoted by triage**: when `event.salience ≥ 0.7 AND ticker.confidence ≥ 0.8`, upsert `(ticker, ttl_until = now() + 7d, tags ∋ ["auto", "event:<id>"])`. New mention refreshes `ttl_until`. An hourly sweep job prunes rows with `ttl_until < now() AND 'user' NOT IN tags`.

The 0.7 / 0.8 thresholds are starting values to be tuned post-soak from observed data.

### D7 — Telegram: replace F0 stub + separate sensing adapter, two sessions

F0's `tradingagents/dataflows/telegram_osint.py` is a pull-style Telethon stub that raises `DataVendorError("implementation pending")`. F5 will need a Bot API push path — separate concern. F3 needs a *continuous stream* path. The decision:

- F0 stub gets a real Telethon `iter_messages()` implementation for the analyst pull path; uses `TELEGRAM_OSINT_SESSION`.
- F3 ships a separate streaming adapter (`iic-sense-telegram.service`) that uses Telethon `add_event_handler(NewMessage)`; uses `TELEGRAM_SENSING_SESSION` (distinct `.session` file). Two session files because Telethon will kick a second concurrent connection on the same session.
- F5's brief delivery (out of scope here) will use `python-telegram-bot` with a bot token — entirely separate library and credentials.

### D8 — Exit gate: dev machine, single contiguous 24h, no restarts

Tightens the engineering bar beyond the program spec's "24-hour continuous run" wording. The user runs it on the dev machine with `systemd-inhibit` holding sleep off. The evaluator reads `systemctl show iic-sense-*.service --property=NRestarts` and fails the gate if any adapter restarted during the window.

Implications cascade:

- Every adapter must be **defensively retry-internal** (D2).
- Per-iteration timeouts in every adapter loop (no unbounded hangs).
- Memory growth must be bounded — pre-soak with a 1h-per-adapter dry-run before the 24h attempt.
- Cursors (§4) still get implemented but are not relied on for gate passage; they're correct engineering for normal operation.

## 3 · Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ INGESTION  (six independent systemd units — defensive retry-internal)    │
│                                                                            │
│   polygon-ingest  telegram-ingest  x-ingest  rss-ingest                    │
│   gdelt-ingest    macro-ingest                                             │
│        │                │              │         │                         │
│        └────────────────┴──── XADD ────┴─────────┘                         │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
                          ┌─────────────────────────┐
                          │ Redis  (systemd unit)   │
                          │   ingest:raw stream     │  AOF=everysec
                          │   fingerprints:<date>   │  72h TTL
                          │   salience:cache:*      │  24h TTL
                          └────────────┬────────────┘
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ TRIAGE  (iic-triage.service — N async consumers in one XREADGROUP)       │
│                                                                            │
│   Stage 1 dedupe (hash) → Stage 2 dedupe (embed)                           │
│        │                                                                   │
│        ▼                                                                   │
│   Salience LLM call (cached) → ticker extraction + reference validation    │
│        │                                                                   │
│        ▼                                                                   │
│   events row + event_ticker rows + watchlist upsert (if gated)             │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
                          ┌─────────────────────────┐
                          │ SQLite (F1 store)              │
                          │   events                       │
                          │   event_ticker                 │
                          │   watchlist                    │
                          │   ingest_cursor      (NEW)     │
                          │   tickers            (NEW)     │
                          │   event_fingerprints (NEW)     │
                          │   event_embeddings   (NEW)     │
                          └────────────────────────────────┘
```

The ingestion → buffer → triage handoff is one-way; the triage consumer never writes back to Redis except to `XACK` and to update salience caches. SQLite is the canonical store for everything that survives triage. Filesystem `data/events/<event_id>.json` continues to hold the raw payload (per program spec §6 filesystem layout); SQLite holds the indexed metadata + the `raw_path` pointer.

### Three load-bearing constraints

1. **One-way data flow.** Adapters never read from `events`; triage never writes to `ingest:raw`. The only feedback loop is the cursor write (per-adapter) so the adapter remembers where to resume.
2. **At-least-once semantics.** Every adapter writes with idempotent keys (`external_id` or a deterministic fingerprint). The dedupe pipeline tolerates re-delivery. A crashed triage consumer's batch goes back to the pending-entries list and is re-processed; idempotent writes mean re-processing is safe.
3. **Schema additions are append-only.** F1 already defines `events`, `event_ticker`, `watchlist`, `suppression`. F3 adds two reference tables. No existing column is reshaped.

## 4 · Ingestion adapters

### Common contract

```python
class IngestAdapter(Protocol):
    name: str  # "polygon_news", "telegram", "x", "rss", "gdelt", "macro"

    async def stream(self, redis: aioredis.Redis, cursor: CursorStore) -> None:
        """Long-lived. Reads from the source, writes envelopes to
        Redis stream "ingest:raw", and persists its cursor after every
        successful batch.

        Defensive: catches all transient errors with exponential backoff
        + jitter. Only re-raises on configuration errors that require
        operator intervention (e.g., missing credentials, schema break).
        """
```

The envelope on `ingest:raw`:

```json
{
  "source": "polygon_news",
  "ingested_ts": "2026-05-26T14:33:21.123Z",
  "external_id": "pn:abc123",
  "text": "<normalized full text>",
  "source_tags": {"tickers": ["AAPL"], "category": "earnings"},
  "raw_path": "data/events/staging/2026-05-26/abc123.json"
}
```

`raw_path` is written to disk by the adapter before `XADD`, so on a crash mid-write Redis never points at a non-existent file. The triage worker rewrites `raw_path` to the canonical `data/events/<event_id>.json` location on success.

### Per-source notes

| Source | Mode | Poll interval | Cursor | Library | Replaces stub at |
|---|---|---|---|---|---|
| `polygon_news` | REST poll | 60s | last-seen `published_utc` | `requests` (sync inside an asyncio task is fine for 1 call/min) | [tradingagents/dataflows/polygon.py:75](../../tradingagents/dataflows/polygon.py) |
| `telegram` | Telethon `iter_messages` per channel | 90s | max `message_id` per channel | `telethon` | new; sibling to [tradingagents/dataflows/telegram_osint.py](../../tradingagents/dataflows/telegram_osint.py) which becomes the F0 pull-path real impl |
| `x` | Polled search or filtered stream (decide at implementation) | 60s | `since_id` | `tweepy` | new |
| `rss` | `feedparser` per feed | 5min | max `published` ts per feed | `feedparser` | new |
| `gdelt` | GDELT 2.0 doc API | 15min | `last_seen_date` | `requests` + `pandas` | new |
| `macro` | FRED + TradingEconomics calendar | 30min | `last_release_id` | `requests` | new |

Each adapter lives at `tradingagents/sensing/adapters/<source>.py` with a `class <Source>Adapter` plus an `if __name__ == "__main__":` entry point for the systemd unit (`ExecStart=/usr/bin/env python -m tradingagents.sensing.adapters.polygon_news`).

### Cursor persistence

```python
class CursorStore:
    """Thin wrapper over the ingest_cursor SQLite table.
    Atomic upsert per source. WAL mode keeps it lock-free in practice."""
    def get(self, source: str) -> str | None: ...
    def set(self, source: str, cursor: str) -> None: ...
```

Each adapter calls `cursor.set(self.name, new_cursor)` after every successful batch write to Redis. On restart, `cursor.get(self.name)` returns the last known cursor; the adapter resumes from there. Critically, an adapter can also resume from "now minus N hours" if its cursor is missing or stale beyond a threshold (config: `max_cursor_lag_hours: 6`), preventing a long-stopped adapter from flooding the system on restart.

## 5 · Triage pipeline

`iic-triage.service` runs a single Python process with N async consumers in one Redis consumer group (`triage`). N defaults to 4; configurable. Each consumer is an `asyncio.Task`.

### Consumer loop

```python
async def consume():
    while True:
        envelopes = await redis.xreadgroup(
            groupname="triage", consumername=consumer_id,
            streams={"ingest:raw": ">"}, count=10, block=5000,
        )
        for env_id, env in envelopes:
            try:
                await process_one(env)
                await redis.xack("ingest:raw", "triage", env_id)
            except Exception:
                # Don't ack — pending entries list will retry.
                # On 5 failures (XPENDING idle > N min), a sweep
                # moves to dead-letter stream "ingest:dead".
                log.exception("triage failed for %s", env_id)
```

### `process_one` stages

1. **Stage 1 dedupe (hash):** Compute `fp = sha256(normalize(text))`. Look up the envelope's `external_id` and `fp` in `event_fingerprints` (SQLite). Either hit → write `events` row with `status='duplicate'`, `deduped_of=<existing>`, insert *no* `event_fingerprints` rows (the original already owns them), return.
2. **Stage 1 record fingerprints:** Insert into `event_fingerprints` two rows for the new event: `(external_id, event_id, kind='external_id')` (if present) and `(fp, event_id, kind='sha256')`. Also `SADD fingerprints:<today_utc> <fp>` + 72h `EXPIRE` for the hot path (Redis is the fast positive-cache; the SQLite table is the durable record).
3. **Stage 2 dedupe (embed):** Embed text. Query `sqlite-vec` joined with `event_embeddings` for the nearest neighbour whose `events.ingested_ts > now() - 24h`. If `cosine >= 0.92`, write `events` row with `status='duplicate'`, `deduped_of=<nearest.event_id>`, *skip* `event_embeddings` insert (we don't store duplicates' embeddings — the original is the canonical vector), return.
4. **Salience scoring:** Build cache key `salience:<source>:<fp[:32]>`. If `GET` hits, use cached. Else call `quick_think_llm` with the prompt below; `SETEX` 24h.
5. **Ticker validation:** Union of `mentioned_tickers` from the LLM response and `source_tags.tickers` from the envelope. For each, look up in `tickers` reference table; drop unknowns (LLM hallucinations). Per remaining ticker, emit `(ticker, confidence, source_tag)`.
6. **Write event:** Insert `events` row (`status='triaged'`, `raw_path` updated to canonical location). Insert one `event_embeddings` row linking the event to the vec_index row. Insert `event_ticker` rows.
7. **Watchlist update:** For each ticker where `salience >= 0.7 AND confidence >= 0.8`, upsert `watchlist` with `ttl_until = now() + 7d` and `tags ∋ ["auto", f"event:{event_id}"]`. Existing user-curated entries (`ttl_until IS NULL`) are not overwritten — only `last_briefed` and tags update.

Status enum used by F3: `'triaged'` for active events (extends the F1 schema convention), `'duplicate'` for dedup'd events (new value documented in §2 D4 and §7).

### Salience LLM prompt

```text
You are scoring market-relevance for an investment watchlist.

ACTIVE WATCHLIST: {watchlist_csv}
RECENT MACRO CONTEXT (last 4h, may be empty): {macro_context}

EVENT SOURCE: {source}
EVENT TIMESTAMP: {ingested_ts}
EVENT TEXT (first 800 chars): {text}
SOURCE-PROVIDED TICKER TAGS (may be empty): {source_tags}

Return strictly JSON:
{
  "salience": <float 0.0-1.0>,
  "matched_tickers": [<ticker from watchlist that this materially involves>],
  "mentioned_tickers": [{"ticker": "<symbol>", "confidence": <float 0-1>}],
  "reason": "<one sentence>"
}

Salience anchors:
  0.0-0.3 : routine, no clear watchlist relevance
  0.3-0.6 : context relevant but unlikely to move prices alone
  0.6-0.85: directly relevant to a watchlist instrument
  0.85-1.0: high-impact, time-sensitive, watchlist-relevant
```

The active watchlist is fetched once per consumer at startup and refreshed every 60s — bounded staleness without per-call DB pressure.

## 6 · Watchlist update logic

Two write paths into `watchlist`:

```python
# Path A: User-curated (CLI)
def watchlist_add_user(ticker: str, tags: list[str] = ()):
    upsert(
        watchlist,
        ticker=ticker,
        added_ts=now(),
        last_briefed=None,
        ttl_until=None,                      # ← permanent
        tags=json.dumps(list(set(tags + ["user"]))),
    )

# Path B: Triage auto-promotion (inside process_one)
def watchlist_auto_promote(ticker: str, event_id: str, salience: float, conf: float):
    if salience < 0.7 or conf < 0.8:
        return
    existing = get(watchlist, ticker)
    if existing and "user" in existing.tags:
        # Don't touch user-curated entries; just refresh last_briefed for visibility
        update(watchlist, ticker, last_briefed=now())
        return
    upsert(
        watchlist,
        ticker=ticker,
        added_ts=existing.added_ts if existing else now(),
        last_briefed=now(),
        ttl_until=now() + timedelta(days=7),   # ← always refreshed
        tags=json.dumps(sorted(set(
            (existing.tags if existing else []) + ["auto", f"event:{event_id}"]
        ))),
    )
```

Sweep job (`iic-watchlist-sweep.timer`, hourly):

```sql
DELETE FROM watchlist
WHERE ttl_until IS NOT NULL
  AND ttl_until < datetime('now')
  AND tags NOT LIKE '%"user"%';
```

Each prune logs `(ticker, added_ts, last_event_id)` to `data/logs/watchlist-sweep.log` for audit.

## 7 · Schema additions (append-only)

Four new tables, plus a single comment-only update to the existing `events.status` enum documentation. No DDL change to any existing table.

```sql
-- ============================================================
-- F3 tables — added by F3 ingestion + triage
-- ============================================================

-- Per-adapter resumption state. Atomic upsert from CursorStore.
CREATE TABLE IF NOT EXISTS ingest_cursor (
    source     TEXT PRIMARY KEY,           -- e.g., "polygon_news"
    cursor     TEXT NOT NULL,              -- adapter-specific opaque payload
    updated_ts TEXT NOT NULL
);

-- Reference ticker universe. Seeded from Polygon + crypto static list.
-- LLM-extracted tickers are validated against this table before write.
CREATE TABLE IF NOT EXISTS tickers (
    ticker     TEXT PRIMARY KEY,           -- "AAPL", "BTC-USD"
    exchange   TEXT NOT NULL,              -- "NASDAQ" | "NYSE" | "ARCA" | "CRYPTO"
    name       TEXT NOT NULL,              -- "Apple Inc."
    aliases    TEXT,                       -- JSON array: ["Apple", "Apple Computer"]
    active     INTEGER NOT NULL DEFAULT 1, -- 0 = delisted (filtered)
    updated_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickers_active ON tickers(active);

-- Stage-1 dedupe lookup. One row per (fingerprint, kind) for each event's
-- external_id and SHA-256 fingerprint. Cheap PK lookup before any embedding.
CREATE TABLE IF NOT EXISTS event_fingerprints (
    fingerprint TEXT NOT NULL,             -- external_id or sha256 hex
    kind        TEXT NOT NULL,             -- 'external_id' | 'sha256'
    event_id    TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    created_ts  TEXT NOT NULL,
    PRIMARY KEY (fingerprint, kind)
);
CREATE INDEX IF NOT EXISTS idx_event_fingerprints_event ON event_fingerprints(event_id);

-- Stage-2 dedupe link. One row per non-duplicate event linking it to its
-- vec_index embedding. Duplicates do NOT get embeddings stored (the original
-- is the canonical vector for that semantic cluster).
CREATE TABLE IF NOT EXISTS event_embeddings (
    event_id   TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    vec_id     INTEGER NOT NULL,           -- app-layer FK to vec_index.rowid
    created_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_embeddings_vec ON event_embeddings(vec_id);
```

**No reshape of `events`, `event_ticker`, `watchlist`, or any F1/F2 table.** All new structures are tables. The only edit to existing schema is a comment-only line in `schema.sql` around line 137 extending the documented enum for `events.status` from `"new" | "triaged" | "discarded"` to `"new" | "triaged" | "discarded" | "duplicate"`. No CHECK constraint exists on the column, so the DDL is unchanged.

`event_ticker.confidence` already exists; `events.deduped_of` already exists; `watchlist.ttl_until` is already nullable. Everything else fits the F1 schema as-is.

Seed for `tickers`: one-off CLI `forge sense reseed-tickers` pulls from Polygon `/v3/reference/tickers` (paginated, free on developer tier) for US equities and merges in a top-20 crypto static list from `tradingagents/sensing/data/crypto_universe.yaml`. Re-runnable monthly. Ships ~10k rows.

## 8 · systemd units and Redis configuration

Eight units in `ops/systemd/` (six adapters + triage + watchlist-sweep timer):

```
ops/systemd/
  iic-sense-polygon.service
  iic-sense-telegram.service
  iic-sense-x.service
  iic-sense-rss.service
  iic-sense-gdelt.service
  iic-sense-macro.service
  iic-triage.service
  iic-watchlist-sweep.service
  iic-watchlist-sweep.timer
```

Template service file (one example):

```ini
# ops/systemd/iic-sense-polygon.service
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

Service-level `Restart=on-failure` is a safety net for normal operation. The exit-gate evaluator (§9) checks `systemctl show ... --property=NRestarts` and **fails the gate if any adapter restarted during the 24h window**.

`MemoryMax=512M` and `CPUQuota=50%` ship per Appendix A of the program spec — measurement-on, but systemd will *kill* the unit if memory exceeds (this is hard kill, not graceful guard; documented in the runbook).

### Redis configuration

```conf
# ops/redis/redis.conf
appendonly yes
appendfsync everysec        # lose at most 1s of in-flight data on host crash
maxmemory 256mb
maxmemory-policy noeviction # never silently drop in-flight events
save ""                     # disable RDB snapshots; AOF is the source of durability
dir /var/lib/redis
```

Installed via the `redis-server` package (standard distro package). systemd unit name is the distro default `redis-server.service`, on which the adapters and triage `Requires=`.

## 9 · Boundary tests and exit-gate evaluator

### Per-phase boundary tests (P7 discipline)

Five tests in `tests/sensing/`:

1. **Adapter envelope contract** (`test_adapter_envelope.py`) — for each adapter, mock the source response and assert: envelope shape matches the contract, cursor updates, `XADD` to `ingest:raw` is called.
2. **Dedupe two-stage** (`test_dedupe.py`) — feed two byte-identical items + one near-duplicate. Assert: 1 active, 2 with `status='duplicate'`, `deduped_of` matches first event, embedding written to `sqlite-vec`.
3. **Salience cache** (`test_salience_cache.py`) — same envelope twice. Assert: LLM called once, cached value returned on the second.
4. **Watchlist gate** (`test_watchlist_promote.py`) — synthetic event with `salience=0.85, ticker_confidence=0.9` for a new ticker. Assert: `watchlist` row appears with `tags ∋ "auto"` and `ttl_until ≈ now + 7d`. Same event with `salience=0.6`. Assert: no upsert. User-curated existing entry. Assert: not overwritten, only `last_briefed` advances.
5. **Reference validator** (`test_ticker_validator.py`) — LLM returns `["AAPL", "NOTREAL", "TSLA"]`. Reference table contains `AAPL` and `TSLA`. Assert: only `AAPL` and `TSLA` get `event_ticker` rows.

All five use mock LLM / mock Redis where possible. They're fast (`unit` marker) and run on every commit.

### Exit-gate evaluator

`scripts/f3_exit_gate.py` (cleanly invokable as `python scripts/f3_exit_gate.py --since "2026-MM-DDTHH:MM:SSZ"`):

```python
def evaluate_exit_gate(since: datetime) -> ExitGateResult:
    until = since + timedelta(hours=24)
    events = db.query("SELECT * FROM events WHERE ingested_ts BETWEEN ? AND ?", since, until)
    duplicates = [e for e in events if e.status == "duplicate"]
    active = [e for e in events if e.status == "triaged"]

    # Criterion 1: ≥100 events ingested
    crit1 = len(events) >= 100

    # Criterion 2: ≥80% deduped successfully — manual spot check
    # The script SAMPLES 30 duplicate rows and renders side-by-side comparison;
    # the human reviewer signs off in the artifact.
    sample = random.sample(duplicates, min(30, len(duplicates)))
    spot_check_md = render_dedup_sample(sample)

    # Criterion 3: watchlist auto-update
    autos_in_window = db.query(
        "SELECT * FROM watchlist WHERE added_ts BETWEEN ? AND ? AND tags LIKE '%\"auto\"%'",
        since, until,
    )
    crit3 = len(autos_in_window) >= 1

    # Criterion 4: NO adapter restarts during the window
    nrestarts = check_systemctl_restarts(
        ["iic-sense-polygon", "iic-sense-telegram", "iic-sense-x",
         "iic-sense-rss", "iic-sense-gdelt", "iic-sense-macro",
         "iic-triage"],
        since,
    )
    crit4 = all(n == 0 for n in nrestarts.values())

    return ExitGateResult(
        events_total=len(events), duplicates=len(duplicates),
        autos=autos_in_window, restarts=nrestarts,
        spot_check_md=spot_check_md,
        passed_auto=crit1 and crit3 and crit4,
        passed_spot_check=None,  # human signs off in artifact
    )
```

Output artifact at `docs/superpowers/artifacts/2026-MM-DD-f3-exit-gate-report.md` containing:
- Summary counts and per-source breakdown
- Per-adapter restart counts (must be all zero)
- The dedup spot-check sample (30 rows with original + duplicate side-by-side)
- A human sign-off line: `Spot-check pass (≥24/30 are genuine duplicates): YES / NO — <reviewer notes>`
- The auto-promoted watchlist rows that appeared during the window

The 80% criterion is explicitly an **operator-signed manual review** — that matches the program spec's "(manual spot-check on a sample)" wording.

## 10 · Cost and operational notes

### Estimated cost during the 24h gate run

- Salience LLM (DeepSeek `quick_think_llm`): ~$0.0005 × ~100 events ≈ $0.05.
- Embeddings (dedupe stage 2): ~$0.00001 × ~70 surviving items ≈ $0.0007.
- External-source APIs: Polygon (free dev tier), GDELT (free), FRED (free), TradingEconomics (free), Telegram (free), X (depends on access tier — may be the cost outlier).

Total expected gate cost: **under $0.10** even with comfortable buffer for X access.

### Pre-flight checklist for the 24h run

Lives at `ops/runbooks/f3-exit-gate.md`. Headlines:

1. Dev machine on AC power. `systemd-inhibit --what=sleep --who="F3 exit gate" --why="24h sensing soak" sleep infinity &` running.
2. Screen lock + display sleep disabled for the run window.
3. All six adapters configured (env vars set; baseline channel/feed lists populated).
4. Redis up, AOF confirmed via `redis-cli config get appendonly`.
5. `tickers` table seeded; row count ≥ 8000 (or skip the gate).
6. Baseline `watchlist` set via `forge watchlist add` for the user's standing tickers.
7. Pre-soak: 1-hour dry run for each adapter individually. Each must produce ≥1 event with no `NRestarts`. If any fails, fix before the 24h attempt.
8. Start time recorded; `--since` value of the evaluator matches.
9. Disable auto-sleep at the OS level too (`gnome-session-properties` or equivalent) as belt-and-braces.

### Logs

- Per-adapter: `/var/log/iic/sense-<source>.log` (systemd-managed rotation).
- Triage: `/var/log/iic/triage.log`.
- Watchlist sweep: `data/logs/watchlist-sweep.log` (appended by the sweep service).

### Backups

Two stores now. Single backup script (`ops/backup.sh`) does both: SQLite via `sqlite3 .backup`, Redis via `redis-cli BGREWRITEAOF` then `cp /var/lib/redis/appendonly.aof`. Daily cron.

## 11 · Risks (F3 additions to the program register)

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-F3-1 | An adapter has an unhandled exception path → systemd restarts it → exit gate fails | High | Defensive try/except inside the loop with exponential backoff; per-iteration timeout; pre-soak 1h-per-adapter dry run before the 24h attempt (item 7 in the checklist) |
| R-F3-2 | Salience LLM rate-limits on a burst, drops events | Med | Per-consumer async semaphore caps concurrent LLM calls; fall back to embedding-novelty as degraded salience signal with `salience_source='embed_fallback'` recorded on the event |
| R-F3-3 | X/Twitter API access in flux; adapter is the most fragile source | Med | X adapter ships behind per-source `enabled=false` config; exit gate doesn't require all 6 sources — 5 is fine if events ≥100 and dedup spot-check passes |
| R-F3-4 | LLM hallucinates tickers → wrong watchlist promotions | Low | Reference-table validation rejects unknown symbols; logged for later prompt-tightening |
| R-F3-5 | Embedding API outage breaks stage-2 dedupe | Low | Stage 1 still runs; stage 2 wraps in try/except, logs, falls through — events still write, just without semantic dedupe |
| R-F3-6 | Redis crashes mid-run; in-flight messages lost | Low (with AOF=everysec, ≤1s loss) | AOF=everysec + `noeviction`; adapters resume from cursor on the next batch so the gap is bounded |
| R-F3-7 | sqlite-vec embedding column grows without bound under continuous F3 ingest | Low at F3 volume; Med post-F5 | Embeddings on duplicates are stored once on the *original* event only; a daily compaction job (out of F3 scope, noted for F5) can prune embeddings of events older than N days |
| R-F3-8 | Dev-machine kernel update / mandatory reboot interrupts the 24h run | Med | Disable unattended-upgrades for the window; check `uptime` and pending reboot flag before starting; document in checklist |

## 12 · Out of scope

The following are deliberately not part of F3:

- **Automatic run-triggering on events** (F4) — events become *queryable*; F4 wires them to graph runs.
- **Brief delivery** (F5), including event alerts via Telegram or email.
- **Streamlit dashboard** over events / queue depth (F5).
- **Cost-guard enforcement** — measurement only per Appendix A of the program spec.
- **Reflection / post-hoc tuning of salience thresholds** — needs post-soak data; lives in a separate analysis pass after F3 runs for a week.
- **Sub-ticker entities** (options chains, FX pairs, on-chain events) — F3 covers US equities + top-20 crypto only.
- **GDELT GKG (knowledge graph) ingestion** — only the lighter doc-level feed in F3; GKG is heavy and adds a CSV-parsing dependency we don't need yet.
- **Backfill of historical events** — F3 is forward-only from the moment the adapters start.
- **Multi-language news sources** — English-language only for now; the LLM scoring prompt assumes English.
- **F0 OSINT Telegram channel list refactor** — F3 inherits the existing `telegram_channels` config; expansion is a separate task.

## 13 · Open questions deferred to implementation

1. **X adapter access tier.** Decide between filtered stream (requires elevated access) and polled search (lower-tier OK). May influence whether the X adapter ships in the F3 cut.
2. **Salience thresholds tuning.** 0.7 / 0.8 are starting values. After the 24h soak, plot the actual `(salience, ticker_confidence)` distribution and tune.
3. **GDELT polling interval.** GDELT updates every 15 min; we poll matching. If batch sizes are unwieldy (>100 docs per poll), drop to 30 min and increase per-batch dedup.
4. **Stage-2 dedupe cosine threshold (0.92).** Probably right for short-form news; might be too tight for long-form pieces where boilerplate inflates similarity. Re-tune from spot-check data.
5. **Macro adapter source priority.** FRED is reliable but US-centric; TradingEconomics is broader but rate-limited. Default to FRED-primary, TE-secondary; reconfirm with the operator at implementation.
6. **Telegram channel curation.** The current `telegram_channels` config has channels picked for F0 OSINT context. Auditing them for "useful for salience scoring" is a separate task; F3 ships with whatever F0 has.

---

*End of IIC-FORGE-06. The companion implementation plan (IIC-FORGE-06-plan) follows from `superpowers:writing-plans`.*
