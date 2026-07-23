"""Multi-symbol backtest engine (roadmap P3 / architecture track T4).

Drives one shared ``SimBroker`` across N symbols on a single master clock (a
``PortfolioReplay``). At each master step, for every symbol that has a fresh
bar closing then:

  1. fill orders resting from that symbol's prior bars, at THIS bar (open);
  2. manage that symbol's open positions against THIS bar (stops/TPs/trailing);
  3. if warmed up, let the symbol's native strategy decide from a per-symbol,
     look-ahead-safe snapshot — new intents rest and fill on the symbol's
     NEXT bar (same decision→next-open timing as the single-symbol engine).

Portfolio equity is marked every step with each symbol's most-recent close
(``equity_marks``), so a slow symbol contributes its last close between its
own bars — never a future price. Capital is shared: the broker's count and
gross-exposure caps now bind ACROSS symbols, which is the portfolio-heat
behaviour (a per-symbol allocator / correlation filter layers on top later).

Native (order-book) strategies only — the pipeline/recommendation path is
single-symbol. One stateless strategy instance may serve every symbol
(positions come from the per-symbol context, not internal state); pass a
{symbol: strategy} mapping when a strategy holds per-symbol state.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from tradingagents.contracts import ProConfig
from tradingagents.pro.backtest.broker import ClosedTrade, PendingOrder, SimBroker
from tradingagents.pro.backtest.metrics import PerformanceReport, performance_report
from tradingagents.pro.backtest.portfolio import PortfolioReplay


@dataclass
class PortfolioBacktestResult:
    equity_curve: list[float]
    trades: list[ClosedTrade]
    report: PerformanceReport
    decisions: int
    executed: int
    symbols: tuple[str, ...]
    rejections: dict[str, int] = field(default_factory=dict)

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else 0.0


class PortfolioEngine:
    def __init__(
        self,
        replay: PortfolioReplay,
        strategy,
        config: ProConfig,
        broker: SimBroker | None = None,
        min_history: int = 60,
        decide_every: int = 1,
        periods_per_year: int = 252,
    ):
        if min_history < 3:
            raise ValueError("min_history must be >= 3")
        if decide_every < 1:
            raise ValueError("decide_every must be >= 1")
        self.replay = replay
        self.config = config
        self.broker = broker or SimBroker()
        self.min_history = min_history
        self.decide_every = decide_every
        self.periods_per_year = periods_per_year
        # one strategy per symbol; a bare strategy is shared across all symbols
        self._strategies: dict[str, object] = (
            dict(strategy) if isinstance(strategy, Mapping)
            else dict.fromkeys(replay.symbols, strategy))
        for symbol in replay.symbols:
            if symbol not in self._strategies:
                raise ValueError(f"no strategy provided for symbol {symbol!r}")
            if hasattr(self._strategies[symbol], "decide"):
                raise ValueError(
                    "PortfolioEngine drives native (order-book) strategies only; "
                    f"{symbol!r} looks like a pipeline strategy")

    def run(self) -> PortfolioBacktestResult:
        replay = self.replay
        equity_curve: list[float] = []
        decisions = executed = 0
        rejections: dict[str, int] = {}

        started: set[int] = set()
        for symbol in replay.symbols:
            strat = self._strategies[symbol]
            if id(strat) not in started:  # a shared instance starts once
                strat.on_start(self._context(symbol, 0))
                started.add(id(strat))

        for step in range(len(replay)):
            for symbol in replay.active_symbols_at(step):
                i = replay.local_index(symbol, step)
                bar = replay.bar_at(symbol, step)
                strat = self._strategies[symbol]
                # 1. fill this symbol's resting orders at this bar
                for order_id in self.broker.match_pending(bar, i, symbol=symbol):
                    executed += 1
                    self._fire_fill(strat, order_id, bar)
                # 2. manage this symbol's open positions against this bar
                #    (closed trades are recorded on the broker as they finalize)
                self.broker.process_bar(bar, symbol=symbol)
                # 3. decide (native) once warmed up, and only if a NEXT bar
                #    exists for this symbol (an intent needs a bar to fill on)
                last_index = len(replay.replay(symbol).bars) - 1
                if (i >= self.min_history and i < last_index
                        and (i - self.min_history) % self.decide_every == 0):
                    decisions += 1
                    equity = self.broker.equity_marks(self._marks_at(step))
                    for intent in strat.on_bar(self._context(symbol, step)):
                        outcome = self._submit_intent(symbol, intent, i, bar, equity)
                        if outcome is not None:
                            rejections[outcome] = rejections.get(outcome, 0) + 1
            equity_curve.append(self.broker.equity_marks(self._marks_at(step)))

        # force-close every symbol at ITS final bar (end of its data)
        for symbol in replay.symbols:
            final_bar = replay.replay(symbol).bars[-1]
            self.broker.close_all(final_bar, symbol=symbol)
        equity_curve.append(self.broker.equity_marks(self._final_marks()))
        for symbol in replay.symbols:  # one on_stop per instance
            strat = self._strategies[symbol]
            if id(strat) in started:
                strat.on_stop(self._context(symbol, len(replay) - 1))
                started.discard(id(strat))

        return PortfolioBacktestResult(
            equity_curve=equity_curve,
            trades=list(self.broker.closed),
            report=performance_report(equity_curve, self.broker.closed,
                                      self.periods_per_year),
            decisions=decisions,
            executed=executed,
            symbols=replay.symbols,
            rejections=rejections,
        )

    # --- internals -----------------------------------------------------------

    def _marks_at(self, step: int) -> dict[str, float]:
        """Each symbol's most-recent close at/before this step (look-ahead-safe;
        a not-yet-started symbol is simply absent)."""
        marks: dict[str, float] = {}
        for symbol in self.replay.symbols:
            bar = self.replay.bar_at(symbol, step)
            if bar is not None:
                marks[symbol] = bar.close
        return marks

    def _final_marks(self) -> dict[str, float]:
        return {s: self.replay.replay(s).bars[-1].close for s in self.replay.symbols}

    def _context(self, symbol: str, step: int):
        from tradingagents.pro.backtest.strategy import (
            AccountView,
            PositionView,
            StrategyContext,
        )

        marks = self._marks_at(step)
        equity = self.broker.equity_marks(marks)
        # only THIS symbol's positions are visible to its decision
        positions = tuple(
            PositionView(
                id=oid, symbol=p.symbol, side=p.side, quantity=p.quantity,
                entry_price=p.entry_price, stop=p.stop,
                unrealized_pnl=(1 if p.side == "BUY" else -1)
                * (marks.get(p.symbol, p.entry_price) - p.entry_price) * p.quantity,
                opened_at=p.opened_at,
            )
            for oid, p in self.broker.positions.items() if p.symbol == symbol
        )
        strat = self._strategies[symbol]
        params = getattr(strat, "params", {})
        snapshot = self.replay.snapshot_at(symbol, step)
        return StrategyContext(
            snapshot=snapshot,
            equity=equity,
            params=params if isinstance(params, dict) else {},
            positions=positions,
            account=AccountView(
                equity=equity, cash_pnl=self.broker.cash_pnl,
                gross_exposure=self.broker.gross_notional_marks(marks),
                open_positions=self.broker.open_count,
            ),
        )

    def _submit_intent(self, symbol: str, intent, i: int, ref_bar,
                       equity: float) -> str | None:
        """Size + submit one OrderIntent as a pending order for ``symbol``.
        Returns a rejection reason string, or None on submit."""
        from tradingagents.pro.analytics.risk import fixed_risk_position_size

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
            return "no_sizing"  # risk_pct sizing needs a bracket stop
        self.broker.submit(PendingOrder(
            id=f"{symbol}-{i}-{intent.tag or uuid.uuid4().hex[:8]}",
            kind=intent.kind, side=intent.side, quantity=quantity,
            limit_price=intent.limit_price, stop_price=intent.stop_price,
            stop_loss=stop_loss,
            take_profits=list(bracket.take_profits) if bracket else [],
            trailing_mode=bracket.trailing if bracket else None,
            trailing_mult=bracket.trailing_mult if bracket else None,
            symbol=symbol, submitted_index=i, tag=intent.tag,
        ))
        return None

    def _fire_fill(self, strategy, order_id: str, bar) -> None:
        from tradingagents.pro.backtest.strategy import Fill

        pos = self.broker.positions.get(order_id)
        if pos is None:
            return
        strategy.on_fill(Fill(
            order_tag=order_id, symbol=pos.symbol, side=pos.side,
            quantity=pos.quantity, price=pos.entry_price,
            at=bar.start, is_entry=True,
        ))


__all__ = ["PortfolioBacktestResult", "PortfolioEngine"]
