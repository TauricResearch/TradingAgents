"""View models: JSON-serializable projections for the dashboard.

Pure functions over RunRecords, ProMemory, and BacktestResults — fully
testable without FastAPI. Every recommendation view renders the complete
TradeRecommendation schema (Phase 0 requirement): action, confidence,
levels, ladder, size, regime, evidence, counterarguments, vote breakdown,
historical analogs, and the derived risk/reward.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from tradingagents.contracts import TradeAction, TradeRecommendation
from tradingagents.pro.backtest import BacktestResult
from tradingagents.pro.dashboard.recorder import RunRecord
from tradingagents.pro.memory import MemoryKind, ProMemory


def market_overview(run: RunRecord | None) -> dict:
    if run is None:
        return {"status": "no runs yet"}
    summary = run.snapshot_summary()
    summary.update({
        "run_id": run.run_id,
        "started_at": run.started_at.isoformat(),
        "execution_status": run.state.get("execution_status"),
        "rejected_at": run.rejection and run.rejection.get("stage"),
    })
    return summary


def _mark_for(symbol: str, ticks, marketdata) -> tuple[float | None, str]:
    """Best available mark price with an honest provenance label:
    live tick > latest daily close (eod) > none (falls back to entry)."""
    if ticks is not None:
        cached = ticks.get(symbol)
        if cached is not None:
            return cached[0], "live"
    if marketdata is not None:
        try:
            bars = marketdata.get_bars(symbol, "1d", limit=1)
            if bars:
                return bars[-1].close, "eod"
        except Exception:  # degraded vendor must not break /api/status
            pass
    return None, "entry"


def open_positions_view(router, equity: float | None,
                        ticks=None, marketdata=None) -> tuple[list[dict], float | None]:
    """Positions with entry/mark/unrealized P&L (trader review G2).

    Entry comes from the venue adapter's book (avg_price); mark from the
    tick cache or daily close, labeled. Anything unknowable is null —
    never a fabricated number.
    """
    entries: dict[str, float] = {}
    adapter = getattr(router, "adapter", None)
    if adapter is not None:
        try:
            for pos in adapter.positions():
                entries[pos.symbol] = pos.avg_price
        except Exception:
            pass
    positions: list[dict] = []
    unrealized_total: float | None = None
    for symbol, quantity in sorted(router.local_book.items()):
        entry = entries.get(symbol)
        mark, mark_source = _mark_for(symbol, ticks, marketdata)
        if mark is None and entry is not None:
            mark = entry
        unrealized = (
            (mark - entry) * quantity
            if mark is not None and entry is not None and mark_source != "entry"
            else None
        )
        if unrealized is not None:
            unrealized_total = (unrealized_total or 0.0) + unrealized
        exposure_pct = (
            abs(quantity * mark) / equity * 100.0
            if mark is not None and equity else None
        )
        positions.append({
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry,
            "mark_price": mark,
            "mark_source": mark_source,
            "unrealized_pnl": unrealized,
            "exposure_pct": exposure_pct,
        })
    return positions, unrealized_total


def system_status(router, equity: float | None = None, arming=None,
                  ticks=None, marketdata=None) -> dict:
    """Kill switch, circuit breaker, open book, and per-pair arming
    (UX review RISK-01; go-live Phase 4).

    ``router`` is an ExecutionRouter or None (dashboard attached to a
    replay/monitor-only state). Read-only: reset stays an operator action.
    ``arming`` is an ArmingStore or None; absent = every pair is PAPER.
    """
    arming_view = arming.status() if arming is not None else {}
    live_armed = any(v["tier"] in ("canary", "live")
                     for v in arming_view.values())
    if router is None:
        return {"attached": False, "trading_halted": None,
                "arming": arming_view, "live_armed": live_armed}
    breaker = router.breaker.check()
    engaged = router.kill_switch.engaged
    positions, unrealized_total = open_positions_view(
        router, equity, ticks=ticks, marketdata=marketdata)
    return {
        "attached": True,
        "kill_switch": {"engaged": engaged, "reason": router.kill_switch.reason},
        "circuit_breaker": {"tripped": breaker.tripped, "reason": breaker.reason},
        "open_positions": positions,
        "unrealized_total": unrealized_total,
        "equity": equity,
        "trading_halted": engaged or breaker.tripped,
        "arming": arming_view,
        "live_armed": live_armed,
    }


def alert_feed(runs: Sequence[RunRecord], limit: int = 50) -> dict:
    """Operational events derived from run records, newest first (ALERT-02).

    severity: critical = security (quarantined injection), warning = a
    stage refused the trade, info = degraded inputs the agents disclosed.
    """
    alerts: list[dict] = []
    for run in runs:
        def add(severity: str, text: str, run=run) -> None:
            alerts.append({
                "time": run.started_at.isoformat(),
                "run_id": run.run_id,
                "severity": severity,
                "text": text,
            })

        snapshot = run.state.get("snapshot")
        for feed in (snapshot.missing_feeds if snapshot else []):
            if feed.startswith("news:quarantined"):
                add("critical", f"suspected prompt injection quarantined ({feed})")
            else:
                add("info", f"feed unavailable: {feed}")
        if run.rejection:
            reasons = "; ".join(str(r) for r in run.rejection.get("reasons", []))
            add("warning",
                f"trade rejected at {run.rejection.get('stage')}"
                + (f": {reasons}" if reasons else ""))
        execution_status = run.state.get("execution_status") or ""
        if execution_status.startswith("blocked:"):
            add("warning", f"execution {execution_status}")
    alerts.reverse()
    return {"alerts": alerts[:limit]}


def recommendation_view(rec: TradeRecommendation | None,
                        invalidation: str | None = None,
                        rejection: dict | None = None) -> dict:
    if rec is None:
        if rejection:  # EXPL-01: a rejected run explains itself
            return {"status": "rejected", "rejection": rejection}
        return {"status": "no recommendation"}
    view = rec.model_dump(mode="json")  # the full Phase 0 schema, verbatim
    view["vote_tally"] = {
        action.value: count for action, count in rec.vote_breakdown.tally().items()
    }
    view["n_evidence"] = len(rec.evidence)
    view["n_counterarguments"] = len(rec.counterarguments)
    # the reflection stage's falsifiability condition (UX review EXPL-02)
    view["invalidation"] = invalidation
    view["rejection"] = rejection
    return view


def debate_timeline(run: RunRecord) -> dict:
    return {
        "run_id": run.run_id,
        "node_sequence": list(run.node_sequence),
        "entries": [
            {
                "speaker": e["speaker"],
                "stance": e.get("stance"),
                "confidence": e.get("confidence"),
                "argument": e["argument"],
                "cited": e.get("cited", []),
            }
            for e in run.debate
        ],
        "rejection": run.rejection,
    }


def evidence_panels(run: RunRecord) -> dict:
    panels = {}
    for team, evidence in run.state.get("evidence_by_team", {}).items():
        panels[team] = [
            {
                "agent_id": e.agent_id,
                "direction": e.direction.value,
                "confidence": e.confidence,
                "claim": e.claim,
                "data_refs": [
                    {"name": r.name, "value": r.value} for r in e.data_refs
                ],
                "sources": [s.id for s in e.sources],
            }
            for e in evidence
        ]
    return panels


def trade_journal(memory: ProMemory) -> dict:
    trades = {r.id: r for r in memory.records(MemoryKind.TRADE)}
    entries = []
    total_pnl = 0.0
    by_mode: dict[str, dict] = {}
    for outcome in memory.records(MemoryKind.OUTCOME):
        trade = trades.get(outcome.ref_id)
        pnl = outcome.payload.get("pnl", 0.0)
        total_pnl += pnl
        # venue truth + arming mode ride in the outcome payload (Phase 5);
        # paper trades default to mode "paper" with zero venue fields
        mode = outcome.payload.get("mode", "paper")
        won = outcome.payload.get("won")
        entries.append({
            "symbol": outcome.symbol,
            "action": trade.payload.get("action") if trade else None,
            "regime": trade.payload.get("regime") if trade else None,
            "pnl": pnl,
            "won": won,
            "closed_at": outcome.created_at.isoformat(),
            "mode": mode,
            "commission": outcome.payload.get("commission", 0.0),
            "venue_order_id": outcome.payload.get("venue_order_id", ""),
            "fill_price": outcome.payload.get("fill_price"),
            "entry_price": outcome.payload.get("entry_price"),
        })
        bucket = by_mode.setdefault(mode, {"n_trades": 0, "wins": 0,
                                           "total_pnl": 0.0})
        bucket["n_trades"] += 1
        bucket["wins"] += 1 if won else 0
        bucket["total_pnl"] += pnl
    for bucket in by_mode.values():
        bucket["win_rate"] = (bucket["wins"] / bucket["n_trades"]
                              if bucket["n_trades"] else None)
    wins = sum(1 for e in entries if e["won"])
    return {
        "entries": entries,
        "total_pnl": total_pnl,
        "n_trades": len(entries),
        "win_rate": wins / len(entries) if entries else None,
        "by_mode": by_mode,
    }


def backtest_view(result: BacktestResult | None, monte_carlo=None) -> dict:
    if result is None:
        return {"status": "no backtest yet"}
    view = {
        "report": result.report.as_dict(),
        "final_equity": result.final_equity,
        "decisions": result.decisions,
        "executed": result.executed,
        "rejections": dict(result.rejections),
        "equity_curve": list(result.equity_curve),
        "n_trades": len(result.trades),
    }
    if monte_carlo is not None:
        view["monte_carlo"] = {
            "final_equity_p5": monte_carlo.final_equity_p5,
            "final_equity_p50": monte_carlo.final_equity_p50,
            "final_equity_p95": monte_carlo.final_equity_p95,
            "max_drawdown_p95": monte_carlo.max_drawdown_p95,
            "prob_loss": monte_carlo.prob_loss,
        }
    return view


def memory_insights(memory: ProMemory) -> dict:
    counts = defaultdict(int)
    for record in memory.records():
        counts[record.kind.value] += 1
    lessons = memory.records(MemoryKind.MISTAKE) + memory.records(
        MemoryKind.WINNING_PATTERN
    )
    lessons.sort(key=lambda r: r.created_at, reverse=True)
    return {
        "counts": dict(counts),
        "recent_lessons": [
            {"kind": r.kind.value, "text": r.text} for r in lessons[:10]
        ],
    }


def agent_performance(runs: Sequence[RunRecord], memory: ProMemory) -> dict:
    """Per-agent activity plus outcome-scored accuracy.

    An agent scores on a closed trade when its vote was directional: correct
    if it voted with the executed action and the trade won, or against it
    and the trade lost. HOLD votes are neutral and not scored.
    """
    stats: dict[str, dict] = defaultdict(
        lambda: {"votes": 0, "confidence_sum": 0, "scored": 0, "correct": 0}
    )
    outcomes = {
        r.ref_id: r.payload for r in memory.records(MemoryKind.OUTCOME)
    }
    trade_records = {r.id: r for r in memory.records(MemoryKind.TRADE)}

    for run in runs:
        rec = run.recommendation
        if rec is None:
            continue
        outcome = None
        for trade_id, trade in trade_records.items():
            if trade.payload.get("recommendation_id") == rec.id:
                outcome = outcomes.get(trade_id)
                break
        for vote in rec.vote_breakdown.votes:
            row = stats[vote.agent_id]
            row["votes"] += 1
            row["confidence_sum"] += vote.confidence
            if outcome is None or vote.vote is TradeAction.HOLD:
                continue
            row["scored"] += 1
            agreed = vote.vote is rec.action
            won = bool(outcome.get("won"))
            if (agreed and won) or (not agreed and not won):
                row["correct"] += 1

    return {
        agent_id: {
            "votes": row["votes"],
            "avg_confidence": row["confidence_sum"] / row["votes"] if row["votes"] else 0,
            "scored": row["scored"],
            "hit_rate": row["correct"] / row["scored"] if row["scored"] else None,
        }
        for agent_id, row in sorted(stats.items())
    }
