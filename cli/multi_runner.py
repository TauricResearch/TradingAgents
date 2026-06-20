"""Multi-ticker parallel run orchestration for the CLI.

A single CLI invocation can analyze multiple tickers concurrently. The
pipeline's wall time is dominated by LLM API round-trips rather than local CPU,
so a thread pool keeps total time close to a single run, modulo the provider's
rate limits and the configured worker cap.

Each worker spins its own :class:`TradingAgentsGraph` instance because the
graph carries per-run state on ``self`` (ticker, ``curr_state``,
``log_states_dict``). Each worker also owns its own :class:`MessageBuffer` and
streams chunks through the same ``process_chunk_into_buffer`` helper the
single-ticker rich UI uses — so the per-ticker grid view in this module shows
the same agent statuses, messages, and report content as the single-run path.

Two views are available, chosen by ticker count:

* **Grid view** (``len(entries) <= GRID_MAX``): one rich mini-panel per ticker,
  arranged side-by-side. Shows the per-agent status table, the current report
  snippet, the most recent messages, and per-ticker stats.
* **Status board** (everything larger): a single compact table with one row per
  ticker. Avoids unreadable panels when the watchlist is large.

Persistence is deferred: workers capture ``final_state`` and keep their graph
instance alive on the result record, so the batch-level persist prompt can call
``graph.finalize_run(...)`` per ticker after the user confirms.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from cli.stats_handler import StatsCallbackHandler
from cli.utils import detect_asset_type, filter_analysts_for_asset_type
from cli.viewer import Viewer
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Cutoff between the per-ticker grid and the compact status board. Above this,
# the grid panels become too narrow to read in a normal terminal width.
GRID_MAX = 4

# Coarse pipeline stages used for the status board (and the grid panel
# subtitle). Order matters: the worker inspects the latest streamed chunk and
# picks the latest matching stage.
STAGE_ORDER = [
    ("queued",           "queued"),
    ("analysts",         "analysts"),
    ("research_debate",  "research debate"),
    ("trader",           "trader"),
    ("risk_debate",      "risk debate"),
    ("portfolio",        "portfolio mgr"),
    ("done",             "done"),
    ("failed",           "failed"),
]
STAGE_LABEL = dict(STAGE_ORDER)


def _derive_stage(chunk: dict[str, Any]) -> str:
    """Map a streamed state chunk to a coarse stage key.

    Picked off ``stream_mode="values"`` chunks (full cumulative state), so we
    just look for the latest populated field. Order is intentional: later
    stages override earlier ones when present.
    """
    if chunk.get("final_trade_decision"):
        return "portfolio"
    risk = chunk.get("risk_debate_state") or {}
    if any(risk.get(k) for k in ("aggressive_history", "conservative_history", "neutral_history", "judge_decision")):
        return "risk_debate"
    if chunk.get("trader_investment_plan"):
        return "trader"
    invest = chunk.get("investment_debate_state") or {}
    if any(invest.get(k) for k in ("bull_history", "bear_history", "judge_decision")):
        return "research_debate"
    if any(chunk.get(k) for k in ("market_report", "sentiment_report", "news_report", "fundamentals_report")):
        return "analysts"
    return "queued"


@dataclass
class TickerState:
    """Live, mutable status for one ticker. Read by the renderer.

    ``buffer`` is the per-ticker :class:`MessageBuffer` once the worker has
    initialized it. The grid renderer pulls agent statuses, the current report
    snippet, and recent messages straight from there, so the per-ticker panels
    show the same content the single-run rich UI shows.
    """

    ticker: str
    position_size_gbp: float | None = None
    asset_type: str = "stock"
    stage: str = "queued"
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result_summary: str | None = None
    buffer: Any = None  # cli.main.MessageBuffer; Any to avoid import cycle
    stats_handler: StatsCallbackHandler | None = None
    effective_analysts: list[str] = field(default_factory=list)


@dataclass
class TickerResult:
    """Terminal result for one ticker. Returned to the CLI for post-run flow."""

    ticker: str
    position_size_gbp: float | None
    asset_type: str
    original_thesis: str
    final_state: dict[str, Any] | None
    stats: dict[str, Any] | None
    duration: float
    error: str | None
    graph: TradingAgentsGraph | None = None  # kept alive for finalize_run


def _build_graph_for_worker(
    selected_analyst_keys: list[str],
    asset_type: str,
    config: dict[str, Any],
) -> tuple[TradingAgentsGraph, StatsCallbackHandler, list[str]]:
    """Create a fresh graph + stats handler scoped to one ticker.

    Returns ``(graph, stats_handler, effective_analyst_keys)``. Effective keys
    drop any analyst incompatible with the per-ticker asset type (e.g. the
    fundamentals analyst is dropped for crypto tickers) so a mixed watchlist
    of stocks and crypto can share one CLI selection.
    """
    from cli.models import AnalystType, AssetType

    asset_enum = AssetType.CRYPTO if asset_type == "crypto" else AssetType.STOCK
    selected_enums = [AnalystType(k) for k in selected_analyst_keys]
    effective_enums = filter_analysts_for_asset_type(selected_enums, asset_enum)
    effective_keys = [e.value for e in effective_enums]

    stats_handler = StatsCallbackHandler()
    graph = TradingAgentsGraph(
        effective_keys,
        config=config,
        debug=False,
        callbacks=[stats_handler],
    )
    return graph, stats_handler, effective_keys


def _summarize_decision(final_state: dict[str, Any]) -> str:
    """Pull a short summary string for the status board / grid subtitle."""
    decision = final_state.get("final_trade_decision") or ""
    if not decision:
        return "done"
    head = decision.strip().splitlines()[0][:80] if decision.strip() else "done"
    return head


def _run_one(
    entry: tuple[str, float | None],
    analysis_date: str,
    selected_analyst_keys: list[str],
    selections: dict[str, Any],
    config: dict[str, Any],
    run_purpose: str,
    states: dict[str, TickerState],
    lock: threading.Lock,
    viewer: Viewer | None = None,
) -> TickerResult:
    """Worker entry point — runs the full pipeline for one ticker."""
    # Late import to avoid a top-level cycle: cli.main imports this module via
    # run_tickers, and we need MessageBuffer + process_chunk_into_buffer from it.
    from cli.main import MessageBuffer, process_chunk_into_buffer

    ticker, position_size_gbp = entry
    asset_type = detect_asset_type(ticker).value
    started_at = time.time()

    with lock:
        st = states[ticker]
        st.started_at = started_at
        st.asset_type = asset_type
        st.position_size_gbp = position_size_gbp
        st.stage = "analysts"

    try:
        graph, stats_handler, effective_keys = _build_graph_for_worker(
            selected_analyst_keys, asset_type, config
        )
        graph.ticker = ticker

        # Per-ticker MessageBuffer drives the per-cell grid view. init_for_analysis
        # seeds agent_status and report_sections based on the *effective* analyst
        # set for this ticker so a mixed watchlist still gets the right rows.
        buffer = MessageBuffer()
        buffer.init_for_analysis(effective_keys)
        with lock:
            states[ticker].buffer = buffer
            states[ticker].stats_handler = stats_handler
            states[ticker].effective_analysts = list(effective_keys)
            # Mark the first analyst as in_progress so the grid shows activity
            # before the first streamed chunk arrives.
            if effective_keys:
                from cli.main import ANALYST_AGENT_NAMES
                first = ANALYST_AGENT_NAMES.get(effective_keys[0])
                if first:
                    buffer.update_agent_status(first, "in_progress")

        if viewer is not None:
            viewer.register(ticker, asset_type, position_size_gbp, effective_keys)
            viewer.update(ticker, buffer, stage="analysts")

        original_thesis = ""
        if run_purpose == "recheck":
            original_thesis = graph.resolve_original_thesis(ticker)
            if not original_thesis:
                duration = time.time() - started_at
                with lock:
                    states[ticker].stage = "failed"
                    states[ticker].finished_at = time.time()
                    states[ticker].error = "no prior thesis (recheck)"
                if viewer is not None:
                    viewer.update(
                        ticker, buffer, stage="failed",
                        error="no prior thesis (recheck)", finished=True,
                    )
                return TickerResult(
                    ticker=ticker,
                    position_size_gbp=position_size_gbp,
                    asset_type=asset_type,
                    original_thesis="",
                    final_state=None,
                    stats=None,
                    duration=duration,
                    error="no prior thesis (recheck)",
                    graph=None,
                )

        instrument_context = graph.resolve_instrument_context(ticker, asset_type)
        graph._resolve_pending_entries(ticker)

        init_state = graph.propagator.create_initial_state(
            ticker,
            analysis_date,
            asset_type=asset_type,
            instrument_context=instrument_context,
            position_size_gbp=position_size_gbp,
            original_thesis=original_thesis,
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        # Drive both the coarse stage indicator AND the per-ticker MessageBuffer
        # (which feeds the grid panel) from every streamed chunk. The buffer
        # update goes through the same helper used by the single-ticker rich UI,
        # so the grid cells show identical agent / report content.
        latest_chunk: dict[str, Any] = {}
        for chunk in graph.graph.stream(init_state, **args):
            latest_chunk = chunk
            process_chunk_into_buffer(buffer, chunk)
            stage = _derive_stage(chunk)
            if stage == "queued":
                continue
            with lock:
                if states[ticker].stage not in ("failed", "done"):
                    states[ticker].stage = stage
            if viewer is not None:
                viewer.update(ticker, buffer, stage=stage)

        final_state = latest_chunk or {}
        # Mirror the single-ticker post-stream loop: force every agent row to
        # "completed" so the grid doesn't end with a stale "in_progress".
        for agent in list(buffer.agent_status.keys()):
            buffer.update_agent_status(agent, "completed")

        duration = time.time() - started_at
        summary = _summarize_decision(final_state)

        with lock:
            states[ticker].stage = "done"
            states[ticker].finished_at = time.time()
            states[ticker].result_summary = summary

        if viewer is not None:
            viewer.update(ticker, buffer, stage="done", finished=True)

        return TickerResult(
            ticker=ticker,
            position_size_gbp=position_size_gbp,
            asset_type=asset_type,
            original_thesis=original_thesis,
            final_state=final_state,
            stats=stats_handler.get_stats(),
            duration=duration,
            error=None,
            graph=graph,
        )

    except Exception as exc:  # noqa: BLE001 — isolate per-ticker failures
        duration = time.time() - started_at
        msg = f"{type(exc).__name__}: {exc}"[:120]
        with lock:
            states[ticker].stage = "failed"
            states[ticker].finished_at = time.time()
            states[ticker].error = msg
        if viewer is not None:
            # ``buffer`` may not exist if we failed before init_for_analysis;
            # use locals().get to avoid an UnboundLocalError on early raises.
            viewer.update(
                ticker, locals().get("buffer"),
                stage="failed", error=msg, finished=True,
            )
        return TickerResult(
            ticker=ticker,
            position_size_gbp=position_size_gbp,
            asset_type=asset_type,
            original_thesis="",
            final_state=None,
            stats=None,
            duration=duration,
            error=msg,
            graph=None,
        )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _elapsed_str(st: TickerState) -> str:
    if st.started_at is None:
        return "—"
    end = st.finished_at or time.time()
    secs = int(end - st.started_at)
    return f"{secs // 60:02d}:{secs % 60:02d}"


def _stage_cell(stage: str) -> str:
    label = STAGE_LABEL.get(stage, stage)
    if stage == "done":
        return f"[green]{label}[/green]"
    if stage == "failed":
        return f"[red]{label}[/red]"
    if stage == "queued":
        return f"[dim]{label}[/dim]"
    return f"[blue]{label}[/blue]"


def _render_board(
    states: dict[str, TickerState],
    started: float,
    max_workers: int,
) -> Panel:
    """Compact one-row-per-ticker status board (large-watchlist fallback)."""
    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("Ticker", style="cyan", width=12)
    table.add_column("Stage", style="green", width=16)
    table.add_column("Elapsed", style="yellow", width=8, justify="right")
    table.add_column("Result", style="white", ratio=1)

    for ticker, st in states.items():
        result_cell = (
            f"[red]{st.error}[/red]" if st.error
            else (st.result_summary or "—")
        )
        table.add_row(ticker, _stage_cell(st.stage), _elapsed_str(st), result_cell)

    wall_secs = int(time.time() - started)
    footer = (
        f"Workers: {max_workers}  |  Elapsed: "
        f"{wall_secs // 60:02d}:{wall_secs % 60:02d}"
    )
    return Panel(table, title="Multi-ticker run", subtitle=footer, border_style="cyan")


# Display order for the per-ticker mini agent table.
_GRID_TEAMS = (
    ("Analyst", ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"]),
    ("Research", ["Bull Researcher", "Bear Researcher", "Research Manager"]),
    ("Trading", ["Trader"]),
    ("Risk", ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]),
    ("Portfolio", ["Portfolio Manager"]),
)


def _render_ticker_panel(st: TickerState) -> Panel:
    """Render one ticker as a rich panel (agent status + current report + tail messages)."""
    buf = st.buffer

    # --- Top: agent status table ---------------------------------------------
    status_tbl = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
        padding=(0, 1),
        expand=True,
    )
    status_tbl.add_column("Team", style="cyan", justify="left")
    status_tbl.add_column("Agent", style="green", justify="left")
    status_tbl.add_column("Status", justify="left")

    if buf is None:
        status_tbl.add_row("—", "—", "[dim]waiting[/dim]")
    else:
        for team, agents in _GRID_TEAMS:
            visible = [a for a in agents if a in buf.agent_status]
            if not visible:
                continue
            for i, agent in enumerate(visible):
                status = buf.agent_status.get(agent, "pending")
                if status == "in_progress":
                    cell: Any = Spinner("dots", text="[blue]running[/blue]", style="bold cyan")
                else:
                    color = {"pending": "yellow", "completed": "green", "error": "red"}.get(status, "white")
                    cell = f"[{color}]{status}[/{color}]"
                status_tbl.add_row(team if i == 0 else "", agent, cell)

    # --- Middle: current report snippet --------------------------------------
    if buf is not None and buf.current_report:
        snippet = buf.current_report
        if len(snippet) > 600:
            snippet = snippet[:600] + "…"
        report_block: Any = Panel(
            Markdown(snippet),
            title="Current report",
            border_style="green",
            padding=(0, 1),
        )
    else:
        report_block = Panel(
            "[italic]waiting for first report…[/italic]",
            title="Current report",
            border_style="green",
            padding=(0, 1),
        )

    # --- Bottom: last few messages ------------------------------------------
    msg_tbl = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        expand=True,
    )
    msg_tbl.add_column("ts", style="cyan", no_wrap=True, width=8)
    msg_tbl.add_column("type", style="green", no_wrap=True, width=8)
    msg_tbl.add_column("content", ratio=1, no_wrap=False)
    if buf is not None:
        rows: list[tuple[str, str, str]] = []
        # Last 3 tool calls and last 3 messages, newest first.
        for ts, name, args in list(buf.tool_calls)[-3:]:
            rows.append((ts, "Tool", f"{name}: {str(args)[:60]}"))
        for ts, mtype, content in list(buf.messages)[-3:]:
            text = str(content) if content else ""
            if len(text) > 160:
                text = text[:157] + "…"
            rows.append((ts, mtype, text))
        # Sort by timestamp; newest at the top.
        rows.sort(key=lambda r: r[0], reverse=True)
        for ts, mtype, content in rows[:5]:
            msg_tbl.add_row(ts, mtype, Text(content, overflow="fold"))
    else:
        msg_tbl.add_row("", "", "[dim]waiting…[/dim]")
    msg_block = Panel(msg_tbl, title="Recent activity", border_style="blue", padding=(0, 1))

    body = Group(status_tbl, report_block, msg_block)

    # --- Title + subtitle ----------------------------------------------------
    pos = f" £{st.position_size_gbp:,.0f}" if st.position_size_gbp else ""
    title = f"[bold cyan]{st.ticker}[/bold cyan]  [dim]({st.asset_type}{pos})[/dim]"

    if st.error:
        subtitle = f"[red]{st.error}[/red]"
        border = "red"
    elif st.stage == "done":
        subtitle = f"[green]done[/green]  •  {_elapsed_str(st)}"
        border = "green"
    else:
        stats = (st.stats_handler.get_stats() if st.stats_handler else {}) or {}
        llm = stats.get("llm_calls", "—")
        subtitle = f"{_stage_cell(st.stage)}  •  {_elapsed_str(st)}  •  LLM {llm}"
        border = "cyan"

    return Panel(body, title=title, subtitle=subtitle, border_style=border, padding=(0, 1))


def _render_grid(
    states: dict[str, TickerState],
    started: float,
    max_workers: int,
) -> Panel:
    """Per-ticker rich panels arranged side by side."""
    panels = [_render_ticker_panel(st) for st in states.values()]
    grid = Columns(panels, equal=True, expand=True)

    wall_secs = int(time.time() - started)
    footer = (
        f"Workers: {max_workers}  |  Elapsed: "
        f"{wall_secs // 60:02d}:{wall_secs % 60:02d}"
    )
    return Panel(grid, title="Multi-ticker run", subtitle=footer, border_style="magenta")


def run_tickers(
    entries: list[tuple[str, float | None]],
    analysis_date: str,
    selected_analyst_keys: list[str],
    selections: dict[str, Any],
    config: dict[str, Any],
    run_purpose: str,
    console: Console | None = None,
    viewer: Viewer | None = None,
) -> list[TickerResult]:
    """Run the pipeline for many tickers concurrently and return per-ticker results.

    ``entries`` is ``[(ticker, position_size_gbp_or_None), ...]``. Concurrency
    is capped by ``config["max_parallel_tickers"]`` (env override
    ``TRADINGAGENTS_MAX_PARALLEL_TICKERS``). The rich per-ticker grid is used
    when ``len(entries) <= GRID_MAX``; otherwise the compact status board.
    """
    console = console or Console()
    cap = int(config.get("max_parallel_tickers", 3) or 1)
    max_workers = max(1, min(len(entries), cap))

    states: dict[str, TickerState] = {t: TickerState(ticker=t) for t, _ in entries}
    lock = threading.Lock()
    started = time.time()
    results: list[TickerResult] = []

    # When the browser viewer is attached, the terminal stays out of the way:
    # no full-screen rich grid (which crowds out everything else on screen and
    # is hard to read for several tickers anyway) — just one line per
    # completion so the user knows the run is progressing.
    headless = viewer is not None

    def _submit_all(executor: ThreadPoolExecutor) -> set:
        return {
            executor.submit(
                _run_one,
                entry, analysis_date, selected_analyst_keys, selections,
                config, run_purpose, states, lock, viewer,
            )
            for entry in entries
        }

    if headless:
        console.print(
            f"[dim]Running {len(entries)} tickers (max {max_workers} parallel)…[/dim]"
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = _submit_all(executor)
            pending = set(futures)
            while pending:
                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    r = future.result()
                    results.append(r)
                    secs = int(r.duration)
                    elapsed = f"{secs // 60:02d}:{secs % 60:02d}"
                    if r.error:
                        console.print(f"  [red]✗ {r.ticker}[/red]  {elapsed}  {r.error}")
                    else:
                        console.print(f"  [green]✓ {r.ticker}[/green]  {elapsed}")
    else:
        render = _render_grid if len(entries) <= GRID_MAX else _render_board
        with Live(
            render(states, started, max_workers),
            console=console,
            refresh_per_second=2,
        ) as live:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = _submit_all(executor)
                pending = set(futures)
                while pending:
                    done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for future in done:
                        results.append(future.result())
                    live.update(render(states, started, max_workers))
            live.update(render(states, started, max_workers))

    # Preserve user input order in the returned list so summaries read naturally.
    by_ticker = {r.ticker: r for r in results}
    return [by_ticker[t] for t, _ in entries if t in by_ticker]
