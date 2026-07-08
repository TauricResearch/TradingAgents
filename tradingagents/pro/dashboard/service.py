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


def system_status(router, equity: float | None = None) -> dict:
    """Kill switch, circuit breaker, and open book (UX review RISK-01).

    ``router`` is an ExecutionRouter or None (dashboard attached to a
    replay/monitor-only state). Read-only: reset stays an operator action.
    """
    if router is None:
        return {"attached": False, "trading_halted": None}
    breaker = router.breaker.check()
    engaged = router.kill_switch.engaged
    return {
        "attached": True,
        "kill_switch": {"engaged": engaged, "reason": router.kill_switch.reason},
        "circuit_breaker": {"tripped": breaker.tripped, "reason": breaker.reason},
        "open_positions": [
            {"symbol": symbol, "quantity": quantity}
            for symbol, quantity in sorted(router.local_book.items())
        ],
        "equity": equity,
        "trading_halted": engaged or breaker.tripped,
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
    for outcome in memory.records(MemoryKind.OUTCOME):
        trade = trades.get(outcome.ref_id)
        pnl = outcome.payload.get("pnl", 0.0)
        total_pnl += pnl
        entries.append({
            "symbol": outcome.symbol,
            "action": trade.payload.get("action") if trade else None,
            "regime": trade.payload.get("regime") if trade else None,
            "pnl": pnl,
            "won": outcome.payload.get("won"),
            "closed_at": outcome.created_at.isoformat(),
        })
    wins = sum(1 for e in entries if e["won"])
    return {
        "entries": entries,
        "total_pnl": total_pnl,
        "n_trades": len(entries),
        "win_rate": wins / len(entries) if entries else None,
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
