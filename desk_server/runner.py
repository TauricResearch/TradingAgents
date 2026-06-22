"""Per-run execution: drive the engine on a worker thread and push events onto
the asyncio loop for the SSE endpoint to drain.

``graph.stream_run`` is synchronous and blocking, so it runs in the loop's
executor; every event is handed back to the loop with ``call_soon_threadsafe``
so all mutation of the run's buffer happens on the loop thread (no locks needed).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
import traceback
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from desk_adapter.diff import SnapshotDiffer
from desk_adapter.env import build_engine_config
from desk_server.events import build_event


class RunCancelled(Exception):
    """Raised (via a callback) to interrupt the engine promptly on cancel."""


class CancelCallbackHandler(BaseCallbackHandler):
    """Raises ``RunCancelled`` at the next LLM / tool / chain boundary once the
    run is cancelled, so a Stop interrupts within one call instead of waiting for
    the whole in-flight node (which can be minutes of LLM + tool calls) to finish.

    ``raise_error`` makes LangChain propagate the exception instead of swallowing
    it, which aborts the graph; the call already in flight finishes, but no new
    LLM/tool call starts.
    """

    raise_error = True

    def __init__(self, handle: RunHandle) -> None:
        super().__init__()
        self._handle = handle

    def _check(self) -> None:
        if self._handle.cancelled:
            raise RunCancelled

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self._check()

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self._check()

    def on_tool_start(self, *args: Any, **kwargs: Any) -> None:
        self._check()

    def on_chain_start(self, *args: Any, **kwargs: Any) -> None:
        self._check()


class RunHandle:
    """Buffers a run's events and signals the SSE generator when new ones land."""

    def __init__(self, run_id: str, loop: asyncio.AbstractEventLoop):
        self.run_id = run_id
        self.loop = loop
        self.events: list[dict] = []
        self.seq = 0
        self.done = False
        self.cancelled = False
        self.status = "warming"
        self.updated = asyncio.Event()

    # -- loop-thread only --
    def _append(self, event_type: str, fields: dict[str, Any]) -> None:
        self.seq += 1
        self.events.append(build_event(self.run_id, self.seq, event_type, fields))
        if event_type in ("started", "done", "error", "cancelled"):
            self.status = event_type
        self.updated.set()

    def _finish(self) -> None:
        self.done = True
        self.updated.set()

    # -- worker-thread safe --
    def emit(self, event_type: str, **fields: Any) -> None:
        self.loop.call_soon_threadsafe(self._append, event_type, fields)

    def emit_event(self, event: dict) -> None:
        fields = {k: v for k, v in event.items() if k != "type"}
        self.emit(event["type"], **fields)

    def finish(self) -> None:
        self.loop.call_soon_threadsafe(self._finish)


def run_blocking(handle: RunHandle, run_config: dict) -> None:
    """Executed in a worker thread. Streams the engine and emits events."""
    saved_env: dict[str, str | None] = {}
    try:
        from cli.stats_handler import StatsCallbackHandler
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # Inject the provider/data keys the app supplied (from Keychain) into the
        # process env so the engine's clients (which read os.getenv) pick them up.
        # Loopback-only; never written to disk. The prior values are restored in
        # ``finally`` so a run's keys never leak into a later /test or a run that
        # omits them. (Runs are serialized on a single-worker executor — see
        # desk_server/app.py — so two runs never race on os.environ.)
        for env_name, value in (run_config.get("keys") or {}).items():
            if value:
                saved_env[env_name] = os.environ.get(env_name)
                os.environ[env_name] = value

        analysts = run_config.get("analysts") or ["market", "social", "news", "fundamentals"]
        cfg = build_engine_config(run_config)
        differ = SnapshotDiffer(analysts)
        stats = StatsCallbackHandler()
        cancel_cb = CancelCallbackHandler(handle)

        handle.emit("warming", phase="graph_build")
        graph = TradingAgentsGraph(
            selected_analysts=analysts, debug=False, config=cfg, callbacks=[stats, cancel_cb]
        )

        ticker = run_config["ticker"]
        trade_date = run_config["trade_date"]
        asset_type = run_config.get("asset_type", "stock")
        handle.emit(
            "started",
            ticker=ticker,
            asset_type=asset_type,
            trade_date=str(trade_date),
            analysts=analysts,
            profile_name=run_config.get("profile_name", ""),
            max_debate_rounds=cfg.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=cfg.get("max_risk_discuss_rounds", 1),
            benchmark=graph._resolve_benchmark(ticker),
        )

        start = time.time()
        final: dict = {}
        completed = True
        try:
            for snapshot in graph.stream_run(ticker, trade_date, asset_type=asset_type):
                if handle.cancelled:  # belt-and-braces; the callback usually fires first
                    completed = False
                    break
                final = snapshot
                for event in differ.process(snapshot):
                    handle.emit_event(event)
                handle.emit("stats", elapsed_s=round(time.time() - start, 2), **stats.get_stats())
        except RunCancelled:
            # The cancel callback aborted an in-flight node mid-stream.
            completed = False

        if completed:
            rating = ""
            with contextlib.suppress(Exception):
                rating = graph.process_signal(final.get("final_trade_decision", ""))
            handle.emit("done", rating=rating, run_dir=cfg.get("results_dir", ""))
        else:
            handle.emit("cancelled", at_node=getattr(differ, "active", None))
    except Exception as exc:  # noqa: BLE001 - surface any engine failure to the client
        traceback.print_exc()
        handle.emit("error", scope="fatal", message=str(exc))
    finally:
        for env_name, prior in saved_env.items():
            if prior is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = prior
        handle.finish()
