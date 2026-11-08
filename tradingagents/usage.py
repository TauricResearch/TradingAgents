"""Local LLM metering. Never stores prompts, responses, credentials or exception text."""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


def usage_path():
    from tradingagents.default_config import DEFAULT_CONFIG
    return Path(DEFAULT_CONFIG["usage_db_path"])


class UsageStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else usage_path()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            db.executescript("""
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, run_id TEXT, ticker TEXT, analysis_date TEXT,
                    source TEXT, provider TEXT, model TEXT, agent TEXT,
                    started_at REAL, duration REAL, status TEXT,
                    tokens_in INTEGER, tokens_out INTEGER, cached_tokens INTEGER,
                    input_rate REAL, output_rate REAL, cache_rate REAL, cost_usd REAL
                );
                CREATE INDEX IF NOT EXISTS calls_started ON calls(started_at);
                CREATE TABLE IF NOT EXISTS prices (
                    provider TEXT, model TEXT, input_rate REAL NOT NULL,
                    output_rate REAL NOT NULL, cache_rate REAL, updated_at REAL,
                    PRIMARY KEY(provider, model)
                );
            """)
            yield db

    def set_price(self, provider, model, input_rate, output_rate, cache_rate=None):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?)",
                       (provider, model, input_rate, output_rate, cache_rate, time.time()))

    def prices(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM prices ORDER BY provider, model")]

    def start(self, call):
        with self.connect() as db:
            price = db.execute("SELECT * FROM prices WHERE provider=? AND model=?",
                               (call["provider"], call["model"])).fetchone()
            values = {**call, "input_rate": price["input_rate"] if price else None,
                      "output_rate": price["output_rate"] if price else None,
                      "cache_rate": price["cache_rate"] if price else None}
            keys = list(values)
            db.execute(f"INSERT OR IGNORE INTO calls ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                       [values[key] for key in keys])

    def finish(self, call_id, duration, status, usage):
        with self.connect() as db:
            row = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if not row or row["status"] != "started":
                return
            tin = usage.get("input_tokens") if usage else None
            tout = usage.get("output_tokens") if usage else None
            cached = (usage.get("input_token_details") or {}).get("cache_read", 0) if usage else None
            cost = None
            if (tin is not None and tout is not None and row["input_rate"] is not None
                    and (not cached or row["cache_rate"] is not None)
                    and not (usage.get("input_token_details") or {}).get("cache_creation")):
                cost = ((tin - min(cached or 0, tin)) * row["input_rate"]
                        + tout * row["output_rate"]
                        + min(cached or 0, tin) * (row["cache_rate"] or 0)) / 1_000_000
            db.execute("""UPDATE calls SET duration=?, status=?, tokens_in=?, tokens_out=?,
                       cached_tokens=?, cost_usd=? WHERE id=?""",
                       (duration, status, tin, tout, cached, cost, call_id))

    def report(self, start=None, end=None, ticker=None, model=None, run_id=None):
        clauses, args = [], []
        for column, value, operator in (("started_at", start, ">="), ("started_at", end, "<"),
                ("ticker", ticker, "="), ("model", model, "="), ("run_id", run_id, "=")):
            if value is not None:
                clauses.append(f"{column} {operator} ?")
                args.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM calls" + where + " ORDER BY started_at DESC", args)]
        def totals(items):
            return {"calls": len(items), "failed": sum(r["status"] == "failed" for r in items),
                    "unfinished": sum(r["status"] == "started" for r in items),
                    "tokens_in": sum(r["tokens_in"] or 0 for r in items),
                    "tokens_out": sum(r["tokens_out"] or 0 for r in items),
                    "cached_tokens": sum(r["cached_tokens"] or 0 for r in items),
                    "unknown_usage": sum(r["tokens_in"] is None for r in items),
                    "unpriced": sum(r["cost_usd"] is None for r in items),
                    "cost_usd": sum(r["cost_usd"] or 0 for r in items),
                    "duration": sum(r["duration"] or 0 for r in items)}
        groups = {}
        for row in rows:
            key = (row["provider"], row["model"])
            groups.setdefault(key, []).append(row)
        return {"totals": totals(rows), "models": [
            {"provider": key[0], "model": key[1], **totals(items)} for key, items in groups.items()],
            "calls": rows}


class UsageCallback(BaseCallbackHandler):
    """One callback per tier; shared context is set before each analysis.

    SDK retries hidden inside a single model invocation cannot be counted separately.
    Start records survive an abrupt process exit as unfinished calls.
    """
    def __init__(self, context, provider, model, store=None):
        self.context, self.provider, self.model = context, provider, model
        self.store = store or UsageStore()

    def _safe(self, operation, *args):
        try:
            operation(*args)
        except Exception:
            logger.warning("LLM usage could not be recorded", exc_info=False)

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        self._start(run_id, metadata)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs):
        self._start(run_id, metadata)

    def _start(self, run_id, metadata):
        self._safe(self.store.start, {
            "id": str(run_id), "run_id": self.context.get("run_id", "background"),
            "ticker": self.context.get("ticker", ""), "analysis_date": self.context.get("analysis_date", ""),
            "source": self.context.get("source", "python"), "provider": self.provider,
            "model": self.model, "agent": (metadata or {}).get("usage_agent") or (metadata or {}).get("langgraph_node", "background"),
            "started_at": time.time(), "status": "started",
        })

    def _finish(self, run_id, status, usage):
        def finish():
            with self.store.connect() as db:
                row = db.execute("SELECT started_at FROM calls WHERE id=?", (str(run_id),)).fetchone()
            if row:
                self.store.finish(str(run_id), max(0, time.time() - row["started_at"]), status, usage)
        self._safe(finish)

    def on_llm_end(self, response, *, run_id, **kwargs):
        usage = None
        try:
            message = response.generations[0][0].message
            usage = message.usage_metadata
            if not usage:
                raw = message.response_metadata.get("token_usage") or message.response_metadata.get("usage")
                if raw and "prompt_tokens" in raw and "completion_tokens" in raw:
                    usage = {"input_tokens": raw["prompt_tokens"], "output_tokens": raw["completion_tokens"],
                             "input_token_details": {"cache_read": (raw.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}}
        except (AttributeError, IndexError, TypeError):
            pass
        self._finish(run_id, "completed", usage)

    def on_llm_error(self, error, *, run_id, response=None, **kwargs):
        self._finish(run_id, "failed", None)


def new_context(config):
    return {"source": config.get("usage_source", "python"),
            "run_id": config.get("usage_run_id") or uuid.uuid4().hex}
