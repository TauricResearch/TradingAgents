"""Retro-scorer: close the calibration loop over REAL past decisions.

Every stored run whose recommendation was never taken to a closed trade
(judge said BUY/SELL but the order was gated, venue-refused, or simply
predates execution) still made a falsifiable claim. This module scores
those claims against what price actually did next and writes OUTCOME
records so agent hit rates and the calibration chart accrue.

Honesty invariants (trader review — the calibration chart is "the
product's honesty metric"):
- only REAL recommendations from REAL runs are scored — never a fake or
  replayed LLM decision;
- outcomes are provenance-tagged ``mode: "retro"`` and excluded from the
  trade journal/blotter (they are graded predictions, not trades);
- no lesson records are written (``write_lesson=False``) — lessons are
  reserved for lived trades;
- unresolved tickets (neither stop nor final target hit yet) are skipped,
  not guessed;
- idempotent per recommendation id: re-running backfill never
  double-scores.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingagents.contracts import OHLCVBar, TradeAction, TradeRecommendation


@dataclass(frozen=True)
class RetroOutcome:
    pnl: float
    exit_price: float
    exit_reason: str  # "stop" | "take_profit"
    closed_at: object  # datetime of the resolving bar


def simulate_ticket(
    rec: TradeRecommendation, bars: list[OHLCVBar],
) -> RetroOutcome | None:
    """Walk bars AFTER the decision; first touch of stop or final target
    resolves the ticket. Conservative tie-break: a bar spanning both the
    stop and the target counts as a stop (worst case). Returns None while
    unresolved — the honest answer for a live thesis."""
    if rec.action is TradeAction.HOLD:
        return None
    entry = rec.entry_price
    stop = rec.stop_loss
    targets = rec.take_profits or []
    if entry is None or stop is None or not targets:
        return None
    final_target = targets[-1].price
    qty = rec.position_size.quantity if rec.position_size else 1.0
    direction = 1.0 if rec.action is TradeAction.BUY else -1.0

    for bar in bars:
        stop_hit = bar.low <= stop if direction > 0 else bar.high >= stop
        target_hit = (bar.high >= final_target if direction > 0
                      else bar.low <= final_target)
        if stop_hit:  # conservative: stop wins ties within one bar
            return RetroOutcome(
                pnl=(stop - entry) * qty * direction,
                exit_price=stop, exit_reason="stop", closed_at=bar.start,
            )
        if target_hit:
            return RetroOutcome(
                pnl=(final_target - entry) * qty * direction,
                exit_price=final_target, exit_reason="take_profit",
                closed_at=bar.start,
            )
    return None


def backfill_outcomes(runs, memory, bars_for,
                      open_symbols: frozenset | set = frozenset()) -> dict:
    """Score every eligible stored run. ``bars_for(run)`` returns the bars
    strictly AFTER the run's decision bar for its symbol/timeframe (the
    caller owns data access). ``open_symbols`` = symbols with a live open
    position — their tickets belong to the live loop, never to retro.
    Returns counters for the operator."""
    from tradingagents.pro.memory import MemoryKind

    scored = 0
    skipped_unresolved = 0
    skipped_ineligible = 0
    skipped_already = 0
    closed_refs = {o.ref_id for o in memory.records(MemoryKind.OUTCOME)}
    for run in runs:
        rec = getattr(run, "recommendation", None)
        if rec is None or rec.action is TradeAction.HOLD:
            skipped_ineligible += 1
            continue
        # the pipeline records a TRADE for every recommendation at decision
        # time — idempotency is "has an OUTCOME", not "has a record"
        existing = memory.find_trade_by_recommendation(rec.id)
        if existing is not None and existing.id in closed_refs:
            skipped_already += 1  # lived close or a prior backfill
            continue
        if existing is not None and run.symbol in open_symbols:
            skipped_unresolved += 1  # a live open position owns this ticket
            continue
        try:
            bars = bars_for(run)
        except Exception:
            skipped_unresolved += 1
            continue
        sim = simulate_ticket(rec, bars)
        if sim is None:
            skipped_unresolved += 1
            continue
        trade = existing or memory.record_trade(rec, event_time=run.started_at)
        memory.close_trade(
            trade.id,
            pnl=sim.pnl,
            event_time=sim.closed_at,
            details={
                "mode": "retro",
                "exit_reason": sim.exit_reason,
                "fill_price": rec.entry_price,
                "entry_price": rec.entry_price,
                "run_id": run.run_id,
            },
            write_lesson=False,
        )
        scored += 1
    return {
        "scored": scored,
        "skipped_unresolved": skipped_unresolved,
        "skipped_ineligible": skipped_ineligible,
        "skipped_already_scored": skipped_already,
    }
