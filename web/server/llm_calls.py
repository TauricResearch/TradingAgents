"""File-backed LLM call log. One JSONL line per call, per run."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_llm_call(
    run_id: str,
    *,
    node_name: str,
    ticker: str,
    model: str,
    prompt_text: str,
    response_text: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
    started_at: Optional[str] = None,
) -> None:
    """Append a single LLM call to ``{run_dir}/llm_calls.jsonl``."""
    call = {
        "id": f"{run_id}:{_now_iso()}:{node_name}",
        "run_id": run_id,
        "node_name": node_name,
        "ticker": ticker,
        "model": model,
        "prompt_text": prompt_text,
        "response_text": response_text,
        "tool_calls_json": tool_calls or [],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "started_at": started_at or _now_iso(),
    }
    try:
        storage.append_run_llm_call(run_id, call)
    except KeyError:
        pass


def llm_calls_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Return all LLM calls recorded for a run, in order."""
    return storage.list_run_llm_calls(run_id)


def list_runs_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Return all run.json rows for a ticker, newest first."""
    return storage.list_ticker_runs(ticker)