"""The real run engine: drives a TradingAgentsGraph analysis asynchronously.

Faithfully re-implements ``TradingAgentsGraph.propagate()``'s scaffolding for
the async web path:

- sync phases (`_resolve_pending_entries`, instrument resolution, post-run
  logging/memory/signal) run via the loop's executor, never on the event loop;
- the graph streams with ``stream_mode=["updates", "custom"]`` (overriding
  ``get_graph_args``'s hardcoded ``"values"``);
- checkpoint-enabled runs compile with ``AsyncSqliteSaver`` (the sync saver
  hard-raises under the async Pregel loop);
- post-phases include ``store_decision`` and ``clear_checkpoint`` — without
  them the deferred-reflection memory loop silently breaks;
- report sections are written to disk incrementally, so partial reports
  survive a cancelled/failed run, plus a ``run.json`` manifest.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import time
from functools import partial
from pathlib import Path
from typing import Any

# Module-attribute access (not a from-import of the dict): tests reload
# tradingagents.default_config to re-evaluate env overrides, and a direct
# binding would keep pointing at the pre-reload dict.
from tradingagents import default_config
from tradingagents.web.checkpointer import (
    clear_checkpoint,
    open_async_checkpointer,
    thread_id,
)
from tradingagents.web.history import write_manifest
from tradingagents.web.projection import RunProjector

logger = logging.getLogger(__name__)

STREAM_MODES = ["updates", "custom"]

# Per-LLM-call SDK timeout for web runs (generous: deep-think calls can run
# for minutes). Overridable via the llm_timeout config key.
WEB_LLM_TIMEOUT_SECONDS = 600.0


def build_run_config(params: dict[str, Any]) -> dict[str, Any]:
    """Assemble the run config from form selections, honoring env precedence.

    Mirrors ``cli.main._build_run_config``: an explicit ``TRADINGAGENTS_*``
    env override wins over the form's research-depth presets (#977).
    """
    from cli.utils import resolve_backend_url

    config = default_config.DEFAULT_CONFIG.copy()
    depth = int(params.get("research_depth") or 1)
    if not os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        config["max_debate_rounds"] = depth
    if not os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS"):
        config["max_risk_discuss_rounds"] = depth

    provider = str(params["provider"]).lower()
    config["llm_provider"] = provider
    config["quick_think_llm"] = params["quick_think_llm"]
    config["deep_think_llm"] = params["deep_think_llm"]
    config["backend_url"] = resolve_backend_url(
        provider,
        menu_url=params.get("backend_url") or None,
        env_url=default_config.DEFAULT_CONFIG.get("backend_url"),
    )
    # Only overwrite the thinking/effort knobs when the form actually sent a
    # value — TRADINGAGENTS_* env vars keep supplying base defaults otherwise.
    for knob in ("google_thinking_level", "openai_reasoning_effort", "anthropic_effort"):
        if params.get(knob) is not None:
            config[knob] = params[knob]
    if params.get("output_language"):
        config["output_language"] = params["output_language"]
    if params.get("checkpoint_enabled") is not None:
        config["checkpoint_enabled"] = bool(params["checkpoint_enabled"])
    # Explicit LLM SDK timeout so a hung provider call cannot block server
    # exit on the atexit thread join (cancelled runs drain in a detached
    # executor thread that only finishes when the SDK call returns).
    if config.get("llm_timeout") is None:
        config["llm_timeout"] = WEB_LLM_TIMEOUT_SECONDS
    return config


class AnalysisEngine:
    """Injectable engine driving one full analysis run.

    ``graph_factory`` and ``checkpointer_factory`` exist as seams so tests can
    run the whole scaffolding against a fake graph — no LLMs, no network.
    """

    def __init__(self, graph_factory=None, checkpointer_factory=None):
        self._graph_factory = graph_factory
        self._checkpointer_factory = checkpointer_factory or open_async_checkpointer

    def _make_graph(self, selected_analysts, config, callbacks):
        if self._graph_factory is not None:
            return self._graph_factory(
                selected_analysts, config=config, callbacks=callbacks
            )
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        return TradingAgentsGraph(
            selected_analysts, config=config, debug=False, callbacks=callbacks
        )

    async def __call__(self, params: dict[str, Any], emit) -> dict[str, Any]:
        from cli.stats_handler import StatsCallbackHandler

        loop = asyncio.get_running_loop()
        started = time.time()

        ticker = params["ticker"]
        date = params["date"]
        asset_type = params.get("asset_type") or "stock"
        analysts = list(params.get("analysts") or [])
        config = build_run_config(params)

        run_dir = Path(config["results_dir"]) / ticker / date
        reports_dir = run_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "run_id": params.get("run_id"),
            "source": "web",
            "ticker": ticker,
            "date": date,
            "asset_type": asset_type,
            "status": "running",
            "decision": None,
            "provider": config["llm_provider"],
            "deep_think_llm": config["deep_think_llm"],
            "quick_think_llm": config["quick_think_llm"],
            "analysts": analysts,
            "research_depth": params.get("research_depth"),
            "started_at": _dt.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
            "finished_at": None,
            "duration_seconds": None,
            "error": None,
        }
        write_manifest(run_dir, manifest)

        decision: str | None = None
        status = "failed"
        error_summary: str | None = None
        try:
            stats = StatsCallbackHandler()

            def emit_stats() -> None:
                emit("stats", {
                    "elapsed": round(time.time() - started, 1),
                    "llm_calls": stats.llm_calls,
                    "tool_calls": stats.tool_calls,
                })

            # Graph construction touches disk and builds LLM clients: threaded.
            graph = await loop.run_in_executor(
                None, partial(self._make_graph, analysts, config, [stats])
            )

            # Pre-phase: deferred reflection for pending memory-log entries
            # (yfinance + LLM calls — must not block the event loop).
            await loop.run_in_executor(None, graph._resolve_pending_entries, ticker)

            instrument_context = await loop.run_in_executor(
                None, graph.resolve_instrument_context, ticker, asset_type
            )
            init_state = graph.propagator.create_initial_state(
                ticker,
                date,
                asset_type=asset_type,
                past_context=graph.memory_log.get_past_context(ticker),
                instrument_context=instrument_context,
            )
            args = graph.propagator.get_graph_args(callbacks=[stats])
            # The web path projects per-node deltas; propagator hardcodes
            # "values" (full state per step), which is wrong for streaming.
            args["stream_mode"] = list(STREAM_MODES)

            projector = RunProjector(analysts)
            projector.state.update(
                {k: v for k, v in init_state.items() if k != "messages"}
            )

            def handle_events(events: list[tuple[str, dict]]) -> None:
                for event_type, data in events:
                    emit(event_type, data)
                    if event_type == "report_section":
                        section_path = reports_dir / f"{data['section']}.md"
                        try:
                            section_path.write_text(data["markdown"], encoding="utf-8")
                        except OSError:
                            logger.warning("Could not write %s", section_path)

            async def stream() -> None:
                async for item in graph.graph.astream(init_state, **args):
                    if not (isinstance(item, tuple) and len(item) == 2):
                        continue
                    mode, data = item
                    if mode != "updates" or not isinstance(data, dict):
                        continue
                    handle_events(projector.feed(data))
                    emit_stats()

            if config.get("checkpoint_enabled"):
                signature = graph._run_signature(asset_type)
                async with self._checkpointer_factory(
                    config["data_cache_dir"], ticker
                ) as saver:
                    graph.graph = graph.workflow.compile(checkpointer=saver)
                    try:
                        tid = thread_id(ticker, str(date), signature)
                        args.setdefault("config", {}).setdefault(
                            "configurable", {}
                        )["thread_id"] = tid
                        await stream()
                    finally:
                        graph.graph = graph.workflow.compile()
            else:
                await stream()

            handle_events(projector.final_events())
            final_state = projector.merged_state

            # Post-phases, in propagate()'s order: state log -> memory-log
            # decision (deferred reflection source) -> checkpoint clear ->
            # processed signal. All sync, all threaded.
            graph.ticker = ticker
            graph.curr_state = final_state
            await loop.run_in_executor(None, graph._log_state, date, final_state)
            await loop.run_in_executor(None, partial(
                graph.memory_log.store_decision,
                ticker=ticker,
                trade_date=date,
                final_trade_decision=final_state.get("final_trade_decision", ""),
            ))
            if config.get("checkpoint_enabled"):
                await loop.run_in_executor(None, partial(
                    clear_checkpoint,
                    config["data_cache_dir"], ticker, str(date),
                    graph._run_signature(asset_type),
                ))
            decision = await loop.run_in_executor(
                None, graph.process_signal, final_state.get("final_trade_decision", "")
            )
            emit_stats()

            status = "done"
            return {"decision": decision, "ticker": ticker, "date": date}
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            error_summary = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            finished = time.time()
            manifest.update({
                "status": status,
                "decision": decision,
                "finished_at": _dt.datetime.fromtimestamp(finished).isoformat(timespec="seconds"),
                "duration_seconds": round(finished - started, 1),
                "error": error_summary,
            })
            try:
                write_manifest(run_dir, manifest)
            except OSError:
                logger.warning("Could not write run manifest in %s", run_dir)
