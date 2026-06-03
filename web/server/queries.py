"""Read-side helpers that shape persisted data for the API layer.

Pure functions on top of ``storage``; no FastAPI types here. This split
keeps the low-level IO testable independently of the API.
"""
from __future__ import annotations

from datetime import datetime

from tradingagents.dataflows.utils import safe_ticker_component

from web.server import storage


class DuplicateTicker(Exception):
    pass


# ---- watchlist ----

def read_watchlist() -> list[dict]:
    """Return the watchlist rows, sorted by added_at ascending."""
    rows = storage.read_json(storage.data_dir() / "watchlist.json")
    if not rows:
        return []
    return rows.get("tickers", [])


def _write_watchlist(rows: list[dict]) -> None:
    storage.write_json_atomic(
        storage.data_dir() / "watchlist.json",
        {"version": 1, "tickers": rows},
    )


def add_ticker(ticker: str, company_name: str, exchange: str) -> dict:
    """Add a ticker to the watchlist. Raises DuplicateTicker if present."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    if any(r["ticker"] == safe for r in rows):
        raise DuplicateTicker(safe)
    row = {
        "ticker": safe,
        "company_name": company_name,
        "exchange": exchange,
        "added_at": storage.utc_iso(storage.now_utc()),
        "last_run_id": None,
        "last_decision": None,
        "last_decision_at": None,
    }
    rows.append(row)
    _write_watchlist(rows)
    # Make sure the ticker data dir exists so the next /api/runs call
    # can drop its run subdir in there.
    storage.ticker_dir(safe)
    return row


def remove_ticker(ticker: str) -> None:
    """Remove the ticker from the watchlist and delete its analysis data."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    next_rows = [r for r in rows if r["ticker"] != safe]
    if next_rows == rows:
        return  # not present; nothing to do
    _write_watchlist(next_rows)
    storage.clear_ticker_data(safe)


def update_last_decision(ticker: str, run_id: str, decision_text: str, at: datetime) -> None:
    """Set the watchlist row's last_decision_* fields. No-op if ticker is gone."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    changed = False
    for r in rows:
        if r["ticker"] == safe:
            r["last_run_id"] = run_id
            r["last_decision"] = decision_text
            r["last_decision_at"] = storage.utc_iso(at)
            changed = True
    if changed:
        _write_watchlist(rows)


# ---- run queries (shape persisted run.json + events.jsonl for the API) ----

def run_to_dict(r: dict) -> dict:
    """Shape a stored run.json for the API. Keeps the wire format stable."""
    return {
        "id": r.get("id"),
        "ticker": r.get("ticker"),
        "slug": r.get("slug"),
        "started_at": r.get("started_at"),
        "finished_at": r.get("finished_at"),
        "status": r.get("status"),
        "decision_action": r.get("decision_action"),
        "decision_target": r.get("decision_target"),
        "decision_rationale": r.get("decision_rationale"),
        "decision_confidence": r.get("decision_confidence"),
    }


def event_to_dict(e: dict, run_id: str) -> dict:
    """Shape a stored events.jsonl line for the API."""
    return {
        "id": e.get("id"),
        "type": e.get("type"),
        "ts": e.get("ts"),
        "data": e.get("data", {}),
        "run_id": run_id,
    }


def llm_call_to_dict(c: dict) -> dict:
    """Shape a stored llm_calls.jsonl line for the API."""
    return {
        "id": c.get("id"),
        "run_id": c.get("run_id"),
        "ticker": c.get("ticker"),
        "node_name": c.get("node_name", ""),
        "started_at": c.get("started_at"),
        "model": c.get("model", ""),
        "prompt_text": c.get("prompt_text", ""),
        "response_text": c.get("response_text", ""),
        "tool_calls": c.get("tool_calls", []),
        "input_tokens": c.get("input_tokens", 0),
        "output_tokens": c.get("output_tokens", 0),
        "total_tokens": c.get("total_tokens", 0),
        "duration_ms": c.get("duration_ms", 0),
    }
