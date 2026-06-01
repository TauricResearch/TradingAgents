"""Drop-in replacement for TradingAgentsGraph that emits scripted events."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ScriptedNode:
    name: str
    events: list[dict] = field(default_factory=list)
    state_patch: dict = field(default_factory=dict)


@dataclass
class ScriptedRun:
    nodes: list[ScriptedNode]
    final_state: dict
    fail_after: Optional[str] = None  # node name; if set, raise after that node
    rate_limit_count: int = 0  # how many times to raise RateLimitError before succeeding


class RateLimitError(RuntimeError):
    pass


class FakeGraph:
    def __init__(self, run: ScriptedRun):
        self._run = run

    def propagate(self, ticker: str, trade_date: str, *, event_callback: Optional[Callable] = None):
        from web.server import events
        from web.server.runner import _to_run_id
        # ScriptedRun uses sentinel run_id 0; the runner overrides
        raise NotImplementedError("Use FakeTradingAgents wrapper")


class FakeTradingAgents:
    """Acts like TradingAgentsGraph but uses the ScriptedRun for the runner."""
    def __init__(self, script: ScriptedRun):
        self._script = script

    def propagate(self, ticker: str, trade_date: str, *, event_callback=None):
        rl_remaining = self._script.rate_limit_count
        for node in self._script.nodes:
            if event_callback is not None:
                event_callback("node_entered", {"node": node.name})
            for ev in node.events:
                event_callback(ev["type"], ev.get("data", {}))
            if rl_remaining > 0:
                rl_remaining -= 1
                raise RateLimitError("simulated 429")
            if self._script.fail_after == node.name:
                raise RuntimeError(f"simulated failure at {node.name}")
        return self._script.final_state


def happy_path(ticker: str) -> ScriptedRun:
    return ScriptedRun(
        nodes=[
            ScriptedNode("Market Analyst", [
                {"type": "analyst_thinking", "data": {"stage": "market", "message": "analyzing prices"}},
                {"type": "analyst_completed", "data": {"stage": "market", "summary": "bullish"}},
            ]),
            ScriptedNode("Bull Researcher", [
                {"type": "debate_message", "data": {"side": "bull", "round": 1, "text": "upside"}},
            ]),
            ScriptedNode("Bear Researcher", [
                {"type": "debate_message", "data": {"side": "bear", "round": 1, "text": "downside"}},
            ]),
            ScriptedNode("Trader", [
                {"type": "decision", "data": {"action": "BUY", "target": 260.0, "rationale": "ok", "confidence": 0.8}},
            ]),
        ],
        final_state={"decision": {"action": "BUY", "target": 260.0}},
    )
