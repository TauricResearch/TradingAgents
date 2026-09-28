"""Prompt-free, per-run progress driven by LangGraph callback events.

This is an observer, not a second graph runner. Never retain prompts, tool
arguments, headers or raw exception messages in its activity log.
"""

from __future__ import annotations

import os
import sys
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from time import monotonic

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from cli.stats_handler import StatsCallbackHandler

# Presentation labels only; the graph remains responsible for execution order.
_ANALYSTS = {
    "market": ("Market Analyst", "market_report"),
    "social": ("Sentiment Analyst", "sentiment_report"),
    "news": ("News Analyst", "news_report"),
    "fundamentals": ("Fundamentals Analyst", "fundamentals_report"),
}
_FIXED_TEAMS = {
    "Research": ("Bull Researcher", "Bear Researcher", "Research Manager"),
    "Trading": ("Trader",),
    "Risk": ("Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"),
    "Portfolio": ("Portfolio Manager",),
}
_RESEARCH = ("Bull Researcher", "Bear Researcher")
_RISK = ("Aggressive Analyst", "Neutral Analyst", "Conservative Analyst")
_LOOP_AGENTS = frozenset((*_RESEARCH, *_RISK))


def resolve_progress_mode(requested: bool | None, json_output: bool, *, stdout=None, stderr=None) -> str:
    """Auto: live only in a normal terminal; explicit on: plain fallback in pipes.

    Call BEFORE redirect_stdout: otherwise a piped stdout looks like stderr.
    JSON disables only the automatic display; --json --progress uses stderr.
    """
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    terminal = bool(getattr(stderr, "isatty", lambda: False)())
    terminal = terminal and os.environ.get("TERM", "").lower() != "dumb"
    if requested is False:
        return "off"
    if requested is True:
        return "live" if terminal else "plain"
    return "live" if terminal and not json_output and getattr(stdout, "isatty", lambda: False)() else "off"


@dataclass
class AgentProgress:
    team: str
    status: str = "pending"
    turns: int = 0
    seconds: float = 0.0
    started: float | None = None


