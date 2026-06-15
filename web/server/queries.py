"""Read-side helpers that shape persisted data for the API layer.

Pure functions on top of ``storage``; no FastAPI types here. This split
keeps the low-level IO testable independently of the API.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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
        {"version": 2, "tickers": rows},
    )


def add_ticker(ticker: str, company_name: str, exchange: str) -> dict:
    """Add a ticker to the watchlist. Raises DuplicateTicker if present."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    if any(r["ticker"] == safe for r in rows):
        raise DuplicateTicker(safe)
    next_order = max((r.get("sort_order", i) for i, r in enumerate(rows)), default=0) + 1
    row = {
        "ticker": safe,
        "company_name": company_name,
        "exchange": exchange,
        "added_at": storage.utc_iso(storage.now_utc()),
        "last_run_id": None,
        "last_decision": None,
        "last_decision_at": None,
        "sort_order": next_order,
        "group": None,
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


def watchlist_to_dict(w: dict) -> dict:
    """Shape a stored watchlist row for the API."""
    return {
        "ticker": w.get("ticker"),
        "company_name": w.get("company_name"),
        "exchange": w.get("exchange"),
        "added_at": w.get("added_at"),
        "last_run_id": w.get("last_run_id"),
        "last_decision": w.get("last_decision"),
        "last_decision_at": w.get("last_decision_at"),
        "sort_order": w.get("sort_order"),
        "group": w.get("group"),
    }


def update_watchlist_item(ticker: str, group: str | None = None, sort_order: int | None = None) -> dict | None:
    """Update group and/or sort_order for a single watchlist item. Returns the updated row or None."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    for r in rows:
        if r["ticker"] == safe:
            if group is not None:
                r["group"] = group if group else None
            if sort_order is not None:
                r["sort_order"] = sort_order
            _write_watchlist(rows)
            return r
    return None


def reorder_watchlist(tickers: list[str]) -> list[dict]:
    """Reorder the watchlist array to match the given ticker order.

    Items not in ``tickers`` are appended at the end in their current relative
    order. This ensures deletions don't silently drop items.
    """
    safe_tickers = [safe_ticker_component(t).upper() for t in tickers]
    rows = read_watchlist()
    ordered = []
    seen = set()
    for t in safe_tickers:
        for r in rows:
            if r["ticker"] == t and t not in seen:
                ordered.append(r)
                seen.add(t)
                break
    # Append any remaining (e.g. newly added tickers not yet in the client)
    for r in rows:
        if r["ticker"] not in seen:
            ordered.append(r)
    # Re-assign sort_order to match the new array positions
    for i, r in enumerate(ordered):
        r["sort_order"] = i
    _write_watchlist(ordered)
    return ordered


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
    elapsed_s: Optional[float] = None
    started_at = _parse_iso_z(r.get("started_at") or "")
    if started_at is not None:
        finished_str = r.get("finished_at")
        if finished_str:
            finished_at = _parse_iso_z(finished_str)
            if finished_at is not None:
                elapsed_s = round((finished_at - started_at).total_seconds(), 2)
        else:
            elapsed_s = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)

    return {
        "id": r.get("id"),
        "ticker": r.get("ticker"),
        "slug": r.get("slug"),
        "started_at": r.get("started_at"),
        "finished_at": r.get("finished_at"),
        "status": r.get("status"),
        "llm_provider": r.get("llm_provider"),
        "deep_think_model": r.get("deep_think_model"),
        "quick_think_model": r.get("quick_think_model"),
        "start_price": r.get("start_price"),
        "start_price_at": r.get("start_price_at"),
        "total_duration_s": r.get("total_duration_s"),
        "elapsed_s": elapsed_s,
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
        "tool_calls": c.get("tool_calls_json", []),
        "input_tokens": c.get("input_tokens", 0),
        "output_tokens": c.get("output_tokens", 0),
        "total_tokens": c.get("total_tokens", 0),
        "duration_ms": c.get("duration_ms", 0),
    }


# ---- transparency helpers: trace + health ----

# How long a "running" run with no events is considered stuck. Tuned
# generously: a single LLM call can easily take 60-120s on a slow
# provider, and a multi-agent stage chain can have multi-minute gaps.
_RUN_STALE_AFTER_S = 300.0


def build_trace(run_id: str, *, since: str = "", limit: int = 500,
                kinds: Optional[set[str]] = None) -> dict:
    """Merge a run's events + stages + llm calls into one chronological timeline.

    Items are sorted ascending by timestamp (events have ``ts``; stages
    have ``completed_at``; LLM calls have ``started_at`` — all ISO-8601
    with ``Z`` suffix, so plain string comparison is correct).

    Filters:
      - ``since``: skip items whose timestamp is <= this value
        (inclusive). Use the ``id`` of the last item the client already
        received to do a live tail.
      - ``limit``: cap the number of returned items (default 500).
      - ``kinds``: subset of ``{"event", "stage", "llm_call"}`` to
        include; default is all three.

    Each item carries a ``kind`` discriminator and a ``ts`` field; the
    shape of the rest is per-kind (see the per-builder code below).
    """
    rd = storage.read_run_dir(run_id)
    if rd is None:
        return {"run_id": run_id, "items": [], "count": 0, "truncated": False}

    want_events = kinds is None or "event" in kinds
    want_stages = kinds is None or "stage" in kinds
    want_llm = kinds is None or "llm_call" in kinds

    items: list[dict] = []

    if want_events:
        for e in storage.list_run_events(run_id):
            items.append({
                "kind": "event",
                "ts": e.get("ts") or "",
                "id": e.get("id") or "",
                "type": e.get("type") or "",
                "data": e.get("data") or {},
            })
    if want_stages:
        for sp in sorted((rd / "stages").glob("*.json")):
            d = storage.read_json(sp) or {}
            items.append({
                "kind": "stage",
                "ts": d.get("completed_at") or "",
                "stage": d.get("stage") or sp.stem,
                "node": d.get("node") or "",
                "duration_ms": d.get("duration_ms") or 0,
                "value": d.get("value") or "",
            })
    if want_llm:
        for c in storage.list_run_llm_calls(run_id):
            items.append({
                "kind": "llm_call",
                "ts": c.get("started_at") or "",
                "id": c.get("id") or "",
                "node_name": c.get("node_name") or "",
                "model": c.get("model") or "",
                "duration_ms": c.get("duration_ms") or 0,
                "input_tokens": c.get("input_tokens") or 0,
                "output_tokens": c.get("output_tokens") or 0,
                "total_tokens": c.get("total_tokens") or 0,
            })

    # Filter by since (string compare on ISO is correct: same format).
    if since:
        items = [it for it in items if (it.get("ts") or "") > since]

    # Sort ascending by ts; stable order within the same ts preserves
    # the natural insertion order (events → stages → llm_calls).
    items.sort(key=lambda it: (it.get("ts") or "", it.get("kind") or ""))

    truncated = len(items) > limit
    if truncated:
        items = items[:limit]

    return {
        "run_id": run_id,
        "items": items,
        "count": len(items),
        "truncated": truncated,
    }


def build_health(run_id: str) -> dict:
    """Build a liveness + progress summary for a single run.

    Returns the run status, the most recent event (``last_event`` with
    age in seconds), the current node (inferred from the most recent
    ``analyst_started`` event), counts of LLM calls + tokens, and a
    boolean ``is_alive`` that flips false if a "running" run has gone
    silent for more than :data:`_RUN_STALE_AFTER_S` seconds.
    """
    rj = storage.read_run(run_id)
    if rj is None:
        return {"run_id": run_id, "found": False}

    events_list = storage.list_run_events(run_id)
    last_event = events_list[-1] if events_list else None
    last_ts_str = (last_event or {}).get("ts") or rj.get("started_at") or ""
    last_ts = _parse_iso_z(last_ts_str) if last_ts_str else None

    # ``now_utc`` is not imported here; use datetime for portability.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    age_s: Optional[float] = None
    if last_ts is not None:
        age_s = (now - last_ts).total_seconds()

    # Current node: the most recent analyst_started node we have NOT
    # seen an analyst_completed for. The runner emits these in matched
    # pairs per node, so a ``analyst_started`` whose matching
    # ``analyst_completed`` is later in the log is in-flight.
    current_node: Optional[str] = None
    in_flight_nodes: list[str] = []
    completed_nodes: list[str] = []
    for ev in events_list:
        et = ev.get("type")
        ed = ev.get("data") or {}
        node = ed.get("node")
        if et == "analyst_started" and node:
            in_flight_nodes.append(node)
        elif et == "analyst_completed" and node:
            completed_nodes.append(node)
    # Anything still in in_flight is the current node (or, if multiple,
    # the most recently entered one).
    pending = [n for n in in_flight_nodes if n not in completed_nodes]
    if pending:
        current_node = pending[-1]

    # LLM call aggregates.
    llm_calls_list = storage.list_run_llm_calls(run_id)
    total_in = sum(c.get("input_tokens") or 0 for c in llm_calls_list)
    total_out = sum(c.get("output_tokens") or 0 for c in llm_calls_list)
    total_all = sum(c.get("total_tokens") or 0 for c in llm_calls_list)

    # Stage summary.
    rd = storage.read_run_dir(run_id)
    completed_stages: list[str] = []
    if rd is not None:
        for sp in sorted((rd / "stages").glob("*.json")):
            d = storage.read_json(sp) or {}
            s = d.get("stage") or sp.stem
            if s not in completed_stages:
                completed_stages.append(s)

    status = rj.get("status") or "unknown"
    is_alive = status == "running" and (
        age_s is None or age_s <= _RUN_STALE_AFTER_S
    )
    # Terminal states are also "alive" in the sense of the run being
    # observed; liveness only matters for in-flight runs.
    is_alive = is_alive or status in ("done", "failed", "cancelled", "superseded")

    # Duration so far (or final).
    started_at = _parse_iso_z(rj.get("started_at") or "")
    finished_at = _parse_iso_z(rj.get("finished_at") or "")
    end_ts = finished_at or (now if status == "running" else None)
    duration_s: Optional[float] = None
    if started_at is not None and end_ts is not None:
        duration_s = round((end_ts - started_at).total_seconds(), 2)

    return {
        "run_id": run_id,
        "found": True,
        "ticker": rj.get("ticker"),
        "status": status,
        "started_at": rj.get("started_at"),
        "finished_at": rj.get("finished_at"),
        "duration_s": duration_s,
        "is_alive": is_alive,
        "is_stale": (status == "running" and age_s is not None
                     and age_s > _RUN_STALE_AFTER_S),
        "current_node": current_node,
        "last_event": {
            "id": (last_event or {}).get("id"),
            "type": (last_event or {}).get("type"),
            "ts": last_ts_str or None,
            "age_s": age_s,
        },
        "event_count": len(events_list),
        "stages_completed": completed_stages,
        "llm_call_count": len(llm_calls_list),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_all,
        "decision_action": rj.get("decision_action"),
        "decision_target": rj.get("decision_target"),
    }


def _parse_iso_z(s: str):
    """Parse an ISO-8601 string with optional ``Z`` suffix into a datetime."""
    if not s:
        return None
    try:
        # Python 3.11+: ``datetime.fromisoformat`` accepts ``Z``.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
