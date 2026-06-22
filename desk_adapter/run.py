"""The streaming run driver and the resolve-only pass.

Imports ``tradingagents`` (Python >=3.10). Drives the engine's new
``TradingAgentsGraph.stream_run`` generator, diffs each whole-state snapshot
into events via ``desk_adapter.diff``, and emits them as NDJSON.
"""

from __future__ import annotations

import contextlib
import signal
import time
import traceback
from typing import Any

from desk_adapter.diff import SnapshotDiffer
from desk_adapter.env import build_engine_config, load_run_config
from desk_adapter.protocol import Emitter


def _emit_stats(emitter: Emitter, stats_handler: Any, start: float) -> None:
    try:
        stats = stats_handler.get_stats()
    except Exception:
        stats = {}
    emitter.emit(
        "stats",
        llm_calls=stats.get("llm_calls", 0),
        tool_calls=stats.get("tool_calls", 0),
        tokens_in=stats.get("tokens_in", 0),
        tokens_out=stats.get("tokens_out", 0),
        elapsed_s=round(time.time() - start, 2),
    )


def run_command(args: Any, emitter: Emitter) -> int:
    """Execute one analysis run, streaming events. Returns a process exit code."""
    run_config = load_run_config(args.config)
    ticker = run_config["ticker"]
    trade_date = run_config["trade_date"]
    asset_type = run_config.get("asset_type", "stock")
    analysts = run_config.get("analysts") or ["market", "social", "news", "fundamentals"]
    profile_name = run_config.get("profile_name", "")

    # Cancel = SIGTERM -> emit a clean final line then exit. Process-kill is the
    # real cancel; this just gives the app a tidy terminal event when catchable.
    def _on_term(signum, frame):
        emitter.emit("cancelled", at_node=getattr(differ, "active", None))
        raise SystemExit(143)

    differ = SnapshotDiffer(analysts)
    signal.signal(signal.SIGTERM, _on_term)

    emitter.emit("warming", phase="import")
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    cfg = build_engine_config(run_config)
    cfg["max_debate_rounds"] = run_config.get("max_debate_rounds", cfg.get("max_debate_rounds", 1))
    cfg["max_risk_discuss_rounds"] = run_config.get(
        "max_risk_discuss_rounds", cfg.get("max_risk_discuss_rounds", 1)
    )

    emitter.emit("warming", phase="graph_build")
    stats_handler = StatsCallbackHandler()
    graph = TradingAgentsGraph(
        selected_analysts=analysts, debug=False, config=cfg, callbacks=[stats_handler]
    )

    emitter.emit(
        "started",
        ticker=ticker,
        asset_type=asset_type,
        trade_date=str(trade_date),
        analysts=analysts,
        profile_name=profile_name,
        max_debate_rounds=cfg["max_debate_rounds"],
        max_risk_discuss_rounds=cfg["max_risk_discuss_rounds"],
        benchmark=graph._resolve_benchmark(ticker),
    )

    start = time.time()
    final_state: dict = {}
    try:
        for snapshot in graph.stream_run(ticker, trade_date, asset_type=asset_type):
            final_state = snapshot
            for event in differ.process(snapshot):
                emitter.emit_event(event)
            _emit_stats(emitter, stats_handler, start)
    except SystemExit:
        return 143
    except Exception as exc:  # noqa: BLE001 - surface any engine failure to the UI
        traceback.print_exc()  # -> stderr (fd 1 is reserved for the protocol)
        emitter.emit("error", scope="fatal", message=str(exc))
        return 1

    rating = ""
    with contextlib.suppress(Exception):
        rating = graph.process_signal(final_state.get("final_trade_decision", ""))
    _emit_stats(emitter, stats_handler, start)
    emitter.emit("done", rating=rating, run_dir=cfg.get("results_dir", ""))
    return 0


def resolve_command(args: Any, emitter: Emitter) -> int:
    """Realize pending outcomes (realized return + alpha + reflection) without a
    full paid re-analysis, via the engine's public resolve methods."""
    run_config = load_run_config(args.config) if args.config else {}
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    cfg = build_engine_config(run_config) if run_config else None
    graph = TradingAgentsGraph(config=cfg) if cfg else TradingAgentsGraph()
    try:
        if args.ticker and not args.all:
            graph.resolve_pending_entries(args.ticker)
            resolved = [args.ticker]
        else:
            resolved = graph.resolve_all_pending()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        emitter.emit("error", scope="fatal", message=str(exc))
        return 1
    emitter.emit("resolved", tickers=resolved)
    return 0
