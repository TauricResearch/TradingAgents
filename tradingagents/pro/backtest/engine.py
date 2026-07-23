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
        strategy=None,
        htf_timeframes=None,
        funding=None,
        **pipeline_kwargs,
    ):
        if min_history < 3:
            raise ValueError("min_history must be >= 3")
        if decide_every < 1:
            raise ValueError("decide_every must be >= 1")
        self.replay = replay
        # optional perp funding (track T5): accrued on open positions each bar.
        # None → no funding (spot; existing behavior).
        self._funding = funding
        # optional higher-timeframe context (track T4): completed HTF snapshots
        # aggregated from this replay's bars, exposed look-ahead-safe via
        # StrategyContext.htf. None → no HTF (existing single-TF behavior).
        self._mtf = None
        if htf_timeframes:
            from tradingagents.pro.backtest.multitf import MultiTimeframeReplay
            self._mtf = MultiTimeframeReplay(replay, htf_timeframes)
        self.broker = broker or SimBroker()
        self.memory = memory
        self.min_history = min_history
        self.decide_every = decide_every
        self.periods_per_year = periods_per_year
        # Strategy SDK (track T1): when a strategy is supplied it owns the
        # decision — bind it (it builds its own pipeline with its params
        # applied) and use its (possibly patched) config so the engine's
        # cooldown check reads the same RiskLimits. Otherwise the legacy path
        # builds the pipeline directly from ``llm`` (unchanged).
        self._strategy = strategy
        if strategy is not None:
            # pipeline adapters build their own pipeline at bind (and may patch
            # the config); native strategies use the engine's config directly.
            self.config = (strategy.bind(config, memory=memory, **pipeline_kwargs)
                           if hasattr(strategy, "bind") else config)
            self._pipeline = None
        else:
            self.config = config
            self._pipeline = build_pro_pipeline(
                llm, config, memory=memory, **pipeline_kwargs)

    def run(self) -> BacktestResult:
        bars = self.replay.bars
        equity_curve: list[float] = []
        decisions = executed = 0
        rejections: dict[str, int] = {}
        strategy = self._strategy
        # a native strategy emits OrderIntents from on_bar (executed via the
        # broker's pending-order book); a pipeline adapter exposes decide and
        # keeps the recommendation path (bit-for-bit unchanged).
        native = strategy is not None and not hasattr(strategy, "decide")
        if native:
            strategy.on_start(self._strategy_context(self.min_history))

        for i in range(self.min_history, len(bars) - 1):
            bar = bars[i]
            # native: fill orders resting from prior bars AT this bar (before
            # managing) so a position opens at this bar's open and is then
            # managed against this bar — matching the recommendation path's
            # decision→next-bar-open→manage timing.
            if native:
                for order_id in self.broker.match_pending(bar, i):
                    executed += 1
                    self._fire_fill(strategy, order_id, bar)
            for closed in self.broker.process_bar(bar):
                self._report_outcome(closed)

            # decide on every eligible bar (throttled by decide_every) even
            # while positions are open — the broker's count/exposure caps, not
            # single-position serialization, bound how many trades run.
            if (i - self.min_history) % self.decide_every == 0:
                snapshot = self.replay.snapshot_at(i)
                equity = self.broker.equity(mark_price=bar.close)
                decisions += 1
                if native:
                    for intent in strategy.on_bar(self._strategy_context(i)):
                        self._submit_intent(intent, i, bar, equity)
                else:
                    if strategy is not None:
                        state = strategy.decide(snapshot, equity)
                    else:
                        state = self._pipeline.invoke(
                            {"snapshot": snapshot, "equity": equity})
                    outcome = self._apply_decision(state, i)
                    if outcome == "executed":
                        executed += 1
                    elif outcome is not None:
                        rejections[outcome] = rejections.get(outcome, 0) + 1

            # perp funding on open positions for holding this bar → next
            if self._funding is not None and self.broker.positions:
                hours = (bars[i + 1].start - bar.start).total_seconds() / 3600.0
                self.broker.accrue_funding(
                    self._funding, {self.replay.symbol: bar.close}, hours)

            equity_curve.append(self.broker.equity(mark_price=bar.close))

        # fill anything resting into the final bar, then force-close
        if native:
            for order_id in self.broker.match_pending(bars[-1], len(bars) - 1):
                executed += 1
                self._fire_fill(strategy, order_id, bars[-1])
        for closed in self.broker.close_all(bars[-1]):
            self._report_outcome(closed)
        equity_curve.append(self.broker.equity(mark_price=bars[-1].close))
        if native:
            strategy.on_stop(self._strategy_context(len(bars) - 1))

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

    # --- native strategy execution (order book) ------------------------------

    def _strategy_context(self, i: int):
        """Read-only view for a native strategy's on_bar/on_start/on_stop —
        the same snapshot+equity the pipeline sees, plus open positions and
        account state assembled from the broker."""
        from tradingagents.pro.backtest.strategy import (
            AccountView,
            PositionView,
            StrategyContext,
        )

        bar = self.replay.bars[i]
        mark = bar.close
        equity = self.broker.equity(mark_price=mark)
        positions = tuple(
            PositionView(
                id=oid, symbol=p.symbol, side=p.side, quantity=p.quantity,
                entry_price=p.entry_price, stop=p.stop,
                unrealized_pnl=(1 if p.side == "BUY" else -1)
                * (mark - p.entry_price) * p.quantity,
                opened_at=p.opened_at,
            )
            for oid, p in self.broker.positions.items()
        )
        params = getattr(self._strategy, "params", {})
        return StrategyContext(
            snapshot=self.replay.snapshot_at(i),
            equity=equity,
            params=params if isinstance(params, dict) else {},
            positions=positions,
            htf=self._mtf.htf_map(i) if self._mtf is not None else {},
            account=AccountView(
                equity=equity, cash_pnl=self.broker.cash_pnl,
                gross_exposure=self.broker._gross_notional(mark),
                open_positions=self.broker.open_count,
            ),
        )

    def _submit_intent(self, intent, i: int, ref_bar, equity: float) -> None:
        """Translate one OrderIntent into a pending order and submit it. Sizes
        risk_pct intents off the entry reference (limit/stop price, else the
        decision bar's close) and the bracket stop, capped by the config's
        max position — the same equity-aware sizing the pipeline uses."""
        import uuid

        from tradingagents.pro.analytics.risk import fixed_risk_position_size
        from tradingagents.pro.backtest.broker import PendingOrder

        bracket = intent.bracket
        stop_loss = bracket.stop_loss if bracket else None
        if intent.quantity is not None:
            quantity = intent.quantity
        elif intent.risk_pct is not None and stop_loss is not None:
            entry_ref = intent.limit_price or intent.stop_price or ref_bar.close
            quantity = fixed_risk_position_size(
                equity, intent.risk_pct, entry=entry_ref, stop=stop_loss,
                max_position_pct=self.config.risk.max_position_pct_equity,
            ).quantity
        else:
            return  # risk_pct sizing needs a bracket stop; nothing to submit
        self.broker.submit(PendingOrder(
            id=f"{i}-{intent.tag or uuid.uuid4().hex[:8]}",
            kind=intent.kind, side=intent.side, quantity=quantity,
            limit_price=intent.limit_price, stop_price=intent.stop_price,
            stop_loss=stop_loss,
            take_profits=list(bracket.take_profits) if bracket else [],
            trailing_mode=bracket.trailing if bracket else None,
            trailing_mult=bracket.trailing_mult if bracket else None,
            symbol=self.replay.symbol, submitted_index=i, tag=intent.tag,
        ))

    def _fire_fill(self, strategy, order_id: str, bar) -> None:
        """Notify a native strategy that one of its orders filled (opened)."""
        from tradingagents.pro.backtest.strategy import Fill

        pos = self.broker.positions.get(order_id)
        if pos is None:
            return
        strategy.on_fill(Fill(
            order_tag=order_id, symbol=pos.symbol, side=pos.side,
            quantity=pos.quantity, price=pos.entry_price,
            at=bar.start, is_entry=True,
        ))

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
