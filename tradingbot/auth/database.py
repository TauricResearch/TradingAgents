"""SQLite persistence layer for user accounts."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UserRecord:
    id: int
    username: str
    phone: str
    email: Optional[str]
    password_hash: str
    salt: str
    created_at: str


class UserDatabase:
    """
    Thin SQLite wrapper for user accounts.

    Uses standard library sqlite3 (no extra deps), matching PortfolioDatabase style.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT    NOT NULL UNIQUE,
        phone           TEXT    NOT NULL UNIQUE,
        email           TEXT,
        password_hash   TEXT    NOT NULL,
        salt            TEXT    NOT NULL,
        created_at      TEXT    NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info("UserDatabase ready at %s", db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)

    # ------------------------------------------------------------------ #
    # CRUD                                                                 #
    # ------------------------------------------------------------------ #

    def insert_user(
        self,
        username: str,
        phone: str,
        email: Optional[str],
        password_hash: str,
        salt: str,
    ) -> UserRecord:
        sql = """
        INSERT INTO users (username, phone, email, password_hash, salt, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        created_at = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                sql, (username, phone, email, password_hash, salt, created_at)
            )
            uid = cur.lastrowid
        return UserRecord(
            id=uid,
            username=username,
            phone=phone,
            email=email,
            password_hash=password_hash,
            salt=salt,
            created_at=created_at,
        )

    def get_by_username(self, username: str) -> Optional[UserRecord]:
        return self._fetch_one("SELECT * FROM users WHERE username = ?", (username,))

    def get_by_phone(self, phone: str) -> Optional[UserRecord]:
        return self._fetch_one("SELECT * FROM users WHERE phone = ?", (phone,))

    def _fetch_one(self, sql: str, params: tuple) -> Optional[UserRecord]:
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_user(row) if row else None

    def _row_to_user(self, row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            username=row["username"],
            phone=row["phone"],
            email=row["email"],
            password_hash=row["password_hash"],
            salt=row["salt"],
            created_at=row["created_at"],
        )
