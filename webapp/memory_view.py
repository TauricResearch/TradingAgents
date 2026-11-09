"""The decision log for the web console: read it, and settle what is due.

The memory log is the record every run reads back: each decision as made, and,
once its holding window has traded, its realized and alpha return with the
model's reflection on the outcome. The page shows it as a table; "Settle now"
runs the same settlement pass a run performs at its start, so decisions whose
window has since traded get their outcome and reflection without waiting for
the next analysis.
"""

from __future__ import annotations

import threading
import time

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.factory import create_tier_client
from tradingagents.memory import TradingMemoryLog
from tradingagents.memory.reflection import Reflector
from tradingagents.memory.settlement import settle_all_pending

# One settlement pass at a time, like the log's own lock asks: reflections call
# the model, and two passes would pay for the same reflection twice.
_SETTLE_LOCK = threading.Lock()


def _log() -> TradingMemoryLog:
    """The live log, at the path the configuration names."""
    return TradingMemoryLog({"memory_log_path": DEFAULT_CONFIG["memory_log_path"]})


def log_path() -> str:
    """Where the live log lives, for the page to show."""
    return str(DEFAULT_CONFIG["memory_log_path"])


def list_entries() -> dict:
    """Every entry in the live log, newest decision first."""
    entries = _log().load_entries()
    entries.sort(key=lambda e: (e["date"], e["ticker"]), reverse=True)
    return {
        "path": log_path(),
        "entries": [
            {
                "date": e["date"],
                "ticker": e["ticker"],
                "rating": e["rating"],
                "pending": e["pending"],
                "raw": e["raw"],
                "alpha": e["alpha"],
                "holding": e["holding"],
                "resolved": e["resolved"],
                "decision": e["decision"],
                "reflection": e["reflection"],
            }
            for e in entries
        ],
    }


def settle(wait: bool = True) -> dict:
    """Settle every ticker's pending decisions whose holding window has traded.

    This is the pass ``TradingAgentsGraph.settle_all_pending`` runs: prices are
    fetched, the outcome written, and the model asked for a reflection. It can
    take a while and calls the provider, so it runs off the request thread and
    the page polls the job like a run.
    """
    with _SETTLE_LOCK:
        if _settle_job["status"] == "running":
            return {"status": "already-running"}
        _settle_job.update(status="running", started_at=time.time(), settled=[], failed=[], error=None)
    try:
        config = DEFAULT_CONFIG
        client = create_tier_client(config, "quick")
        reflector = Reflector(client.get_llm())
        result = settle_all_pending(_log(), reflector, config)
    except Exception as exc:
        _settle_job.update(status="failed", error=f"{type(exc).__name__}: {exc}", finished_at=time.time())
    else:
        _settle_job.update(
            status="completed",
            settled=[{"ticker": t, "date": d} for t, d in result.settled],
            failed=[{"ticker": t, "reason": r} for t, r in result.failed],
            finished_at=time.time(),
        )
    return {"status": _settle_job["status"]}


_settle_job: dict = {"status": "idle", "started_at": None, "finished_at": None,
                     "settled": [], "failed": [], "error": None}


def settle_status() -> dict:
    """The settlement job's state, for the page to poll."""
    return dict(_settle_job)
