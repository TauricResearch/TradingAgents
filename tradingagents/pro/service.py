"""PaperTradingService: the deployable end-to-end loop (Phase 11).

One iteration = build snapshot -> run the full debate pipeline (recorded
for the dashboard) -> route an accepted recommendation through the
execution router -> manage open positions on bar closes -> report realized
P&L back to the router (circuit breaker) and memory (analogs, Kelly).

Position management here is bar-close based — the service reacts to stop/
target breaches observed at snapshot time. Intrabar fills are the backtest
broker's domain; live intrabar management belongs to venue-native
stop/take-profit orders once a real transport is signed off (ADR-0029).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from tradingagents.contracts import MarketSnapshot, ProConfig, TradeAction, TradeRecommendation
from tradingagents.pro.dashboard.app import DashboardState
from tradingagents.pro.execution import ExecutionRouter
from tradingagents.pro.memory import ProMemory
from tradingagents.pro.observability import MetricsRegistry

logger = logging.getLogger(__name__)

SnapshotSource = Callable[[], MarketSnapshot]


@dataclass
class OpenPosition:
    recommendation: TradeRecommendation
    fill_price: float
    quantity: float
    entry_commission: float


class PaperTradingService:
    def __init__(
        self,
        llm,
        config: ProConfig,
        snapshot_source: SnapshotSource,
        router: ExecutionRouter,
        memory: ProMemory,
        dashboard_state: DashboardState | None = None,
        metrics: MetricsRegistry | None = None,
        **pipeline_kwargs,
    ):
        self.llm = llm
        self.config = config
        self.snapshot_source = snapshot_source
        self.router = router
        self.memory = memory
        self.dashboard = dashboard_state or DashboardState(memory=memory)
        self.metrics = metrics or MetricsRegistry()
        self.pipeline_kwargs = pipeline_kwargs
        self.open_positions: dict[str, OpenPosition] = {}

    # --- one iteration -----------------------------------------------------------

    def run_once(self) -> dict:
        snapshot = self.snapshot_source()
        self.metrics.inc("runs_total")

        closed = self._manage_positions(snapshot)

        run = self.dashboard.recorder.record_run(
            self.llm, self.config, snapshot, memory=self.memory,
            **self.pipeline_kwargs,
        )
        rec = run.recommendation
        summary: dict = {
            "run_id": run.run_id,
            "action": rec.action.value if rec else None,
            "rejected_at": run.rejection and run.rejection.get("stage"),
            "closed_positions": closed,
            "order_status": None,
        }
        if run.rejection:
            self.metrics.inc("rejections_total", stage=run.rejection["stage"])
            return summary
        if rec is not None:
            self.metrics.inc("recommendations_total", action=rec.action.value)
        if closed:
            # cooldown: never re-enter on the same bar that closed a position
            # (exit-bar churn); the next iteration may enter fresh
            summary["order_status"] = "cooldown"
            return summary
        if (
            rec is not None
            and rec.action is not TradeAction.HOLD
            and (run.state.get("execution_status") or "").startswith("accepted")
            and rec.symbol not in self.open_positions
        ):
            equity = self.router.adapter.account().equity
            result = self.router.submit_recommendation(rec, equity)
            summary["order_status"] = result.status
            if result.status == "filled":
                self.metrics.inc("orders_filled_total")
                self.open_positions[rec.symbol] = OpenPosition(
                    recommendation=rec,
                    fill_price=result.fill_price,
                    quantity=result.filled_quantity,
                    entry_commission=result.commission,
                )
        return summary

    def run_forever(
        self,
        interval_seconds: float = 3600.0,
        max_iterations: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            try:
                summary = self.run_once()
                logger.info("service iteration complete",
                            extra={"extra_fields": summary})
            except Exception:
                logger.exception("service iteration failed; continuing")
                self.metrics.inc("iteration_errors_total")
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                sleep(interval_seconds)

    # --- internals ----------------------------------------------------------------

    def _manage_positions(self, snapshot: MarketSnapshot) -> list[dict]:
        """Close positions whose stop or final target was breached at the
        latest bar close; report realized P&L to router + memory."""
        if not snapshot.bars:
            return []
        last_close = snapshot.bars[-1].close
        closed = []
        for symbol, position in list(self.open_positions.items()):
            if symbol != snapshot.symbol:
                continue
            rec = position.recommendation
            long = rec.action is TradeAction.BUY
            stop_hit = last_close <= rec.stop_loss if long else last_close >= rec.stop_loss
            final_tp = rec.take_profits[-1].price
            target_hit = last_close >= final_tp if long else last_close <= final_tp
            if not (stop_hit or target_hit):
                continue
            result = self.router.adapter.close_position(symbol, last_close)
            if result.status != "filled":
                logger.warning("close failed for %s: %s", symbol, result.reason)
                continue
            sign = 1 if long else -1
            pnl = (
                sign * (result.fill_price - position.fill_price) * position.quantity
                - position.entry_commission
                - result.commission
            )
            reason = "stop" if stop_hit else "take_profit"
            self.router.record_close(symbol, pnl)
            record = self.memory.find_trade_by_recommendation(rec.id)
            if record is not None:
                self.memory.close_trade(record.id, pnl=pnl,
                                        lesson=f"{rec.action.value} exited via {reason}")
            self.metrics.inc("positions_closed_total", reason=reason)
            self.metrics.set_gauge("last_realized_pnl", pnl)
            del self.open_positions[symbol]
            closed.append({"symbol": symbol, "pnl": pnl, "reason": reason})
        return closed
