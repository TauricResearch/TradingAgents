"""The once-a-day runner: analyze a watchlist, plan, risk-check, maybe execute.

``run_daily`` is the scheduling surface for FR-K3/FR-D: one independent
process per invocation, one coin at a time, a failing coin never stops the
rest. Each coin runs the full crypto pipeline (LLM in the loop), syncs the
venue balance, plans through the bridge (which applies the RiskGuard), and
then decides the confirm policy:

- default (``exec_auto_confirm`` not a literal True): the plan is audited
  and LEFT FOR HUMAN APPROVAL -- nothing is ever sent;
- auto-confirm DRY: executes the dry fill automatically ONLY when the
  third gate (FR-S2) is fully open -- the config ``exec_auto_confirm`` key
  must be a literal True AND the ``TRADINGAGENTS_EXEC_AUTO_CONFIRM`` env
  flag must read true at call time, fail-closed;
- auto-confirm LIVE: additionally requires the FR5 config gate
  (``exec_live`` literal True). Anything missing falls back to
  waiting for approval, with the reason audited.

WARNING: combining an unattended scheduler with auto-confirm LIVE means
real money moves without a human in the loop. That combination is
deliberately gated three ways and should stay off until a dry-run schedule
has run clean for long enough that you trust the whole chain.

Scheduling examples (one process per run; no long-lived daemon here):

cron (Linux/macOS), weekdays at 13:30 UTC:
    30 13 * * 1-5  cd /path/to/project && .venv/bin/python -c \\
        "from tradingagents.execution.daily import run_daily; run_daily()" \\
        >> ~/.tradingagents/logs/daily.log 2>&1

Windows Task Scheduler (schtasks), daily at 08:30 local:
    schtasks /Create /TN "TradingAgents daily" /SC DAILY /ST 08:30 /TR \\
        "cmd /c cd /d C:\\path\\to\\project && .venv\\Scripts\\python.exe -c \\"from tradingagents.execution.daily import run_daily; run_daily()\\""

Note that each run spends LLM quota (one full agent pipeline per coin) and,
with the live gates armed, can place real orders. Do NOT configure
overlapping cron/schtasks schedules for the same watchlist: the
check-then-execute sequence has no cross-process lock, so two overlapping
runs can both pass their re-checks and double the exposure. The date is
UTC today:
``propagate`` receives ``YYYY-MM-DD`` and the pipeline's point-in-time
contract applies unchanged.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from tradingagents.default_config import _BOOL_TRUE
from tradingagents.execution.bridge import ExchangeBridge
from tradingagents.portfolio import PortfolioContext

logger = logging.getLogger(__name__)


def _env_auto_confirm_flag() -> bool:
    """Read TRADINGAGENTS_EXEC_AUTO_CONFIRM at call time, fail-closed.

    Deliberately absent from _ENV_OVERRIDES, like TRADINGAGENTS_EXEC_LIVE:
    its only consumer is this read, so it can never arm the config half.
    """
    raw = os.environ.get("TRADINGAGENTS_EXEC_AUTO_CONFIRM")
    if not raw:
        return False
    return raw.strip().lower() in _BOOL_TRUE


class DailyResult(BaseModel):
    """Per-coin outcome of one ``run_daily`` invocation."""

    ticker: str
    signal: str | None = None
    plan: Any | None = None  # PlannedOrder | None
    executed: bool = False
    order_id: str | None = None
    reason: str | None = None


def _today_iso() -> str:
    """UTC today as ``YYYY-MM-DD``; tests freeze the day by monkeypatching."""
    return datetime.now(timezone.utc).date().isoformat()


def _normalize_watchlist(raw: Any) -> list[str]:
    """Coerce a watchlist at the runner boundary (FR-S4).

    A bare string wraps into a one-element list (never ``list()``-split into
    characters), every entry is stripped, empties are dropped and
    duplicates removed keeping first-seen order.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    coins: list[str] = []
    for entry in raw:
        coin = str(entry).strip()
        if coin and coin not in coins:
            coins.append(coin)
    return coins


def run_daily(
    watchlist: list[str] | str | None = None,
    config: dict | None = None,
) -> list[DailyResult]:
    """Analyze ``watchlist`` (default ``exec_watchlist``) and handle each plan.

    The watchlist is normalized at this boundary: a bare string becomes a
    one-coin list, entries are stripped, empties dropped and duplicates
    deduped in order. Returns one ``DailyResult`` per coin. A coin that
    raises anywhere in its own pipeline (propagate, balance sync, planning)
    is recorded with the error and the loop continues. Never raises for a
    single coin's failure.
    """
    bridge = ExchangeBridge(config=config)
    raw = watchlist if watchlist is not None else bridge.config.get("exec_watchlist")
    coins = _normalize_watchlist(raw)
    today = _today_iso()
    # Lazy import (like ccxt in bridge.py): importing tradingagents.execution
    # stays cheap and tests can mock the graph class wholesale.
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    results: list[DailyResult] = []
    for coin in coins:
        result = DailyResult(ticker=coin)
        try:
            graph = TradingAgentsGraph(config=bridge.config)
            _, signal = graph.propagate(coin, today, asset_type="crypto")
            result.signal = signal
            portfolio = bridge.sync_portfolio()
            plan = bridge.plan_order(coin, signal, portfolio=portfolio)
            result.plan = plan
            _handle_plan(bridge, plan, portfolio, result)
        except Exception as exc:  # one coin's failure never stops the watchlist
            logger.exception("run_daily: %s failed", coin)
            result.reason = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results


def _handle_plan(
    bridge: ExchangeBridge,
    plan: Any,
    portfolio: PortfolioContext,
    result: DailyResult,
) -> None:
    """Apply the confirm policy to one planned order, recording the outcome."""
    if plan.side is None:
        result.reason = plan.reason  # Hold, REVIEW, sizing refusal or risk rejection
        return
    if bridge.config.get("exec_auto_confirm") is not True:
        _wait_for_approval(bridge, plan, "exec_auto_confirm is not enabled; plan awaits approval")
        result.reason = "awaiting approval"
        return
    if not _env_auto_confirm_flag():
        # FR-S2's second half of the third gate: the env flag must read true
        # at call time in dry and live alike -- fail-closed, so one variable
        # (the config literal) never arms auto-confirm alone.
        _wait_for_approval(
            bridge,
            plan,
            "auto-confirm requires TRADINGAGENTS_EXEC_AUTO_CONFIRM=true at call "
            "time; plan awaits approval",
        )
        result.reason = "awaiting approval (auto-confirm env gate closed)"
        return
    if bridge.effective_mode() == "dry":
        result.order_id = bridge.execute_order(plan, confirm=True, portfolio=portfolio)
        result.executed = True
        return
    if bridge.config.get("exec_live") is not True:
        _wait_for_approval(
            bridge,
            plan,
            "auto-confirm on a live venue requires exec_live=True; plan awaits approval",
        )
        result.reason = "awaiting approval (live auto-confirm gate closed)"
        return
    result.order_id = bridge.execute_order(plan, confirm=True, portfolio=portfolio)
    result.executed = True


def _wait_for_approval(bridge: ExchangeBridge, plan: Any, reason: str) -> None:
    """Audit the waiting-for-approval decision so nothing happens silently."""
    bridge.audit_plan(plan, action="awaiting_approval", reason=reason)
