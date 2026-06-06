from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def create_analysis_pack(
    *,
    conn: sqlite3.Connection,
    data_dir: Path,
    event_id: str | None,
    ticker: str,
    trade_date: str,
    source_run_ids: list[str],
    content: dict[str, Any],
) -> str:
    pack_id = uuid.uuid4().hex
    rel_path = Path("analysis_packs") / f"{pack_id}.json"
    abs_path = data_dir / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        json.dumps(content, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    conn.execute(
        "INSERT INTO analysis_packs "
        "(pack_id, event_id, ticker, trade_date, source_run_ids, content_path, "
        "created_ts, version) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (
            pack_id,
            event_id,
            ticker,
            trade_date,
            json.dumps(source_run_ids),
            str(rel_path),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return pack_id


def load_analysis_pack(
    *,
    conn: sqlite3.Connection,
    data_dir: Path,
    pack_id: str,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM analysis_packs WHERE pack_id = ?",
        (pack_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"analysis pack not found: {pack_id}")
    content = json.loads((data_dir / row["content_path"]).read_text(encoding="utf-8"))
    return {
        "pack_id": row["pack_id"],
        "event_id": row["event_id"],
        "ticker": row["ticker"],
        "trade_date": row["trade_date"],
        "source_run_ids": json.loads(row["source_run_ids"]),
        "content_path": row["content_path"],
        "created_ts": row["created_ts"],
        "version": row["version"],
        "content": content,
    }
