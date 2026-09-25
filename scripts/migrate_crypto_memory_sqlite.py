#!/usr/bin/env python3
"""Migrate legacy crypto JSON/JSONL memory files into SQLite tables.

Example:
    python scripts/migrate_crypto_memory_sqlite.py \
        --memory-dir ~/.tradingagents/crypto_memory \
        --db ~/.tradingagents/crypto_memory/tradingagents.db \
        --reset
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from tradingagents.storage import SQLiteTradingStore


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _read_jsonl_many(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)
    return rows


def _reset_space(store: SQLiteTradingStore, user_id: str, memory_space_id: str) -> None:
    with store.connect() as conn:
        for table in (
            "memory_items",
            "paper_accounts",
            "paper_positions",
            "paper_trades",
            "scan_candidates",
            "pending_approvals",
            "processed_signal_keys",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE "
                + ("memory_space_id = ?" if table == "memory_items" else "user_id = ? AND memory_space_id = ?"),
                (memory_space_id,) if table == "memory_items" else (user_id, memory_space_id),
            )
        conn.execute("DELETE FROM dashboard_state WHERE user_id = ?", (user_id,))


def migrate(memory_dir: Path, db_path: Path, user_id: str, memory_space_id: str, reset: bool = False) -> Dict[str, int]:
    store = SQLiteTradingStore(db_path, user_id=user_id)
    if reset:
        _reset_space(store, user_id, memory_space_id)

    counts = {
        "raw": 0,
        "lessons": 0,
        "global": 0,
        "trades": 0,
        "candidates": 0,
        "approvals": 0,
        "positions": 0,
        "account": 0,
        "dashboard_state": 0,
    }

    state = _read_json(memory_dir / "dashboard_state.json", {})
    if isinstance(state, dict) and state:
        store.save_dashboard_state(user_id, state)
        counts["dashboard_state"] = 1

    for item in _read_jsonl_many([memory_dir / "raw.jsonl", memory_dir / "raw" / "raw.jsonl"]):
        store.append_memory("raw", item, memory_space_id=memory_space_id)
        counts["raw"] += 1
    for item in _read_jsonl_many([memory_dir / "lessons.jsonl", memory_dir / "lessons" / "lessons.jsonl"]):
        store.append_memory("lesson", item, memory_space_id=memory_space_id)
        counts["lessons"] += 1
    for item in _read_jsonl_many([memory_dir / "global.jsonl", memory_dir / "global" / "global.jsonl"]):
        store.append_memory("global", item, memory_space_id=memory_space_id)
        counts["global"] += 1

    paper_dir = memory_dir / "paper"
    account = _read_json(paper_dir / "account.json", {})
    if isinstance(account, dict) and account:
        store.save_account(user_id, memory_space_id, account)
        counts["account"] = 1

    positions = _read_json(paper_dir / "positions.json", [])
    if isinstance(positions, list):
        store.save_positions(user_id, memory_space_id, positions)
        counts["positions"] = len(positions)

    for trade in _read_jsonl_many([paper_dir / "trades.jsonl"]):
        store.append_trade(user_id, memory_space_id, trade)
        counts["trades"] += 1

    for candidate in _read_jsonl_many([paper_dir / "scan_candidates.jsonl"]):
        store.append_candidate(user_id, memory_space_id, candidate)
        counts["candidates"] += 1

    approvals = _read_json(paper_dir / "pending_approvals.json", [])
    if isinstance(approvals, list):
        store.save_approvals(user_id, memory_space_id, approvals)
        counts["approvals"] = len(approvals)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate TradingAgents crypto memory files to SQLite")
    parser.add_argument("--memory-dir", default="~/.tradingagents/crypto_memory")
    parser.add_argument("--db", default="~/.tradingagents/crypto_memory/tradingagents.db")
    parser.add_argument("--user-id", default="admin")
    parser.add_argument("--memory-space-id", default="default")
    parser.add_argument("--reset", action="store_true", help="Clear existing rows for this user/memory space before importing")
    args = parser.parse_args()

    counts = migrate(
        Path(args.memory_dir).expanduser(),
        Path(args.db).expanduser(),
        user_id=args.user_id,
        memory_space_id=args.memory_space_id,
        reset=args.reset,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
