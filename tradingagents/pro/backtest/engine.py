"""BacktestEngine: replay history through the *same* pipeline as live.

Loop invariants:
- decisions happen on the close of bar ``i`` from a snapshot containing
  bars ``<= i`` only; entries fill at bar ``i+1``'s open (no lookahead);
- open positions are managed against every bar before any new decision;
- position sizing uses the broker's current equity, so drawdowns shrink
  subsequent risk exactly as they would live;
- every closed trade reports its realized pnl to memory
  (``close_trade``), which is what feeds analogs and Kelly statistics.

The broker holds up to ``max_open_positions`` concurrent positions in the
single backtested symbol, bounded by an aggregate gross-exposure cap; the
engine decides on every eligible bar (not only when flat). Multi-*asset*
portfolio reconciliation still arrives with the Phase 9 layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tradingagents.contracts import ProConfig, TradeAction
from tradingagents.pro.backtest.broker import ClosedTrade, SimBroker
from tradingagents.pro.backtest.data import BarReplay
from tradingagents.pro.backtest.metrics import PerformanceReport, performance_report
from tradingagents.pro.pipeline import build_pro_pipeline

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    equity_curve: list[float]
    trades: list[ClosedTrade]
    report: PerformanceReport
    decisions: int
    executed: int
    rejections: dict[str, int] = field(default_factory=dict)

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else 0.0


class BacktestEngine:
    def __init__(
        self,
        llm,
        config: ProConfig,
        replay: BarReplay,
        broker: SimBroker | None = None,
        memory=None,
        min_history: int = 60,
        decide_every: int = 1,
        periods_per_year: int = 252,
        **pipeline_kwargs,
    ):
        if min_history < 3:
            raise ValueError("min_history must be >= 3")
        if decide_every < 1:
            raise ValueError("decide_every must be >= 1")
        self.config = config
        self.replay = replay
        self.broker = broker or SimBroker()
        self.memory = memory
        self.min_history = min_history
        self.decide_every = decide_every
        self.periods_per_year = periods_per_year
        self._pipeline = build_pro_pipeline(llm, config, memory=memory, **pipeline_kwargs)

    def run(self) -> BacktestResult:
        bars = self.replay.bars
        equity_curve: list[float] = []
        decisions = executed = 0
        rejections: dict[str, int] = {}

        for i in range(self.min_history, len(bars) - 1):
            bar = bars[i]
            for closed in self.broker.process_bar(bar):
                self._report_outcome(closed)

            # decide on every eligible bar (throttled by decide_every) even
            # while positions are open — the broker's count/exposure caps, not
            # single-position serialization, bound how many trades run.
            if (i - self.min_history) % self.decide_every == 0:
                snapshot = self.replay.snapshot_at(i)
                state = self._pipeline.invoke({
                    "snapshot": snapshot,
                    "equity": self.broker.equity(mark_price=bar.close),
                })
                decisions += 1
                outcome = self._apply_decision(state, i)
                if outcome == "executed":
                    executed += 1
                elif outcome is not None:
                    rejections[outcome] = rejections.get(outcome, 0) + 1

            equity_curve.append(self.broker.equity(mark_price=bar.close))

        for closed in self.broker.close_all(bars[-1]):
            self._report_outcome(closed)
        equity_curve.append(self.broker.equity(mark_price=bars[-1].close))

        return BacktestResult(
            equity_curve=equity_curve,
            trades=list(self.broker.closed),
            report=performance_report(
                equity_curve, self.broker.closed, self.periods_per_year
            ),
            decisions=decisions,
            executed=executed,
            rejections=rejections,
        )

    # --- internals -----------------------------------------------------------

    def _apply_decision(self, state: dict, i: int) -> str | None:
        """Open a position from an accepted directional recommendation.
        Returns 'executed', a rejection stage, or None (HOLD/no-op)."""
        rejection = state.get("rejection")
        if rejection:
            return rejection["stage"]
        rec = state.get("recommendation")
        if rec is None or rec.action is TradeAction.HOLD:
            return None
        if self._in_cooldown(rec.action.value, i):
            return "cooldown"
        fill_bar = self.replay.bars[i + 1]
        reason = self.broker.open_from_recommendation(rec, fill_bar)
        return "executed" if reason is None else reason

    def _in_cooldown(self, side: str, i: int) -> bool:
        """Anti-churn: after a stop-out, no same-side re-entry for
        ``stop_cooldown_bars`` bars (measured: instant re-buys after stops
        were 64% of all entries on 5m and re-paid costs into the same
        move). Breakeven exits don't trigger it — they banked a profit."""
        cooldown = self.config.risk.stop_cooldown_bars
        if cooldown <= 0:
            return False
        window_start = self.replay.bars[max(0, i - cooldown)].start
        return any(
            t.reason == "stop" and t.side == side and t.closed_at >= window_start
            for t in reversed(self.broker.closed[-20:])
        )

    def _report_outcome(self, trade: ClosedTrade) -> None:
        if self.memory is None:
            return
        record = self.memory.find_trade_by_recommendation(trade.recommendation_id)
        if record is None:
            logger.warning("no memory record for recommendation %s",
                           trade.recommendation_id)
            return
        self.memory.close_trade(
            record.id, pnl=trade.pnl,
            lesson=f"{trade.side} exited via {trade.reason} after "
                   f"{(trade.closed_at - trade.opened_at)}",
            event_time=trade.closed_at,  # bar time, not wall clock (MEM-01)
        )
