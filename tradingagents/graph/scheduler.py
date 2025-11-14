"""Action scheduler node for orchestrator-controlled execution."""

from __future__ import annotations

from typing import Dict, Any


DISPATCH_MAP = {
    "market": "Market Analyst",
    "news": "News Analyst",
    "social": "Social Analyst",
    "fundamentals": "Fundamentals Analyst",
    "debate": "Bull Researcher",
    "manager": "Research Manager",
    "trader": "Trader",
    "risk": "Risky Analyst",
    "orchestrator": "Portfolio Orchestrator",
}


def create_action_scheduler():
    """Return a node that routes execution based on the orchestrator's queue."""

    def scheduler_node(state: Dict[str, Any]) -> Dict[str, Any]:
        queue = list(state.get("action_queue") or [])
        if queue:
            action = str(queue.pop(0) or "").strip().lower()
            next_node = DISPATCH_MAP.get(action, "Portfolio Orchestrator")
            try:
                print(f"[Action Scheduler] Dispatching '{action}' to {next_node}")
            except Exception:
                pass
            return {
                "action_queue": queue,
                "next_node": next_node,
            }

        directive = (state.get("next_directive") or "stop").lower()
        if directive in {"continue", "orchestrator"}:
            next_node = "Portfolio Orchestrator"
            try:
                print(f"[Action Scheduler] Queue empty; returning control to orchestrator (directive={directive}).")
            except Exception:
                pass
            return {
                "action_queue": queue,
                "next_node": next_node,
            }

        next_node = DISPATCH_MAP.get(directive, "end")
        try:
            print(f"[Action Scheduler] No pending actions; directive '{directive}' maps to {next_node}.")
        except Exception:
            pass
        return {
            "action_queue": queue,
            "next_node": next_node,
        }

    return scheduler_node
