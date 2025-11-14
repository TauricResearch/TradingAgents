"""Lightweight Sequential Thinking MCP server bundled with TradingAgents."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Set

from mcp.server.fastmcp import FastMCP, Context

app = FastMCP(
    name="Sequential Thinking Planner",
    instructions=(
        "Generate ordered action plans for the TradingAgents workflow. "
        "Return a list of analyst/manager nodes to execute and any notes for the orchestrator."
    ),
)

_DEFAULT_ANALYST_ORDER = ["market", "news", "social", "fundamentals"]
_SUPPORT_STAGES = ["debate", "manager", "trader", "risk"]


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    cleaned = text.replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _normalise(role: str) -> str:
    mapping = {
        "market_analyst": "market",
        "run_market": "market",
        "news_analyst": "news",
        "run_news": "news",
        "social_analyst": "social",
        "fundamental": "fundamentals",
        "fundamentals_analyst": "fundamentals",
        "research_manager": "manager",
        "risk_manager": "risk",
        "stop": "end",
    }
    key = (role or "").strip().lower()
    return mapping.get(key, key)


def _append_unique(target: List[str], items: List[str]) -> None:
    seen = set(target)
    for value in items:
        if value and value not in seen:
            target.append(value)
            seen.add(value)


@app.tool()
async def sequential_thinking(ctx: Context, request: Dict[str, Any]) -> Dict[str, Any]:
    """Return a sequential plan for TradingAgents."""

    active = (request or {}).get("active_hypothesis") or {}
    immediate_raw = str(active.get("immediate_actions") or active.get("action") or "").lower()
    immediate_action = immediate_raw if immediate_raw in {"monitor", "escalate", "trade", "execute"} else "monitor"
    priority_val = float(active.get("priority") or 0)
    focus_symbol = str(request.get("focus_symbol") or active.get("ticker") or "").upper()

    required = [
        _normalise(role)
        for role in active.get("required_analysts", [])
    ]
    required = [role for role in required if role in {"market", "news", "social", "fundamentals"}]

    actions: List[str] = []
    if required:
        _append_unique(actions, required)
    else:
        _append_unique(actions, _DEFAULT_ANALYST_ORDER)

    notes_parts = []
    reasoning: List[str] = []
    summary = request.get("summary") or ""
    if summary:
        notes_parts.append(summary)
    reasoning.append(f"Initial directive: {immediate_action.upper()}")
    if immediate_action in {"monitor", "escalate", "trade", "execute"}:
        notes_parts.append(f"Directive: {immediate_action.upper()}")
    portfolio = request.get("account_summary") or {}
    buying_power = portfolio.get("buying_power") or portfolio.get("buying_power_usd")
    cash = portfolio.get("cash") or portfolio.get("cash_usd")
    buying_power_val = _to_float(buying_power)
    cash_val = _to_float(cash)
    portfolio_value = _to_float(portfolio.get("portfolio_value") or portfolio.get("equity"))
    if buying_power or cash:
        notes_parts.append(
            "Capital -> "
            + ", ".join(filter(None, [f"Cash: {cash}" if cash else "", f"Buying Power: {buying_power}" if buying_power else ""]))
        )

    trade_policy = request.get("trade_policy") or {}
    priority_threshold = float(trade_policy.get("priority_threshold", 0.8))
    min_cash_abs = float(trade_policy.get("min_cash_absolute", 0))
    min_cash_ratio = float(trade_policy.get("min_cash_ratio", 0))
    min_cash_required = max(min_cash_abs, portfolio_value * min_cash_ratio)

    positions_summary = request.get("positions_summary") or []
    held_symbols: Set[str] = set()
    for pos in positions_summary:
        symbol = str(pos.get("symbol") or pos.get("symbol:") or "").upper()
        qty_val = _to_float(pos.get("quantity") or pos.get("qty") or 0)
        if symbol and qty_val != 0:
            held_symbols.add(symbol)

    reasoning.append(
        f"Policy thresholds -> priority >= {priority_threshold:.2f}, min cash ${min_cash_required:,.0f}"
    )

    if immediate_action in {"", "monitor"} and focus_symbol:
        reasoning.append(
            f"Evaluating {focus_symbol}: priority {priority_val:.2f}, buying power ${buying_power_val:,.0f}"
        )
        if priority_val >= priority_threshold:
            if focus_symbol not in held_symbols and buying_power_val >= min_cash_required:
                immediate_action = "trade"
                notes_parts.append(f"Auto-upgraded to TRADE for {focus_symbol}")
                reasoning.append("Priority high and sufficient buying power -> promote to TRADE")
            elif buying_power_val > 0:
                immediate_action = "escalate"
                notes_parts.append(f"Escalate {focus_symbol} due to priority {priority_val:.2f}")
                reasoning.append("Priority high but capital reserved -> escalate to manager")
            else:
                notes_parts.append("Insufficient buying power to escalate")
                reasoning.append("Insufficient buying power -> remain monitoring")
        else:
            reasoning.append("Priority below threshold -> remain monitoring")

    if immediate_action in {"trade", "execute"}:
        _append_unique(actions, ["debate", "manager"])
        _append_unique(actions, ["trader"])
        _append_unique(actions, ["risk"])
        if focus_symbol:
            notes_parts.append(
                f"Queue trader for {focus_symbol} (buying power ${buying_power_val:,.0f}, cash ${cash_val:,.0f})"
            )
            reasoning.append("Trader and risk review queued for execution")
    elif immediate_action == "escalate":
        _append_unique(actions, ["debate", "manager"])
        if focus_symbol:
            notes_parts.append(f"Manager review requested for {focus_symbol}")
        reasoning.append("Escalation path via manager")
    else:
        if required:
            _append_unique(actions, required)
        else:
            _append_unique(actions, _DEFAULT_ANALYST_ORDER)
        reasoning.append("Maintain analyst coverage with monitoring loop")

    return {
        "actions": actions,
        "next_decision": immediate_action,
        "notes": "\n".join(notes_parts).strip(),
        "reasoning": reasoning,
    }


async def _main_async() -> None:
    await app.run_stdio_async()


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