class AnalysisProgress(StatsCallbackHandler):
    """Thread-safe callback state and Rich rendering, isolated from the UI globals."""

    def __init__(self, symbol: str, date: str, analysts: list[str], *, console: Console, plain=False):
        super().__init__()
        self.console = console
        self.plain = plain
        self.symbol, self.date = symbol, date
        self.started = monotonic()
        self.phase = "Preparing analysis"
        self.agents = {_ANALYSTS[key][0]: AgentProgress("Analysts") for key in analysts}
        self.agents.update({name: AgentProgress(team) for team, names in _FIXED_TEAMS.items() for name in names})
        self.report_agents = {_ANALYSTS[key][1]: _ANALYSTS[key][0] for key in analysts}
        self.report_agents.update(investment_plan="Research Manager", trader_investment_plan="Trader",
                                  final_trade_decision="Portfolio Manager")
        self.reports: set[str] = set()
        self.activity: deque[str] = deque(maxlen=3)
        self._state_lock = RLock()
        self._root = None
        self._nodes: dict = {}

    def _event(self, text: str) -> None:
        self.activity.append(text)
        if self.plain:
            # No ANSI, Rich markup, model text, prompts or tool arguments in logs.
            self.console.file.write(f"[{int(monotonic() - self.started):>4}s] {text}\n")
            self.console.file.flush()

    def stage(self, text: str) -> None:
        with self._state_lock:
            self.phase = text
            self._event(text)

    def _finish_turn(self, name: str, status: str) -> None:
        row = self.agents[name]
        if row.started is not None:
            row.seconds += monotonic() - row.started
            row.started = None
        row.status = status

    def _observe_state(self, state) -> None:
        """Recover report/debate status from node inputs too (checkpoint resume)."""
        if not isinstance(state, dict):
            return
        for key, agent in self.report_agents.items():
            if state.get(key):
                self.reports.add(key)
                if self.agents[agent].started is None:
                    self.agents[agent].status = "completed"
        for key, names, fields in (
            ("investment_debate_state", _RESEARCH, ("bull_history", "bear_history")),
            ("risk_debate_state", _RISK, ("aggressive_history", "neutral_history", "conservative_history")),
        ):
            debate = state.get(key)
            if isinstance(debate, dict):
                for name, field in zip(names, fields, strict=True):
                    if debate.get(field) and self.agents[name].started is None:
                        self.agents[name].status = "completed" if debate.get("judge_decision") else "waiting"

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, metadata=None, **kwargs):
        with self._state_lock:
            if parent_run_id is None:
                self._root = run_id
                self.phase = "Running analysis"
                self._observe_state(inputs)
                return
            node = (metadata or {}).get("langgraph_node")
            # Only direct graph nodes, not nested prompts, parsers or router chains.
            if parent_run_id != self._root or kwargs.get("name") != node:
                return
            if node not in self.agents and node not in {f"tools_{key}" for key in _ANALYSTS}:
                return
            self._nodes[run_id] = node
            self._observe_state(inputs)
            if node.startswith("tools_"):
                self.phase = f"Fetching data: {_ANALYSTS[node[6:]][0]}"
                return
            if node == "Research Manager":
                for name in _RESEARCH:
                    if self.agents[name].status == "waiting":
                        self._finish_turn(name, "completed")
            elif node == "Portfolio Manager":
                for name in _RISK:
                    if self.agents[name].status == "waiting":
                        self._finish_turn(name, "completed")
            row = self.agents[node]
            row.status = "running"
            row.turns += 1
            row.started = monotonic()
            self.phase = node
            self._event(f"{node}: running (turn {row.turns})")

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        with self._state_lock:
            if run_id == self._root:
                self._observe_state(outputs)
                self.phase = "Finalizing analysis"
                return
            node = self._nodes.pop(run_id, None)
            if node is None:
                return
            self._observe_state(outputs)
            if node not in self.agents:
                return
            messages = outputs.get("messages", []) if isinstance(outputs, dict) else []
            last = messages[-1] if messages else None
            tool_calls = last.get("tool_calls") if isinstance(last, dict) else getattr(last, "tool_calls", None)
            status = "waiting" if node in _LOOP_AGENTS or tool_calls else "completed"
            self._finish_turn(node, status)
            self._event(f"{node}: {'turn complete' if status == 'waiting' else 'completed'}")

    def on_chain_error(self, error, *, run_id, **kwargs):
        with self._state_lock:
            node = self._nodes.pop(run_id, None)
            if node in self.agents:
                self._finish_turn(node, "error")
            elif node and node.startswith("tools_"):
                self._finish_turn(_ANALYSTS[node[6:]][0], "error")
            # Nested errors may be handled by an agent's structured-output retry.
            # Only the outer context decides whether the overall run failed.

    def on_tool_start(self, serialized, input_str, **kwargs):
        super().on_tool_start(serialized, input_str, **kwargs)
        name = str((serialized or {}).get("name", "tool"))
        name = "".join(c for c in name if c.isprintable())[:80]
        with self._state_lock:
            self._event(f"Tool: {name}")

    def on_llm_error(self, error, **kwargs):
        with self._state_lock:
            self._event("LLM attempt failed; an agent may retry")

    def fail(self, error: BaseException) -> None:
        with self._state_lock:
            for name, row in self.agents.items():
                if row.started is not None:
                    self._finish_turn(name, "error")
            self.phase = "Interrupted" if isinstance(error, KeyboardInterrupt) else "Failed"
            self._event(self.phase)

    def complete(self) -> None:
        # Called only AFTER both reports and run.json have been written.
        self.stage("Completed; reports saved")

    def render(self):
        with self._state_lock:
            elapsed = int(monotonic() - self.started)
            stats = self.get_stats()
            completed = sum(row.status == "completed" for row in self.agents.values())
            stats_text = Text(
                f"Elapsed {elapsed // 60:02d}:{elapsed % 60:02d} | Agents {completed}/{len(self.agents)} | "
                f"Reports {len(self.reports)}/{len(self.report_agents)} | "
                f"LLM {stats['llm_calls']} | Tools {stats['tool_calls']} | "
                f"Tokens {stats['tokens_in']:,} in / {stats['tokens_out']:,} out"
            )
            parts = [stats_text]
            if self.console.size.width >= 80 and self.console.size.height >= len(self.agents) + 9:
                table = Table(expand=True, box=None, padding=(0, 1))
                for column in ("Team", "Agent", "Status", "Turns", "Time"):
                    table.add_column(column)
                for name, row in self.agents.items():
                    seconds = row.seconds + (monotonic() - row.started if row.started is not None else 0)
                    cell = Spinner("dots", text="running") if row.status == "running" else Text(
                        row.status, style={"completed": "green", "error": "red", "waiting": "yellow"}.get(row.status, "dim")
                    )
                    table.add_row(row.team, name, cell, str(row.turns), f"{seconds:.0f}s")
                parts.append(table)
            else:
                # Keep the active stage and counters visible in short/narrow terminals.
                active = ", ".join(name for name, row in self.agents.items() if row.status == "running")
                parts.append(Text(f"Current: {active or self.phase}"))
            parts.extend(Text(line, overflow="ellipsis", no_wrap=True) for line in self.activity)
            return Panel(Group(*parts), title=Text(f"TradingAgents | {self.symbol} | {self.date}"),
                         subtitle=Text(self.phase), border_style="cyan")


@contextmanager
def analysis_progress(mode: str, symbol: str, date: str, analysts: list[str]):
    if mode == "off":
        yield None
        return
    if mode not in {"live", "plain"}:
        raise ValueError("progress mode must be live, plain or off")
    # Pin the stream before Rich installs a FileProxy; always write to stderr.
    console = Console(file=sys.stderr)
    progress = AnalysisProgress(symbol, date, analysts, console=console, plain=mode == "plain")
    live = Live(console=console, get_renderable=progress.render, refresh_per_second=4,
                transient=True, redirect_stdout=True, redirect_stderr=True) if mode == "live" else None
    try:
        if live is not None:
            live.start(refresh=True)
        progress.stage("Preparing analysis")
        yield progress
    except BaseException as exc:
        progress.fail(exc)
        raise
    finally:
        if live is not None:
            live.stop()
