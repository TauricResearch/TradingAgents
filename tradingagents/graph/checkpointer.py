"""LangGraph checkpoint support for resumable analysis runs.

Per-ticker SQLite databases so concurrent tickers don't contend.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Mapping

from langchain_core.load.serializable import Serializable
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    get_checkpoint_metadata,
    get_serializable_checkpoint_metadata,
)
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.runnables import RunnableConfig

from tradingagents.dataflows.utils import safe_ticker_component

log = logging.getLogger(__name__)


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """Return the SQLite checkpoint DB path for a ticker."""
    # Reject ticker values that would escape the checkpoints directory.
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(ticker: str, date: str) -> str:
    """Deterministic thread ID for a ticker+date pair."""
    return hashlib.sha256(f"{ticker.upper()}:{date}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSON-safe metadata handling
# ---------------------------------------------------------------------------
#
# ``langgraph_checkpoint_sqlite 3.1.0`` (bundled with ``langgraph 0.4.8``)
# builds checkpoint metadata by calling ``get_checkpoint_metadata`` then
# ``json.dumps(...)``. ``get_checkpoint_metadata`` keeps the per-tick
# ``writes`` key, and ``writes[node_name]`` for an agent node is a dict
# like ``{"messages": [AIMessage(...)]}`` — which ``json.dumps`` cannot
# serialise. The result is the user-reported:
#
#     TypeError: Object of type AIMessage is not JSON serializable
#
# The same package ships a sibling helper, ``get_serializable_checkpoint_metadata``,
# that pops ``writes`` from the result. We use that in :class:`_JsonSafeSqliteSaver`
# so the checkpoint row can be written. We then add a *defensive* fallback
# that stringifies any remaining non-serialisable values, so an unanticipated
# non-JSON-safe value added to the metadata by a future langgraph release
# degrades gracefully (logged + stored as a string) instead of aborting the
# whole run.
#
# If/when the upstream bug is fixed (the ``put`` body should call
# ``get_serializable_checkpoint_metadata`` itself), this subclass becomes a
# no-op shim and can be deleted — the regression test in
# ``tests/test_checkpoint_aimessage.py`` will tell us.

_NON_SERIALIZABLE = (BaseMessage, Serializable)


def _stringify_unsupported(obj: Any) -> Any:
    """Recursively replace non-JSON-serialisable values with their string repr.

    Used only as a last-resort fallback when ``get_serializable_checkpoint_metadata``
    is not enough (e.g. a custom LangChain object sneaks into ``config.metadata``).
    """
    if isinstance(obj, _NON_SERIALIZABLE):
        return f"<{type(obj).__name__} {getattr(obj, 'content', '')[:200]!r}>"
    if isinstance(obj, Mapping):
        return {k: _stringify_unsupported(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_stringify_unsupported(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def _safe_metadata(
    config: RunnableConfig, metadata: CheckpointMetadata
) -> CheckpointMetadata:
    """Return metadata guaranteed to be JSON-serialisable.

    1. Use the langgraph-provided helper that strips the ``writes`` key.
    2. If the result is still not JSON-serialisable, stringify the offender
       and log a warning. This is the belt-and-braces fallback that lets
       the run complete even when an upstream change re-introduces a
       non-serialisable object.
    """
    safe = dict(get_serializable_checkpoint_metadata(config, metadata))
    try:
        json.dumps(safe, ensure_ascii=False)
        return safe
    except (TypeError, ValueError) as exc:
        log.warning(
            "checkpoint metadata contains non-JSON-serialisable values "
            "after stripping writes (%s); falling back to repr()",
            exc,
        )
        return _stringify_unsupported(safe)


class _JsonSafeSqliteSaver(SqliteSaver):
    """``SqliteSaver`` whose ``put`` strips non-JSON-serialisable metadata.

    See module docstring for the upstream bug. The :func:`get_checkpointer`
    context manager returns instances of this class, so every checkpoint
    row written by TradingAgents goes through the safe path — even if a
    test or future caller instantiates a plain ``SqliteSaver`` elsewhere.
    """

    def put(  # type: ignore[override]
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ):
        # ``get_checkpoint_metadata`` here mirrors the upstream call so the
        # row layout matches what a future langgraph fix would produce. We
        # then swap in our safe variant for the JSON encode step.
        from langgraph.checkpoint.sqlite import JsonPlusSerializer  # local: avoid cycles

        # The checkpointer's own serializer is used for the *checkpoint* blob;
        # the metadata blob is a plain JSON string built by upstream. We
        # rebuild only the metadata portion to stay binary-compatible.
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        serialized_metadata = json.dumps(
            _safe_metadata(config, metadata), ensure_ascii=False
        ).encode("utf-8", "ignore")
        with self.cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
                "type, checkpoint, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(config["configurable"]["thread_id"]),
                    checkpoint_ns,
                    checkpoint["id"],
                    config["configurable"].get("checkpoint_id"),
                    type_,
                    serialized_checkpoint,
                    serialized_metadata,
                ),
            )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str) -> Generator[SqliteSaver, None, None]:
    """Context manager yielding a JSON-safe SqliteSaver backed by a per-ticker DB."""
    db = _db_path(data_dir, ticker)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = _JsonSafeSqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def has_checkpoint(data_dir: str | Path, ticker: str, date: str) -> bool:
    """Check whether a resumable checkpoint exists for ticker+date."""
    return checkpoint_step(data_dir, ticker, date) is not None


def checkpoint_step(data_dir: str | Path, ticker: str, date: str) -> int | None:
    """Return the step number of the latest checkpoint, or None if none exists."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, date)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = saver.get_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """Remove all checkpoint DBs. Returns number of files deleted."""
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
    return len(dbs)


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str) -> None:
    """Remove checkpoint for a specific ticker+date by deleting the thread's rows."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, date)
    conn = sqlite3.connect(str(db))
    try:
        for table in ("writes", "checkpoints"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
