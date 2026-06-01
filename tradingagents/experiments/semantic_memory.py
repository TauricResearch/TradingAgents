from __future__ import annotations

import hashlib
import math
import sqlite3
from pathlib import Path
from typing import Iterable


def embed_text(text: str, dimensions: int = 96) -> list[float]:
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class SemanticMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS situations (
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    situation TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    raw_return REAL,
                    alpha_return REAL,
                    reflection TEXT,
                    PRIMARY KEY (ticker, trade_date)
                )
                """
            )

    def store_decision(
        self, ticker: str, trade_date: str, rating: str, situation: str
    ) -> None:
        embedding = ",".join(str(value) for value in embed_text(situation))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO situations(ticker, trade_date, rating, situation, embedding)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ticker, trade_date) DO UPDATE SET
                    rating = excluded.rating,
                    situation = excluded.situation,
                    embedding = excluded.embedding
                """,
                (ticker, trade_date, rating, situation, embedding),
            )

    def resolve_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        reflection: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE situations
                SET raw_return = ?, alpha_return = ?, reflection = ?
                WHERE ticker = ? AND trade_date = ?
                """,
                (raw_return, alpha_return, reflection, ticker, trade_date),
            )

    def find_similar(self, ticker: str, situation: str, limit: int = 3) -> list[dict]:
        query = embed_text(situation)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM situations WHERE reflection IS NOT NULL"
            ).fetchall()
        matches = []
        for row in rows:
            embedding = [float(value) for value in row["embedding"].split(",")]
            item = dict(row)
            item["score"] = cosine_similarity(query, embedding)
            matches.append(item)
        matches.sort(key=lambda item: (item["score"], item["ticker"] == ticker), reverse=True)
        return matches[:limit]

    def resolved_entries(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM situations WHERE reflection IS NOT NULL ORDER BY trade_date"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def format_matches(matches: list[dict]) -> str:
        if not matches:
            return ""
        lines = ["Historically similar situations:"]
        for item in matches:
            lines.append(
                f"- {item['trade_date']} {item['ticker']} ({item['rating']}): "
                f"{item['situation']} Outcome: {item['raw_return']:+.1%}. "
                f"Lesson: {item['reflection']}"
            )
        return "\n".join(lines)
