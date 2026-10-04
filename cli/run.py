"""One CLI execution path: prompted and headless runs share streams and artifacts."""

from __future__ import annotations

import os
import sys
import time
from contextlib import nullcontext, suppress
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import typer
from rich.console import Console
from rich.live import Live

from cli.display import (
    ANALYST_ORDER,
    AnalystWallTimeTracker,
    classify_message_type,
    console,
    create_layout,
    display_complete_report,
    message_buffer,
    update_analyst_statuses,
    update_display,
    update_research_team_status,
)
from cli.run_output import default_export_directory, persist_run_buffer, run_directory
from cli.selections import get_user_selections
from cli.stats_handler import StatsCallbackHandler
from tradingagents.agents.rating import is_review
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree

# The native dashboard uses a shared buffer. Serialize in-process CLI runs and
# protect rendering against concurrent deque updates. SDK work may use threads;
# the display remains an observer and never starts a second graph execution.
_RUN_LOCK = RLock()


@dataclass
class AnalysisResult:
    final_state: dict
    decision: str
    directory: Path
    report: Path | None = None
    progress: object | None = None


def _run_directory(config: dict, ticker: str, trade_date: str) -> Path:
    """Compatibility entry point for the native ticker/date directory helper."""
    return run_directory(config, ticker, trade_date)


def _announce_checkpoint_state(graph, ticker: str, trade_date: str) -> None:
    if getattr(graph, "_resuming", False):
        message_buffer.add_message("System", f"Resuming the saved run for {ticker} on {trade_date}")
    else:
        message_buffer.add_message("System", f"Starting fresh for {ticker} on {trade_date}")


