"""Chart annotations: the AI's record painted onto price (chart Phase 1).

One aggregated read so the chart never fans out per-run requests: every
persisted run for a symbol (decision geometry included) plus the fills
that resulted, joined OUTCOME -> TRADE -> recommendation_id -> run. Links
that can only be inferred by time-window are labeled ``"inferred"`` —
never silently guessed. Times are epoch seconds UTC and deliberately
UNSNAPPED: only the client owns the exact bar array lightweight-charts
demands, so it snaps.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from tradingagents.pro.memory import MemoryKind, ProMemory


def _epoch(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.timestamp())


def _parse_iso(value) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(str(value))
                   .replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def _first_reason(rejection: dict | None) -> str | None:
    """The gate's own words, e.g. 'FOMC in 3.2h — new entries are blocked…'
    (R4.3: the chart popover names the event, not just the stage)."""
    reasons = (rejection or {}).get("reasons") or []
    if not reasons:
        return None
    return str(reasons[0])[:160]


def _run_view(run) -> dict:
    rec = run.recommendation
    view: dict = {
        "run_id": run.run_id,
        "time": _epoch(run.started_at),
        "action": rec.action.value if rec is not None else None,
        "rejected_at": (run.rejection or {}).get("stage"),
        "rejected_reason": _first_reason(run.rejection),
        "confidence": rec.confidence if rec is not None else None,
        "market_regime": rec.market_regime.value if rec is not None else None,
        "geometry": None,
        "span": None,
    }
    if rec is not None and rec.action.value != "HOLD" and rec.entry_price:
        view["geometry"] = {
            "entry": rec.entry_price,
            "stop": rec.stop_loss,
            "invalidation": rec.invalidation_price,
            "take_profits": [
                {"price": tp.price, "size_fraction": tp.size_fraction}
                for tp in rec.take_profits
            ],
            "direction": "long" if rec.action.value == "BUY" else "short",
        }
    return view


def _fills(memory: ProMemory, symbol: str,
           rec_to_run: dict[str, dict]) -> list[dict]:
    trades = {r.id: r for r in memory.records(MemoryKind.TRADE)}
    fills: list[dict] = []
    for outcome in memory.records(MemoryKind.OUTCOME):
        if outcome.symbol != symbol:
            continue
        if outcome.payload.get("mode", "paper") == "retro":
            # retro-scored predictions feed calibration, never the chart
            continue
        trade = trades.get(outcome.ref_id)
        rec_id = trade.payload.get("recommendation_id") if trade else None
        run = rec_to_run.get(rec_id) if rec_id else None
        opened = (trade.event_time or trade.created_at) if trade else None
        fills.append({
            "run_id": run["run_id"] if run else None,
            "link": "exact" if run else "unlinked",
            "entry_time": _epoch(opened),
            "entry_price": outcome.payload.get(
                "entry_price",
                trade.payload.get("entry_price") if trade else None),
            "closed_time": (_parse_iso(outcome.payload.get("closed_at"))
                            or _epoch(outcome.created_at)),
            "fill_price": outcome.payload.get("fill_price"),
            "pnl": outcome.payload.get("pnl", 0.0),
            "won": outcome.payload.get("won"),
            "mode": outcome.payload.get("mode", "paper"),
        })
    return fills


def _infer_links(fills: list[dict], decision_runs: list[dict]) -> None:
    """Legacy fallback: a fill with no recommendation link is attributed to
    the decision run whose [time, next-decision-time) window contains its
    entry — and labeled ``"inferred"`` so the chart can say so."""
    for fill in fills:
        if fill["run_id"] is not None or fill["entry_time"] is None:
            continue
        for i, run in enumerate(decision_runs):
            nxt = (decision_runs[i + 1]["time"]
                   if i + 1 < len(decision_runs) else None)
            if run["time"] is not None and run["time"] <= fill["entry_time"] \
                    and (nxt is None or fill["entry_time"] < nxt):
                fill["run_id"] = run["run_id"]
                fill["link"] = "inferred"
                break


def chart_annotations(runs: Sequence, memory: ProMemory, symbol: str,
                      cadence_seconds: float = 3600.0) -> dict:
    """All chart-paintable AI history for one symbol."""
    views: list[dict] = []
    rec_to_run: dict[str, dict] = {}
    for run in sorted((r for r in runs if r.symbol == symbol),
                      key=lambda r: _epoch(r.started_at) or 0):
        view = _run_view(run)
        views.append(view)
        if run.recommendation is not None:
            rec_to_run[run.recommendation.id] = view
    fills = _fills(memory, symbol, rec_to_run)
    decision_views = [v for v in views if v["geometry"] is not None]
    _infer_links(fills, decision_views)

    closed_by_run = {
        f["run_id"]: f["closed_time"]
        for f in fills
        if f["run_id"] is not None and f["closed_time"] is not None
    }
    for i, view in enumerate(decision_views):
        closed = closed_by_run.get(view["run_id"])
        nxt = (decision_views[i + 1]["time"]
               if i + 1 < len(decision_views) else None)
        if closed is not None:
            span_to, reason = closed, "closed"
        elif nxt is not None:
            # the next decision supersedes this plan on the chart
            span_to, reason = nxt, "superseded"
        else:
            span_to, reason = None, "open"
        view["span"] = {"from": view["time"], "to": span_to, "reason": reason}

    return {
        "symbol": symbol,
        "cadence_seconds": cadence_seconds,
        "runs": views,
        "fills": fills,
    }
