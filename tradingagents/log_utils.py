"""Shared logging module for analysis pipeline.

This module provides a thread-safe logging system that can broadcast
logs to SSE subscribers. Both the server and agent files import from here,
avoiding circular import issues.
"""
import threading
import time
from collections import deque
from datetime import datetime

# Thread-safe log buffer for SSE streaming
analysis_logs = deque(maxlen=1000)
log_lock = threading.Lock()
log_subscribers = []  # List of subscriber queues


def add_log(log_type: str, source: str, message: str):
    """Add a log entry to the buffer and notify SSE subscribers.

    Args:
        log_type: One of 'info', 'success', 'error', 'warning', 'llm', 'agent', 'data'
        source: The source component (e.g. 'system', 'bull_researcher', 'trader')
        message: The log message
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": log_type,
        "source": source,
        "message": message
    }
    with log_lock:
        analysis_logs.append(log_entry)
        # Notify all subscribers
        for queue in log_subscribers:
            try:
                queue.put_nowait(log_entry)
            except Exception:
                pass  # Queue full, skip


class StepTimer:
    """Tracks start/end times for individual pipeline steps.

    Thread-safe timing tracker. Each agent calls start_step() / end_step()
    and _save_to_frontend_db reads the results.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._steps = {}  # step_id -> {started_at, completed_at, duration_ms, status, output_summary}

    def start_step(self, step_id: str):
        """Record the start of a pipeline step. Only sets start time on first call."""
        with self._lock:
            if step_id in self._steps and self._steps[step_id].get("_start_time"):
                # Already started, don't overwrite (multi-turn agents)
                return
            self._steps[step_id] = {
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "duration_ms": None,
                "status": "running",
                "output_summary": None,
                "_start_time": time.time(),
            }

    def end_step(self, step_id: str, status: str = "completed", output_summary: str = None):
        """Record the completion of a pipeline step."""
        with self._lock:
            if step_id not in self._steps:
                # Step wasn't started, create entry anyway
                self._steps[step_id] = {
                    "started_at": datetime.now().isoformat(),
                    "completed_at": datetime.now().isoformat(),
                    "duration_ms": 0,
                    "status": status,
                    "output_summary": output_summary,
                }
                return

            entry = self._steps[step_id]
            entry["completed_at"] = datetime.now().isoformat()
            entry["status"] = status
            if output_summary:
                entry["output_summary"] = output_summary
            start_time = entry.pop("_start_time", None)
            if start_time:
                entry["duration_ms"] = int((time.time() - start_time) * 1000)

    def set_details(self, step_id: str, details: dict):
        """Store structured details for a step (prompt, response, tool_calls).

        Args:
            step_id: The step identifier
            details: Dict with keys like system_prompt, user_prompt, response, tool_calls
        """
        with self._lock:
            if step_id not in self._steps:
                self._steps[step_id] = {}
            self._steps[step_id]["details"] = details

    def update_details(self, step_id: str, updates: dict):
        """Merge updates into existing step details (preserves unmodified fields).

        Use this instead of set_details() when you want to update specific fields
        (e.g., set response) without losing previously-stored fields (e.g., tool_calls).
        """
        with self._lock:
            if step_id not in self._steps:
                self._steps[step_id] = {}
            existing = self._steps[step_id].get("details", {})
            existing.update(updates)
            self._steps[step_id]["details"] = existing

    def get_steps(self) -> dict:
        """Get all recorded step timings."""
        with self._lock:
            # Return copies without internal _start_time field
            result = {}
            for step_id, entry in self._steps.items():
                clean = {k: v for k, v in entry.items() if not k.startswith("_")}
                result[step_id] = clean
            return result

    def clear(self):
        """Reset all step timings."""
        with self._lock:
            self._steps.clear()


# Global step timer instance, shared across all agents in one analysis run
step_timer = StepTimer()


class SymbolProgress:
    """Thread-safe per-symbol step progress tracker for parallel analysis.

    Unlike StepTimer (global, gets cleared per-stock), this tracks progress
    per symbol so the frontend can show "N/12 steps" on each analyzing card.
    """

    TOTAL_STEPS = 12

    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}  # {symbol: {"done": N, "current": "step_name"}}

    def step_done(self, symbol: str, step_id: str):
        """Record that a step completed for a symbol."""
        with self._lock:
            if symbol not in self._data:
                self._data[symbol] = {"done": 0, "current": step_id}
            self._data[symbol]["done"] += 1
            self._data[symbol]["current"] = step_id

    def get(self, symbol: str) -> dict:
        """Get progress for a symbol: {done, total, current}."""
        with self._lock:
            entry = self._data.get(symbol, {"done": 0, "current": None})
            return {"done": entry["done"], "total": self.TOTAL_STEPS, "current": entry["current"]}

    def get_all(self) -> dict:
        """Get progress for all symbols."""
        with self._lock:
            return {
                sym: {"done": e["done"], "total": self.TOTAL_STEPS, "current": e["current"]}
                for sym, e in self._data.items()
            }

    def clear(self, symbol: str):
        """Clear progress for a symbol."""
        with self._lock:
            self._data.pop(symbol, None)


symbol_progress = SymbolProgress()


class RawDataStore:
    """Thread-safe store for raw data fetched during analysis pipeline.

    Captures the actual data returned by vendor APIs (OHLCV, news, fundamentals)
    so it can be saved to the frontend database for debugging/inspection.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = []  # list of {method, symbol, vendor, data, timestamp, ...}

    def log_fetch(self, method: str, symbol: str, vendor: str, raw_data: str,
                  args_str: str = "", duration_s: float = 0):
        """Log a raw data fetch result."""
        with self._lock:
            self._entries.append({
                "method": method,
                "symbol": symbol,
                "vendor": vendor,
                "raw_data": raw_data,
                "args": args_str,
                "duration_s": round(duration_s, 2),
                "timestamp": datetime.now().isoformat(),
                "data_size": len(raw_data) if raw_data else 0,
            })

    def get_entries(self) -> list:
        """Get all captured raw data entries."""
        with self._lock:
            return list(self._entries)

    def clear(self):
        """Reset all captured data."""
        with self._lock:
            self._entries.clear()


# Global raw data store, shared across all data fetches in one analysis run
raw_data_store = RawDataStore()