def _build_run_config(selections: dict, checkpoint: bool | None) -> dict:
    """Interactive selections, with explicit environment/flag precedence."""
    config = DEFAULT_CONFIG.copy()
    for env_var, key in (("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "max_debate_rounds"),
                         ("TRADINGAGENTS_MAX_RISK_ROUNDS", "max_risk_discuss_rounds")):
        if os.environ.get(env_var):
            console.print(
                f"[green]✓ {key} from environment:[/green] {config[key]} "
                f"(set by {env_var}, so the research depth you chose does not apply to it)"
            )
        else:
            config[key] = selections["research_depth"]
    config["quick_think_llm"] = selections["quick_think_llm"]
    config["deep_think_llm"] = selections["deep_think_llm"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    if config["llm_provider"] != str(DEFAULT_CONFIG.get("llm_provider", "")).lower():
        # Match the prompt-free path: custom authentication/routing headers
        # belong to the configured provider and must not follow a menu switch.
        config["llm_headers"] = None
    # A provider without its own reasoning prompt (e.g. Go) must not erase
    # a reasoning option that DEFAULT_CONFIG already read from the environment.
    for key in ("google_thinking_level", "openai_reasoning_effort", "anthropic_effort"):
        if selections.get(key) is not None:
            config[key] = selections[key]
    for key in ("opencode_go_api", "commandcode_api"):
        if selections.get(key) is not None:
            config[key] = selections[key]
    config["output_language"] = selections.get("output_language", "English")
    if checkpoint is not None:
        config["checkpoint_enabled"] = checkpoint
    return config


def _consume_state(chunk: dict, tracker, seen_without_ids: set) -> None:
    """Update the native messages, report panels and incremental section files.

    Called for full `values` snapshots by BOTH CLI entry points. Canonical
    completed sections supersede temporary research/risk debate previews.
    """
    for index, message in enumerate(chunk.get("messages", [])):
        msg_id = getattr(message, "id", None)
        if msg_id is not None:
            if msg_id in message_buffer._processed_message_ids:
                continue
            message_buffer._processed_message_ids.add(msg_id)
        else:
            # LangGraph normally supplies IDs. This fallback avoids re-logging
            # identical snapshots from custom message implementations.
            signature = (index, type(message).__name__, repr(getattr(message, "content", None)),
                         repr(getattr(message, "tool_calls", None)))
            if signature in seen_without_ids:
                continue
            seen_without_ids.add(signature)
        msg_type, content = classify_message_type(message)
        if content and content.strip():
            message_buffer.add_message(msg_type, content)
        for call in getattr(message, "tool_calls", None) or []:
            if isinstance(call, dict):
                message_buffer.add_tool_call(call["name"], call["args"])
            else:
                message_buffer.add_tool_call(call.name, call.args)

    update_analyst_statuses(message_buffer, chunk, wall_time_tracker=tracker)
    debate = chunk.get("investment_debate_state") or {}
    bull, bear, judge = (debate.get(key, "").strip()
                         for key in ("bull_history", "bear_history", "judge_decision"))
    if judge:
        update_research_team_status("completed")
        if message_buffer.agent_status.get("Trader") == "pending":
            message_buffer.update_agent_status("Trader", "in_progress")
    elif bull or bear:
        update_research_team_status("in_progress")
    research = chunk.get("investment_plan") or (
        f"### Research Manager Decision\n{judge}" if judge else
        f"### Bear Researcher Analysis\n{bear}" if bear else
        f"### Bull Researcher Analysis\n{bull}" if bull else None
    )
    if research:
        message_buffer.update_report_section("investment_plan", research)

    if chunk.get("trader_investment_plan"):
        message_buffer.update_report_section("trader_investment_plan", chunk["trader_investment_plan"])
        message_buffer.update_agent_status("Trader", "completed")
        if message_buffer.agent_status.get("Aggressive Analyst") == "pending":
            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

    risk = chunk.get("risk_debate_state") or {}
    preview = None
    for key, agent in (("aggressive_history", "Aggressive Analyst"),
                       ("conservative_history", "Conservative Analyst"),
                       ("neutral_history", "Neutral Analyst")):
        history = risk.get(key, "").strip()
        if history:
            if message_buffer.agent_status.get(agent) != "completed":
                message_buffer.update_agent_status(agent, "in_progress")
            preview = f"### {agent} Analysis\n{history}"
    judge = risk.get("judge_decision", "").strip()
    if judge:
        preview = f"### Portfolio Manager Decision\n{judge}"
        for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"):
            message_buffer.update_agent_status(agent, "completed")
    decision = chunk.get("final_trade_decision") or preview
    if decision:
        message_buffer.update_report_section("final_trade_decision", decision)


def _default_graph_factory(analysts, config, callbacks):
    return TradingAgentsGraph(analysts, config=config, debug=False, callbacks=callbacks)


def _execute_analysis(selections, config, portfolio, mode, graph_factory) -> AnalysisResult:
    selected_set = {getattr(analyst, "value", analyst) for analyst in selections["analysts"]}
    if not selected_set or selected_set.difference(ANALYST_ORDER):
        raise ValueError("Select at least one known analyst")
    selected = [key for key in ANALYST_ORDER if key in selected_set]
    ticker, trade_date = selections["ticker"], selections["analysis_date"]
    directory = _run_directory(config, ticker, trade_date).resolve()
    if trade_date > get_current_date():
        raise ValueError("analysis date cannot be in the future")
    if mode not in {"live", "plain", "off"}:
        raise ValueError("progress mode must be live, plain or off")

    # Pin stderr before Live installs its proxies, preserving --json stdout.
    output_console = Console(file=sys.stderr)
    if mode == "plain":
        from cli.progress import AnalysisProgress

        stats = AnalysisProgress(ticker, trade_date, selected, console=output_console, plain=True)
    else:
        stats = StatsCallbackHandler()
    plan = build_analyst_execution_plan(selected)
    tracker = AnalystWallTimeTracker(plan)
    start_time = time.time()
    if mode == "plain":
        stats.stage("Preparing analysis")
    lock = RLock()
    with _RUN_LOCK, run_config(config):
        message_buffer.init_for_analysis(selected)
        with persist_run_buffer(message_buffer, directory, lock):
            # Journaling also works with --no-progress and --json, and starts
            # before SDK construction so a setup failure has a run log too.
            message_buffer.add_message("System", f"Selected ticker: {ticker}")
            if selections["asset_type"] != "stock":
                message_buffer.add_message("System", f"Detected asset type: {selections['asset_type']}")
            message_buffer.add_message("System", f"Analysis date: {trade_date}")
            message_buffer.add_message("System", f"Selected analysts: {', '.join(selected)}")
            try:
                graph = graph_factory(selected, config, [stats])
                layout = create_layout() if mode == "live" else None

                def render():
                    with lock:
                        update_display(layout, stats_handler=stats, start_time=start_time)
                        return layout

                live = (Live(console=output_console, get_renderable=render, screen=True,
                             refresh_per_second=4, transient=True)
                        if mode == "live" else nullcontext())
                with live:
                    message_buffer.update_agent_status(plan.specs[0].agent_node, "in_progress")
                    tracker.mark_started(selected[0])
                    try:
                        init_state = graph.create_run_state(ticker, trade_date, selections["asset_type"], portfolio)
                        checkpoint_tid = graph.begin_checkpoint(ticker, trade_date, selections["asset_type"], portfolio)
                        if checkpoint_tid is not None:
                            _announce_checkpoint_state(graph, ticker, trade_date)
                        args = graph.propagator.get_graph_args(callbacks=[stats])
                        # Full state snapshots: retaining just the latest avoids
                        # accumulating every copy of the growing debate history.
                        args["stream_mode"] = "values"
                        if checkpoint_tid is not None:
                            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid
                        final_state = None
                        seen_without_ids = set()
                        for chunk in graph.graph.stream(graph.checkpoint_input(init_state), **args):
                            with lock:
                                _consume_state(chunk, tracker, seen_without_ids)
                            if chunk.get("__interrupt__"):
                                raise RuntimeError("Analysis paused at an interrupt; checkpoint retained")
                            final_state = chunk
                        if final_state is None:
                            raise RuntimeError("Analysis produced no state; checkpoint retained")
                        # One shared completion path: JSON state, memory, checkpoint.
                        graph._log_state(trade_date, final_state)
                        graph.record_decision(ticker, trade_date, final_state)
                        graph.clear_checkpoint_on_success(ticker, trade_date, selections["asset_type"], portfolio)
                    finally:
                        graph.end_checkpoint()
                    with lock:
                        for agent in message_buffer.agent_status:
                            message_buffer.update_agent_status(agent, "completed")
                        for section in message_buffer.report_sections:
                            if final_state.get(section):
                                message_buffer.update_report_section(section, final_state[section])
                        message_buffer.add_message("System", f"Completed analysis for {trade_date}")
                        message_buffer.add_message("System", tracker.format_summary())
                decision = graph.process_signal(final_state.get("final_trade_decision", ""))
                return AnalysisResult(final_state, decision, directory,
                                      progress=stats if mode == "plain" else None)
            except BaseException as exc:
                # Preserve partial reports; log the failure type, not potentially
                # credential-bearing provider exception text. CLI reports it.
                phase = "Interrupted" if isinstance(exc, KeyboardInterrupt) else "Failed"
                with suppress(OSError):
                    message_buffer.add_message("System", f"{phase} ({type(exc).__name__}); partial reports retained")
                if mode == "plain":
                    stats.fail(exc)
                raise


def run_analysis(checkpoint: bool | None = None, portfolio=None, *, selections=None,
                 config=None, interactive=True, output_dir: Path | None = None,
                 progress_mode: str | None = None, show_report=False,
                 save_report=True, clear_checkpoints=False,
                 graph_factory=None) -> AnalysisResult:
    """Use the same native CLI workflow, optionally with pre-resolved inputs.

    Headless callers supply both selections and config. Only input collection
    and post-run questions differ: headless exports automatically, optionally
    prints the complete report, and never reads/persists interactive preferences.
    """
    if selections is None:
        if not interactive:
            raise ValueError("Headless analysis requires resolved selections")
        selections = get_user_selections()
    if config is None:
        config = _build_run_config(selections, checkpoint)
    mode = progress_mode if progress_mode is not None else ("live" if interactive else "off")
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints

        count = clear_all_checkpoints(config["data_cache_dir"])
        typer.echo(f"Cleared {count} checkpoint(s).", err=True)
    result = _execute_analysis(selections, config, portfolio, mode, graph_factory or _default_graph_factory)

    save = save_report
    export_path = Path(output_dir).expanduser() if output_dir is not None else default_export_directory(config, selections["ticker"])
    if interactive:
        console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
        if is_review(result.decision):
            console.print("[yellow]No rating could be read. Review the saved decision text rather than treating it as a position.[/yellow]")
        save = typer.prompt("Save report?", default="Y").strip().upper() in ("Y", "YES", "")
        if save:
            export_path = Path(typer.prompt("Save path (press Enter for default)", default=str(export_path)).strip()).expanduser()
    if save:
        if result.progress is not None:
            result.progress.stage("Saving reports")
        try:
            result.report = write_report_tree(result.final_state, selections["ticker"], export_path).resolve()
        except Exception as exc:
            if result.progress is not None:
                result.progress.fail(exc)
            if not interactive:
                raise  # Headless callers must not emit success after a save failure.
            console.print(f"[red]Error saving report: {exc}[/red]")
        else:
            if result.progress is not None:
                result.progress.complete()
            if interactive:
                console.print(f"\n[green]✓ Report saved to:[/green] {result.report.parent}")
                console.print(f"  [dim]Complete report:[/dim] {result.report.name}")
    if not save and result.progress is not None:
        result.progress.stage("Completed; incremental reports saved")
    if interactive:
        show_report = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper() in ("Y", "YES", "")
    if show_report:
        display_complete_report(result.final_state)
    return result
