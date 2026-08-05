"""Storage backend for accumulated social/news media (the poller's data store).

The poller appends one row per message/post and dedups on ``(source,
external_id)`` so overlapping polls don't double-count. For local use the
default is a SQLite file (stdlib, zero extra dependencies). For cloud hosting —
where a container's local disk is ephemeral — point ``MEDIA_DB_URL`` at a
managed database (e.g. Postgres) and the same code persists there instead:

    MEDIA_DB_URL=postgresql+psycopg://user:pass@host:5432/trading

Non-SQLite URLs require the optional extra: ``pip install 'tradingagents[poller]'``.

Both backends expose the same interface — ``store()``, ``stats()``,
``window()`` — so the poller and the (future) backtest loader are agnostic to
where the data lives. ``window()`` returns the look-ahead-safe slice a backtest
at a given trade date should feed the analysts.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Column order is the single source of truth shared by both backends and the
# fetchers in media_sources (which emit dicts with exactly these keys).
COLUMNS = (
    "source", "external_id", "ticker", "subreddit", "author", "sentiment",
    "created_utc", "title", "body", "fetched_utc",
)

# Prediction-market odds are a time series: the same market is re-captured each
# cycle, so the row key is (market_id, captured_utc), not a static id.
ODDS_COLUMNS = (
    "theme", "topic", "market_id", "captured_utc",
    "question", "probability", "volume", "resolution_utc",
)


def _odds_asof_sql(theme_clause: str) -> str:
    """Latest snapshot per market with captured_utc <= :hi. Standard SQL
    (correlated subquery), so it runs unchanged on SQLite and Postgres."""
    return (
        f"SELECT {','.join(ODDS_COLUMNS)} FROM macro_odds o "
        "WHERE captured_utc <= :hi AND captured_utc = "
        "(SELECT MAX(captured_utc) FROM macro_odds o2 "
        " WHERE o2.market_id = o.market_id AND o2.captured_utc <= :hi) "
        f"{theme_clause} ORDER BY volume DESC"
    )


def _midnight_epoch(end: str) -> float:
    """``end`` at 00:00 UTC — the look-ahead-safe upper bound for an as-of read."""
    return datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


_DEFAULT_SQLITE_PATH = Path.home() / ".tradingagents" / "cache" / "media.db"


def _normalize_pg_url(url: str) -> str:
    """Rewrite Postgres URLs to the installed psycopg (v3) driver.

    Fly Managed Postgres / Heroku hand out ``postgres://…``, and a plain
    ``postgresql://…`` makes SQLAlchemy default to psycopg2 (which we don't
    install). Both become ``postgresql+psycopg://…`` so the connection string a
    provider gives you works unedited.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def open_store(url: str | None = None):
    """Open the media store named by ``url`` (or ``$MEDIA_DB_URL`` /
    ``$DATABASE_URL``, or the local default SQLite file). Bare paths and
    ``sqlite:///…`` URLs use the stdlib SQLite backend; any other scheme uses
    the SQLAlchemy backend. ``DATABASE_URL`` is read so a Fly Managed Postgres
    ``fly mpg attach`` (which sets it) works with no extra config.
    """
    import os

    url = (url or os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return SqliteMediaStore(_DEFAULT_SQLITE_PATH)
    if url.startswith("sqlite:///"):
        return SqliteMediaStore(Path(url[len("sqlite:///"):]))
    if "://" not in url:  # bare filesystem path
        return SqliteMediaStore(Path(url))
    return SqlAlchemyMediaStore(_normalize_pg_url(url))


def _window_bounds(end: str, days: int) -> tuple[float, float]:
    """[end - days, end] as UTC epoch seconds, with ``end`` at 00:00 UTC.

    A decision *made on* the trade date should not see that day's later intraday
    chatter, so the upper bound is midnight of ``end`` — look-ahead-safe.
    """
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (end_dt - timedelta(days=days)).timestamp(), end_dt.timestamp()


def _history_bounds(start: str, end: str) -> tuple[float, float]:
    """UTC bounds for an after-close decision on ``end``.

    The graph's market tools include the ``end`` session's closing bar, so a
    backtest decision is timestamped after that close and entered next session.
    Media published *and fetched* before the next UTC midnight is eligible.
    """
    lo = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    hi = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    return lo.timestamp(), hi.timestamp()


class SqliteMediaStore:
    """Local SQLite backend (stdlib ``sqlite3``, no extra dependencies)."""

    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_posts (
                source TEXT NOT NULL, external_id TEXT NOT NULL, ticker TEXT NOT NULL,
                subreddit TEXT, author TEXT, sentiment TEXT, created_utc REAL,
                title TEXT, body TEXT, fetched_utc REAL NOT NULL,
                PRIMARY KEY (source, external_id)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticker_time ON media_posts (ticker, created_utc)"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_odds (
                theme TEXT, topic TEXT, market_id TEXT NOT NULL, captured_utc REAL NOT NULL,
                question TEXT, probability REAL, volume REAL, resolution_utc REAL,
                PRIMARY KEY (market_id, captured_utc)
            )
            """
        )
        # Small key/value table for poller bookkeeping (e.g. last_poll_utc), so
        # the incremental window survives process restarts (Fly redeploys/crashes).
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS poll_state (key TEXT PRIMARY KEY, value REAL)"
        )
        self.conn.commit()

    def store(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            f"INSERT OR IGNORE INTO media_posts ({','.join(COLUMNS)}) "
            f"VALUES ({','.join(':' + c for c in COLUMNS)})",
            rows,
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def stats(self) -> list[tuple]:
        return self.conn.execute(
            "SELECT ticker, source, COUNT(*), MIN(created_utc), MAX(created_utc) "
            "FROM media_posts GROUP BY ticker, source ORDER BY ticker, source"
        ).fetchall()

    def window(self, ticker: str, end: str, days: int) -> list[dict]:
        lo, hi = _window_bounds(end, days)
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT * FROM media_posts WHERE ticker = ? AND created_utc >= ? "
            "AND created_utc <= ? ORDER BY created_utc",
            (ticker.upper(), lo, hi),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    def history_asof(
        self,
        start: str,
        end: str,
        *,
        tickers: list[str] | None = None,
        ticker_prefixes: list[str] | None = None,
        sources: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Rows known by the end-of-day cutoff, newest first.

        Both ``created_utc`` and ``fetched_utc`` are constrained. The latter is
        essential: an old article first discovered today was not available to
        a historical decision and must not leak into a backtest.
        """
        lo, hi = _history_bounds(start, end)
        clauses = ["created_utc >= ?", "created_utc < ?", "fetched_utc < ?"]
        params: list = [lo, hi, hi]
        identity_clauses = []
        if tickers:
            marks = ",".join("?" for _ in tickers)
            identity_clauses.append(f"ticker IN ({marks})")
            params.extend(ticker.upper() for ticker in tickers)
        if ticker_prefixes:
            identity_clauses.extend("ticker LIKE ?" for _ in ticker_prefixes)
            params.extend(prefix.upper() + "%" for prefix in ticker_prefixes)
        if identity_clauses:
            clauses.append("(" + " OR ".join(identity_clauses) + ")")
        if sources:
            marks = ",".join("?" for _ in sources)
            clauses.append(f"source IN ({marks})")
            params.extend(sources)
        params.append(max(1, limit))
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT * FROM media_posts WHERE " + " AND ".join(clauses)
            + " ORDER BY created_utc DESC LIMIT ?",
            params,
        ).fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def store_odds(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            f"INSERT OR IGNORE INTO macro_odds ({','.join(ODDS_COLUMNS)}) "
            f"VALUES ({','.join(':' + c for c in ODDS_COLUMNS)})",
            rows,
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def odds_asof(self, end: str, themes: list[str] | None = None) -> list[dict]:
        params = {"hi": _midnight_epoch(end)}
        clause = ""
        if themes:
            marks = ",".join(f":t{i}" for i in range(len(themes)))
            clause = f"AND o.theme IN ({marks})"
            params.update({f"t{i}": t for i, t in enumerate(themes)})
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(_odds_asof_sql(clause), params).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    def odds_stats(self) -> list[tuple]:
        return self.conn.execute(
            "SELECT theme, COUNT(DISTINCT market_id), COUNT(*), "
            "MIN(captured_utc), MAX(captured_utc) "
            "FROM macro_odds GROUP BY theme ORDER BY theme"
        ).fetchall()

    def get_meta(self, key: str) -> float | None:
        row = self.conn.execute(
            "SELECT value FROM poll_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: float) -> None:
        self.conn.execute(
            "INSERT INTO poll_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


class SqlAlchemyMediaStore:
    """SQLAlchemy backend for networked databases (Postgres, etc.).

    Uses dialect-aware ``INSERT … ON CONFLICT DO NOTHING`` for dedup, which
    SQLite (3.24+) and Postgres both support. ``pool_pre_ping`` keeps a
    long-running poller resilient to idle connection drops on managed DBs.
    """

    def __init__(self, url: str):
        try:
            from sqlalchemy import (  # noqa: I001 — grouped for readability
                Column,
                Float,
                Index,
                MetaData,
                String,
                Table,
                create_engine,
            )
        except ImportError as exc:
            raise RuntimeError(
                f"MEDIA_DB_URL={url!r} needs SQLAlchemy + a driver. "
                "Install the optional extra: pip install 'tradingagents[poller]'"
            ) from exc

        self.engine = create_engine(url, pool_pre_ping=True)
        self.dialect = self.engine.dialect.name
        if self.dialect not in ("postgresql", "sqlite"):
            logger.warning("media store: dedup-on-conflict is verified for postgresql/"
                           "sqlite; %r may behave differently.", self.dialect)
        md = MetaData()
        self.table = Table(
            "media_posts", md,
            Column("source", String, primary_key=True),
            Column("external_id", String, primary_key=True),
            Column("ticker", String, nullable=False),
            Column("subreddit", String), Column("author", String),
            Column("sentiment", String), Column("created_utc", Float),
            Column("title", String), Column("body", String),
            Column("fetched_utc", Float, nullable=False),
        )
        Index("idx_ticker_time", self.table.c.ticker, self.table.c.created_utc)
        self.odds = Table(
            "macro_odds", md,
            Column("theme", String), Column("topic", String),
            Column("market_id", String, primary_key=True),
            Column("captured_utc", Float, primary_key=True),
            Column("question", String), Column("probability", Float),
            Column("volume", Float), Column("resolution_utc", Float),
        )
        self.state = Table(
            "poll_state", md,
            Column("key", String, primary_key=True), Column("value", Float),
        )
        md.create_all(self.engine)

    def _insert_stmt(self, table, conflict_cols):
        if self.dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        return insert(table).on_conflict_do_nothing(index_elements=conflict_cols)

    def _upsert(self, table, conflict_cols, rows: list[dict]) -> int:
        if not rows:
            return 0
        # psycopg may report ``rowcount == -1`` for INSERT ... ON CONFLICT,
        # even when the insert succeeds. RETURNING is reliable on both
        # PostgreSQL and modern SQLite: inserted rows return a key, conflicts
        # return no row.
        stmt = self._insert_stmt(table, conflict_cols).returning(
            table.c[conflict_cols[0]]
        )
        new = 0
        # Row-by-row in one transaction; batches are intentionally small.
        with self.engine.begin() as conn:
            for r in rows:
                if conn.execute(stmt, r).first() is not None:
                    new += 1
        return new

    def store(self, rows: list[dict]) -> int:
        return self._upsert(self.table, ["source", "external_id"], rows)

    def store_odds(self, rows: list[dict]) -> int:
        return self._upsert(self.odds, ["market_id", "captured_utc"], rows)

    def stats(self) -> list[tuple]:
        from sqlalchemy import func, select
        t = self.table
        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(
                select(t.c.ticker, t.c.source, func.count(),
                       func.min(t.c.created_utc), func.max(t.c.created_utc))
                .group_by(t.c.ticker, t.c.source).order_by(t.c.ticker, t.c.source)
            ).all()]

    def window(self, ticker: str, end: str, days: int) -> list[dict]:
        from sqlalchemy import select
        lo, hi = _window_bounds(end, days)
        t = self.table
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t).where(t.c.ticker == ticker.upper())
                .where(t.c.created_utc >= lo).where(t.c.created_utc <= hi)
                .order_by(t.c.created_utc)
            ).mappings().all()
        return [dict(r) for r in rows]

    def history_asof(
        self,
        start: str,
        end: str,
        *,
        tickers: list[str] | None = None,
        ticker_prefixes: list[str] | None = None,
        sources: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict]:
        from sqlalchemy import or_, select

        lo, hi = _history_bounds(start, end)
        t = self.table
        stmt = (
            select(t)
            .where(t.c.created_utc >= lo)
            .where(t.c.created_utc < hi)
            .where(t.c.fetched_utc < hi)
        )
        identities = []
        if tickers:
            identities.append(t.c.ticker.in_([ticker.upper() for ticker in tickers]))
        if ticker_prefixes:
            identities.extend(
                t.c.ticker.like(prefix.upper() + "%") for prefix in ticker_prefixes
            )
        if identities:
            stmt = stmt.where(or_(*identities))
        if sources:
            stmt = stmt.where(t.c.source.in_(sources))
        stmt = stmt.order_by(t.c.created_utc.desc()).limit(max(1, limit))
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(row) for row in rows]

    def odds_asof(self, end: str, themes: list[str] | None = None) -> list[dict]:
        from sqlalchemy import text
        params = {"hi": _midnight_epoch(end)}
        clause = ""
        if themes:
            marks = ",".join(f":t{i}" for i in range(len(themes)))
            clause = f"AND o.theme IN ({marks})"
            params.update({f"t{i}": t for i, t in enumerate(themes)})
        with self.engine.connect() as conn:
            rows = conn.execute(text(_odds_asof_sql(clause)), params).mappings().all()
        return [dict(r) for r in rows]

    def odds_stats(self) -> list[tuple]:
        from sqlalchemy import distinct, func, select
        o = self.odds
        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(
                select(o.c.theme, func.count(distinct(o.c.market_id)), func.count(),
                       func.min(o.c.captured_utc), func.max(o.c.captured_utc))
                .group_by(o.c.theme).order_by(o.c.theme)
            ).all()]

    def get_meta(self, key: str) -> float | None:
        from sqlalchemy import select
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.state.c.value).where(self.state.c.key == key)
            ).first()
        return row[0] if row else None

    def set_meta(self, key: str, value: float) -> None:
        from sqlalchemy import update
        with self.engine.begin() as conn:
            res = conn.execute(
                update(self.state).where(self.state.c.key == key).values(value=value)
            )
            if res.rowcount == 0:
                conn.execute(self.state.insert().values(key=key, value=value))

    def close(self):
        self.engine.dispose()
