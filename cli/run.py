"""Running one analysis from the CLI: build the graph, stream it into the live view, save the report."""

import os
import sys
import time
import webbrowser
from pathlib import Path

import typer
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
from cli.selections import depth_from_env, get_user_selections, unattended_gaps
from cli.stats_handler import StatsCallbackHandler
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    build_analyst_execution_plan,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _run_directory(config: dict, ticker: str, trade_date: str) -> Path:
    """Where this run writes, with the ticker validated as a path component.

    Every other path that interpolates a ticker checks it first; a value of
    ".." here would place the run outside the results directory.
    """
    return Path(config["results_dir"]) / safe_ticker_component(ticker) / trade_date


def _announce_checkpoint_state(graph, ticker: str, trade_date: str) -> None:
    """Say whether this run resumed a saved one, where the user can see it.

    The graph logs this, but nothing in the CLI configures logging and the live
    view owns the screen, so a resume was invisible.
    """
    if getattr(graph, "_resuming", False):
        message_buffer.add_message(
            "System", f"Resuming the saved run for {ticker} on {trade_date}"
        )
    else:
        message_buffer.add_message("System", f"Starting fresh for {ticker} on {trade_date}")


def _build_run_config(selections: dict, checkpoint: bool | None) -> dict:
    """Assemble the run config from interactive selections, honoring env precedence.

    Round counts and checkpoint follow "explicit env/flag wins": an env-applied
    value on DEFAULT_CONFIG is preserved unless the user overrode it on the CLI.
    """
    config = DEFAULT_CONFIG.copy()
    # Research depth sets both round counts, but an explicit env override
    # (TRADINGAGENTS_MAX_DEBATE_ROUNDS / _MAX_RISK_ROUNDS) wins over the
    # interactive selection — leave the env-applied value in place (#977).
    rounds = (("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "max_debate_rounds"),
              ("TRADINGAGENTS_MAX_RISK_ROUNDS", "max_risk_discuss_rounds"))
    depth_was_asked = not depth_from_env()
    for env_var, key in rounds:
        if not os.environ.get(env_var):
            config[key] = selections["research_depth"]
        elif depth_was_asked:
            # The depth question appeared (it is skipped only when both are
            # set), so say which half of the answer the environment overrode.
            console.print(
                f"[green]✓ {key} from environment:[/green] {config[key]} "
                f"(set by {env_var}, so the research depth you chose does not apply to it)"
            )
    config["quick_think_llm"] = selections["quick_think_llm"]
    config["deep_think_llm"] = selections["deep_think_llm"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    # Provider-specific thinking configuration. Only the main provider's is
    # asked; a tier on another provider keeps its configured value (#1440).
    for key in ("google_thinking_level", "openai_reasoning_effort", "anthropic_effort"):
        if selections.get(key) is not None:
            config[key] = selections[key]
    config["output_language"] = selections.get("output_language", "English")
    # --checkpoint/--no-checkpoint overrides only when explicitly given; omitting
    # the flag preserves TRADINGAGENTS_CHECKPOINT_ENABLED / the default (#976).
    if checkpoint is not None:
        config["checkpoint_enabled"] = checkpoint
    return config


def run_analysis(checkpoint: bool | None = None, portfolio=None, flags=None):
    # Direct Python callers that use the historical no-argument API have no
    # holdings to attach, so preserve that call shape as an explicit
    # no-portfolio mode. The CLI always supplies its flag dictionary and still
    # requires an explicit mode for unattended runs.
    legacy_direct_call = flags is None
    flags = {"without_portfolio": True} if legacy_direct_call else flags
    interactive = bool(sys.stdin and sys.stdin.isatty())
    if not interactive:
        gaps = unattended_gaps(flags)
        if gaps:
            console.print("[red]No terminal to answer the setup questions. Set:[/red]")
            for gap in gaps:
                console.print(f"  {gap}")
            raise typer.Exit(code=1)

    selections = get_user_selections(flags)
    config = _build_run_config(selections, checkpoint)
    stats_handler = StatsCallbackHandler()
    selected_set = {getattr(analyst, "value", analyst) for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    config["selected_analysts"] = selected_analyst_keys
    asset_type = getattr(selections["asset_type"], "value", selections["asset_type"])
    config["asset_type"] = asset_type

    from cli.input_ui import RunCancelled, resolve_run_context
    from tradingagents.runapi.execution import run_analysis_api
    from tradingagents.runapi.result import InputError
    try:
        run_context = resolve_run_context(
            selections["ticker"], selections["analysis_date"],
            portfolio_path=flags.get("portfolio_path"),
            without_portfolio=bool(flags.get("without_portfolio")),
            portfolio_as_of=flags.get("portfolio_as_of"),
            loaded_portfolio=flags.get("loaded_portfolio"),
            portfolio=portfolio, interactive=interactive,
        )
    except RunCancelled as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return None
    except InputError as exc:
        console.print(f"[red]{exc.detail}[/red]")
        raise typer.Exit(code=1) from None

    analyst_execution_plan = build_analyst_execution_plan(selected_analyst_keys)
    analyst_wall_time_tracker = AnalystWallTimeTracker(analyst_execution_plan)
    message_buffer.init_for_analysis(selected_analyst_keys)
    start_time = time.time()
    layout = create_layout()
    engine_state = {}

    def graph_factory(selected_analysts, config, callbacks):
        return TradingAgentsGraph(selected_analysts, config=config, debug=False, callbacks=callbacks)

    def engine_runner(graph, context):
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        if asset_type != "stock":
            message_buffer.add_message("System", f"Detected asset type: {asset_type}")
        message_buffer.add_message("System", f"Analysis date: {selections['analysis_date']}")
        message_buffer.add_message(
            "System", f"Selected analysts: {', '.join(getattr(analyst, 'value', analyst) for analyst in selections['analysts'])}"
        )
        for spec in analyst_execution_plan.specs:
            message_buffer.update_agent_status(spec.agent_node, "in_progress")
            analyst_wall_time_tracker.mark_started(spec.key)

        with Live(layout, refresh_per_second=4, screen=True):
            update_display(layout, stats_handler=stats_handler, start_time=start_time)
            update_display(layout, f"Analyzing {selections['ticker']} on {selections['analysis_date']}...",
                           stats_handler=stats_handler, start_time=start_time)
            init_agent_state = graph.create_run_state(
                selections["ticker"], selections["analysis_date"],
                asset_type, context.portfolio_context(),
            )
            args = graph.propagator.get_graph_args(callbacks=[stats_handler])
            checkpoint_tid = graph.begin_checkpoint(
                selections["ticker"], selections["analysis_date"],
                asset_type, context.portfolio_context(),
            )
            if checkpoint_tid is not None:
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid
                _announce_checkpoint_state(graph, selections["ticker"], selections["analysis_date"])
            trace = []
            try:
                for messages, chunk in graph.stream_run(graph.checkpoint_input(init_agent_state), **args):
                    for message in messages:
                        msg_id = getattr(message, "id", None)
                        if msg_id is not None:
                            if msg_id in message_buffer._processed_message_ids:
                                continue
                            message_buffer._processed_message_ids.add(msg_id)
                        msg_type, content = classify_message_type(message)
                        if content and content.strip():
                            message_buffer.add_message(msg_type, content)
                        for tool_call in getattr(message, "tool_calls", []) or []:
                            if isinstance(tool_call, dict):
                                message_buffer.add_tool_call(tool_call.get("name", "tool"), tool_call.get("args", {}))
                            else:
                                message_buffer.add_tool_call(tool_call.name, tool_call.args)
                    if chunk is None:
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                        continue
                    update_analyst_statuses(message_buffer, chunk,
                                            wall_time_tracker=analyst_wall_time_tracker)
                    debate = chunk.get("investment_debate_state")
                    if debate:
                        bull = (debate.get("bull_history") or "").strip()
                        bear = (debate.get("bear_history") or "").strip()
                        manager = (chunk.get("investment_plan") or "").strip()
                        if bull or bear:
                            update_research_team_status("in_progress")
                        if bull:
                            message_buffer.update_report_section("investment_plan", f"### Bull Researcher Analysis\n{bull}")
                        if bear:
                            message_buffer.update_report_section("investment_plan", f"### Bear Researcher Analysis\n{bear}")
                        if manager:
                            message_buffer.update_report_section("investment_plan", f"### Research Manager Recommendation\n{manager}")
                            update_research_team_status("completed")
                            message_buffer.update_agent_status("Trader", "in_progress")
                    trader_plan = chunk.get("trader_investment_plan")
                    if trader_plan:
                        message_buffer.update_report_section("trader_investment_plan", trader_plan)
                        if message_buffer.agent_status.get("Trader") != "completed":
                            message_buffer.update_agent_status("Trader", "completed")
                            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
                    risk = chunk.get("risk_debate_state")
                    if risk:
                        for key, label in (("aggressive_history", "Aggressive Analyst"),
                                           ("conservative_history", "Conservative Analyst"),
                                           ("neutral_history", "Neutral Analyst")):
                            text = (risk.get(key) or "").strip()
                            if text:
                                message_buffer.update_report_section(
                                    "final_trade_decision", f"### {label} Analysis\n{text}"
                                )
                        decision = (chunk.get("final_trade_decision") or "").strip()
                        if decision:
                            message_buffer.update_report_section(
                                "final_trade_decision", f"### Portfolio Manager Final Rating\n{decision}"
                            )
                            for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst",
                                          "Portfolio Manager"):
                                message_buffer.update_agent_status(agent, "completed")
                    trace.append(chunk)
                    update_display(layout, stats_handler=stats_handler, start_time=start_time)
                for chunk in trace:
                    engine_state.update(chunk)
            finally:
                graph.end_checkpoint()
            for agent in message_buffer.agent_status:
                message_buffer.update_agent_status(agent, "completed")
            message_buffer.add_message("System", f"Completed analysis for {selections['analysis_date']}")
            message_buffer.add_message("System", analyst_wall_time_tracker.format_summary())
            for section, value in engine_state.items():
                if section in message_buffer.report_sections:
                    message_buffer.update_report_section(section, value)
            update_display(layout, stats_handler=stats_handler, start_time=start_time)
        return engine_state

    def message_log_text():
        lines = [f"{stamp} [{kind}] {content}" for stamp, kind, content in message_buffer.messages]
        lines.extend(
            f"{stamp} [Tool Call] {name}({args})"
            for stamp, name, args in message_buffer.tool_calls
        )
        return "\n".join(lines) + ("\n" if lines else "")

    result = run_analysis_api(
        run_context, config=config, selected_analysts=selected_analyst_keys,
        graph_factory=graph_factory, engine_runner=engine_runner,
        callbacks=[stats_handler], html=flags.get("html") is not False,
        message_log_provider=message_log_text,
    )
    if result.run_outcome == "COMPLETED":
        console.print("\n[bold cyan]Analysis Complete[/bold cyan]")
    else:
        console.print(f"\n[yellow]Analysis incomplete: {result.stop_reason}[/yellow]")
    if result.report_path:
        console.print(f"[green]Audit report:[/green] {result.report_path}")
    if result.manifest_path:
        console.print(f"[green]Run manifest:[/green] {result.manifest_path}")
    console.print(f"[dim]Output check: {result.output_check}[/dim]")
    if result.findings:
        for finding in result.findings:
            console.print(f"[yellow]{finding.rule}: {finding.detail}[/yellow]")

    show = flags.get("show")
    if show is None:
        show = (typer.confirm("Display the analysis report on screen?", default=True)
                if interactive and not legacy_direct_call else False)
    if show and engine_state:
        display_complete_report(engine_state)
    return result

def _yes(question: str) -> bool:
    return typer.prompt(question, default="Y").strip().upper() in ("Y", "YES", "")


def _graphical_browser():
    """A browser that opens a page in its own window on this machine, or None.

    Over SSH the page sits on the remote machine, and a terminal browser (lynx,
    w3m, elinks) would take over the terminal, so neither is offered.
    """
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return None
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return None
    if type(browser) is webbrowser.GenericBrowser or isinstance(browser, webbrowser.Elinks):
        return None
    return browser


def _open_page(page: Path) -> None:
    """Offer to open the saved page in a browser window, and say where it is if opening fails."""
    browser = _graphical_browser()
    if browser is None or not _yes("Open it in your browser?"):
        return
    try:
        opened = browser.open(page.as_uri())
    except (webbrowser.Error, OSError):
        opened = False
    if not opened:
        console.print(f"  [dim]Could not open a browser; the page is at:[/dim] {page}")


def _offer_reports(final_state, graph, ticker, save=None, show=None, html=None):
    """Save the report tree and show it; ``save``/``show``/``html`` answer the questions when given.

    A saved report includes the HTML page unless ``html`` is False. Someone
    answering the save question at the prompt is also asked about the page and
    offered to open it; a run whose flags answer the save question asks neither.
    """
    asked = save is None
    if asked:
        save = typer.prompt("Save report?", default="Y").strip().upper() in ("Y", "YES", "")
    if save:
        # Under results_dir, not the working directory: in Docker the working
        # directory is inside the container and the report goes with it, while
        # results_dir is the mounted volume the rest of the run already writes to.
        save_path = graph.default_report_path(ticker)
        if asked:   # someone at the prompt may pick another folder
            save_path = Path(typer.prompt(
                "Save path (press Enter for default)", default=str(save_path)
            ).strip())
        if html is None:
            html = _yes("Also save it as an HTML page?") if asked else True
        saved = False
        try:
            report_file = graph.save_reports(final_state, ticker, save_path, html=html)
            saved = True
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")
        if saved and html:
            page = (save_path / "complete_report.html").resolve()
            console.print(f"  [dim]HTML report:[/dim] {page.name}")
            if asked:
                _open_page(page)

    if show is None:
        show = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper() in ("Y", "YES", "")
    if show:
        display_complete_report(final_state)
