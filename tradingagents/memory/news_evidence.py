"""SQLite-backed canonical store for news evidence records.

This is the canonical provenance layer for news analysis. It persists
article-level records with stable evidence IDs so agent outputs can later
reference exact stored evidence rather than inventing source labels from
prompt text alone.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from tradingagents.default_config import DEFAULT_CONFIG, get_env_value


@dataclass(frozen=True)
class NewsEvidenceRecord:
    run_id: str
    evidence_id: str
    ticker: str
    trade_date: str
    section_label: str
    ordinal: int
    source: str
    published_at: str
    title: str
    url: str
    summary: str
    raw_json: str


def _default_db_path() -> Path:
    override = get_env_value("TRADINGAGENTS_NEWS_EVIDENCE_DB")
    if override:
        return Path(override)
    results_dir = Path(str(DEFAULT_CONFIG.get("results_dir", "./reports")))
    return results_dir / "news_evidence.sqlite3"


class NewsEvidenceStore:
    """Persist and retrieve article evidence using sqlite3."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS news_articles (
                    article_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS news_run_articles (
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    section_label TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    article_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, ticker, section_label, article_id),
                    FOREIGN KEY(article_id) REFERENCES news_articles(article_id)
                );
                CREATE INDEX IF NOT EXISTS idx_news_run_articles_lookup
                ON news_run_articles (run_id, ticker, trade_date, section_label, ordinal);
                """
            )

    def ingest_prefetched_sections(
        self,
        *,
        run_id: str,
        ticker: str,
        trade_date: str,
        prefetched: dict[str, str],
    ) -> list[NewsEvidenceRecord]:
        records: list[NewsEvidenceRecord] = []
        ticker_upper = str(ticker or "").upper()
        for section_label, payload in prefetched.items():
            for index, article in enumerate(_extract_articles(payload), start=1):
                record = _build_record(
                    run_id=run_id,
                    ticker=ticker_upper,
                    trade_date=trade_date,
                    section_label=section_label,
                    article=article,
                    ordinal=index,
                )
                if record is None:
                    continue
                self._upsert_record(record)
                records.append(record)
        return records

    def fetch_records(
        self,
        *,
        run_id: str,
        ticker: str,
        trade_date: str | None = None,
    ) -> list[NewsEvidenceRecord]:
        query = """
            SELECT r.run_id, a.article_id AS evidence_id, r.ticker, r.trade_date,
                   r.section_label, r.ordinal, a.source, a.published_at,
                   a.title, a.url, a.summary, a.raw_json
            FROM news_run_articles r
            JOIN news_articles a ON a.article_id = r.article_id
            WHERE r.run_id = ? AND r.ticker = ?
        """
        params: list[str] = [run_id, ticker.upper()]
        if trade_date:
            query += " AND r.trade_date = ?"
            params.append(trade_date)
        query += " ORDER BY r.section_label ASC, r.ordinal ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            NewsEvidenceRecord(
                run_id=row["run_id"],
                evidence_id=row["evidence_id"],
                ticker=row["ticker"],
                trade_date=row["trade_date"],
                section_label=row["section_label"],
                ordinal=int(row["ordinal"]),
                source=row["source"],
                published_at=row["published_at"],
                title=row["title"],
                url=row["url"],
                summary=row["summary"],
                raw_json=row["raw_json"],
            )
            for row in rows
        ]

    def build_prompt_context(self, records: Iterable[NewsEvidenceRecord]) -> str:
        records = list(records)
        lines = [
            "## Evidence Records",
            "",
            "These are SQLite-backed evidence records persisted for this run.",
            "Use the evidence IDs below to ground claims when possible. Evidence IDs are not a replacement for source/date citations; they are traceability handles.",
            "",
        ]
        if not records:
            lines.append("_No persisted evidence records available._")
            return "\n".join(lines).strip()
        for record in records:
            lines.append(
                f"- [Evidence ID: {record.evidence_id}] "
                f"Source: {record.source} | Published: {record.published_at} | "
                f"Section: {record.section_label} | Ordinal: {record.ordinal} | Title: {record.title}"
            )
        return "\n".join(lines).strip()

    def _upsert_record(self, record: NewsEvidenceRecord) -> None:
        article_id = _make_article_id(
            source=record.source,
            title=record.title,
            url=record.url,
            published_at=record.published_at,
        )
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO news_articles (
                    article_id, source, published_at, title, url, summary,
                    raw_json, content_hash, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    summary = excluded.summary,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    article_id,
                    record.source,
                    record.published_at,
                    record.title,
                    record.url,
                    record.summary,
                    record.raw_json,
                    article_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO news_run_articles (
                    run_id, ticker, trade_date, section_label, ordinal, article_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, ticker, section_label, article_id) DO UPDATE SET
                    ordinal = excluded.ordinal
                """,
                (
                    record.run_id,
                    record.ticker,
                    record.trade_date,
                    record.section_label,
                    record.ordinal,
                    article_id,
                    now,
                ),
            )


def _extract_articles(payload: str) -> list[dict]:
    try:
        parsed = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return []
    feed = parsed.get("feed")
    if not isinstance(feed, list):
        return []
    return [article for article in feed if isinstance(article, dict)]


def _build_record(
    *,
    run_id: str,
    ticker: str,
    trade_date: str,
    section_label: str,
    article: dict,
    ordinal: int,
) -> NewsEvidenceRecord | None:
    title = str(article.get("title") or "").strip()
    source = str(
        article.get("source")
        or article.get("source_domain")
        or "Unknown"
    ).strip()
    url = str(article.get("url") or "").strip()
    published_at = _normalize_published_at(
        article.get("time_published") or article.get("published_at") or trade_date
    )
    summary = str(article.get("summary") or "").strip()

    if not title:
        return None

    evidence_id = _make_article_id(
        source=source,
        title=title,
        url=url,
        published_at=published_at,
    )
    return NewsEvidenceRecord(
        run_id=run_id,
        evidence_id=evidence_id,
        ticker=ticker,
        trade_date=trade_date,
        section_label=section_label,
        ordinal=ordinal,
        source=source,
        published_at=published_at,
        title=title,
        url=url,
        summary=summary,
        raw_json=json.dumps(article, sort_keys=True),
    )


def _normalize_published_at(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "N/A"
    if re.fullmatch(r"\d{8}T\d{6}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def _make_article_id(
    *,
    source: str,
    title: str,
    url: str,
    published_at: str,
) -> str:
    normalized_parts = [
        re.sub(r"\s+", " ", str(source or "").strip().lower()),
        re.sub(r"\s+", " ", str(title or "").strip().lower()),
        str(url or "").strip().lower(),
        str(published_at or "").strip().lower(),
    ]
    raw = "|".join(normalized_parts)
    return f"art_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"
