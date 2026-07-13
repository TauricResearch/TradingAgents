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
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from tradingagents.contracts import MarketSnapshot, ProConfig, TradeAction, TradeRecommendation
from tradingagents.pro.alerting import AlertManager
from tradingagents.pro.dashboard.app import DashboardState
from tradingagents.pro.execution import ExecutionRouter
from tradingagents.pro.memory import ProMemory
from tradingagents.pro.observability import MetricsRegistry

logger = logging.getLogger(__name__)

SnapshotSource = Callable[[], MarketSnapshot]


def _final_tp_price(rec) -> float:
    prices = getattr(rec, "take_profit_prices", None)
    if prices is not None:
        return prices[-1]
    return rec.take_profits[-1].price


@dataclass
class _RehydratedPlan:
    """Minimal exit plan reconstructed from a memory trade record; only the
    fields _manage_positions touches."""

    id: str
    action: TradeAction
    stop_loss: float
    take_profit_prices: list[float]


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
        alerts: AlertManager | None = None,
        on_event: Callable[[str, dict], None] | None = None,
        run_lock: threading.Lock | None = None,
        **pipeline_kwargs,
    ):
        self.llm = llm
        self.config = config
        self.snapshot_source = snapshot_source
        self.router = router
        self.memory = memory
        self.dashboard = dashboard_state or DashboardState(memory=memory)
        self.metrics = metrics or MetricsRegistry()
        self.alerts = alerts or AlertManager(metrics=self.metrics)
        self.on_event = on_event
        # serializes pipeline executions (hourly loop vs on-demand trigger)
        self.run_lock = run_lock or threading.Lock()
        self.pipeline_kwargs = pipeline_kwargs
        self.open_positions: dict[str, OpenPosition] = {}
        self.rehydrate()

    # --- durability (REL-01) ---------------------------------------------------

    def rehydrate(self) -> None:
        """Rebuild open-position tracking after a restart from the adapter's
        book plus memory's open trade records. Positions we cannot match to
        a remembered recommendation are left to reconcile() to flag."""
        for position in self.router.adapter.positions():
            if position.symbol in self.open_positions:
                continue
            rec = self._find_open_recommendation(position.symbol)
            if rec is None:
                logger.warning("unmatched venue position in %s; reconcile will flag it",
                               position.symbol)
                continue
            self.open_positions[position.symbol] = OpenPosition(
                recommendation=rec,
                fill_price=position.avg_price,
                quantity=position.quantity,
                entry_commission=0.0,  # already charged pre-restart
            )
            sign = 1 if position.side == "BUY" else -1
            self.router.local_book.setdefault(
                position.symbol, sign * position.quantity
            )

    def _find_open_recommendation(self, symbol: str):
        from tradingagents.pro.memory import MemoryKind

        closed_ids = {
            r.ref_id for r in self.memory.records(MemoryKind.OUTCOME)
        }
        for record in reversed(self.memory.records(MemoryKind.TRADE)):
            if record.symbol != symbol or record.id in closed_ids:
                continue
            payload = record.payload
            if not payload.get("stop_loss") or not payload.get("take_profits"):
                return None
            from tradingagents.contracts import TradeAction as TA

            return _RehydratedPlan(
                id=payload.get("recommendation_id", record.id),
                action=TA(payload["action"]),
                stop_loss=payload["stop_loss"],
                take_profit_prices=list(payload["take_profits"]),
            )
        return None

    # --- one iteration -----------------------------------------------------------

    def run_once(self, snapshot: MarketSnapshot | None = None,
                 config: ProConfig | None = None) -> dict:
        with self.run_lock:
            summary = self._run_once(snapshot=snapshot, config=config)
        self._emit("run", summary)
        for closed in summary.get("closed_positions", []):
            self._emit("position", {"state": "closed", **closed})
        if summary.get("order_status") == "filled":
            self._emit("position", {"state": "opened",
                                    "symbol": summary.get("symbol"),
                                    "action": summary.get("action")})
        self._emit("status", self._status_event())
        return summary

    def _emit(self, type_: str, data: dict) -> None:
        """UI push hook (SSE); a broken consumer never breaks the loop."""
        if self.on_event is None:
            return
        try:
            self.on_event(type_, data)
        except Exception:
            logger.exception("on_event consumer failed for %s event", type_)

    def _status_event(self) -> dict:
        from tradingagents.pro.dashboard import service as views

        try:
            equity = self.router.adapter.account().equity
        except Exception:
            equity = None
        return views.system_status(self.router, equity)

    def _run_once(self, snapshot: MarketSnapshot | None = None,
                  config: ProConfig | None = None) -> dict:
        snapshot = snapshot if snapshot is not None else self.snapshot_source()
        config = config or self.config
        self.metrics.inc("runs_total")

        reconciliation = self.router.reconcile()
        if not reconciliation.in_sync:
            self.metrics.inc("reconciliation_failures_total")
            self.alerts.emit(
                "critical", "reconciliation_drift",
                "local book and venue disagree; new entries blocked",
                missing=",".join(reconciliation.missing_on_venue),
                unknown=",".join(reconciliation.unknown_on_venue),
            )

        closed = self._manage_positions(snapshot)

        quarantined = [f for f in snapshot.missing_feeds
                       if f.startswith("news:quarantined")]
        if quarantined:
            self.alerts.emit(
                "critical", "injection_quarantined",
                f"{len(quarantined)} news item(s) quarantined as suspected "
                "prompt injection before reaching any prompt",
                symbol=snapshot.symbol,
            )

        run = self.dashboard.recorder.record_run(
            self.llm, config, snapshot, memory=self.memory,
            on_node=lambda name: self._emit("stage", {"stage": name,
                                                      "symbol": snapshot.symbol}),
            **self.pipeline_kwargs,
        )
        rec = run.recommendation
        summary: dict = {
            "run_id": run.run_id,
            "symbol": snapshot.symbol,
            "action": rec.action.value if rec else None,
            "rejected_at": run.rejection and run.rejection.get("stage"),
            "closed_positions": closed,
            "order_status": None,
            "in_sync": reconciliation.in_sync,
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
        if not reconciliation.in_sync:
            # book drift is an incident, not a trading opportunity
            summary["order_status"] = "blocked:reconciliation"
            return summary
        if (
            rec is not None
            and rec.action is not TradeAction.HOLD
            and (run.state.get("execution_status") or "").startswith("accepted")
            and rec.symbol not in self.open_positions
        ):
            # Phase 3 data-health gate: with live gates armed, degraded
            # ingestion is a hard pre-trade stop — never trade on data
            # you'd flag as degraded in the UI
            if (getattr(self.router, "live_gates", None) is not None
                    and snapshot.missing_feeds):
                self.router.audit.append("live_data_health", {
                    "recommendation_id": rec.id,
                    "missing_feeds": list(snapshot.missing_feeds),
                })
                self.alerts.emit(
                    "warning", "order_rejected",
                    f"entry for {rec.symbol} blocked: degraded feeds "
                    f"{list(snapshot.missing_feeds)}", symbol=rec.symbol,
                )
                summary["order_status"] = "blocked:data_health"
                return summary
            spread_bps = None
            if snapshot.quote and snapshot.quote.bid and snapshot.quote.ask:
                mid = (snapshot.quote.bid + snapshot.quote.ask) / 2
                if mid > 0:
                    spread_bps = 10_000.0 * (
                        snapshot.quote.ask - snapshot.quote.bid) / mid
            equity = self.router.adapter.account().equity
            result = self.router.submit_recommendation(
                rec, equity, spread_bps=spread_bps)
            summary["order_status"] = result.status
            if result.status == "rejected":
                reason = result.reason or ""
                safety_stop = reason.startswith(("kill_switch", "circuit_breaker"))
                self.alerts.emit(
                    "critical" if safety_stop else "warning",
                    "order_rejected",
                    f"order for {rec.symbol} rejected: {reason}",
                    symbol=rec.symbol,
                )
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
            except Exception as exc:
                logger.exception("service iteration failed; continuing")
                self.metrics.inc("iteration_errors_total")
                self.alerts.emit(
                    "warning", "iteration_error",
                    f"service iteration raised {type(exc).__name__}: {exc}",
                )
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                sleep(interval_seconds)

    # --- internals ----------------------------------------------------------------

    def _manage_positions(self, snapshot: MarketSnapshot) -> list[dict]:
        """Close positions whose stop or final target was breached at the
        latest bar close; report realized P&L to router + memory."""
        if not snapshot.bars:
            return []
        bar = snapshot.bars[-1]
        closed = self._consume_oms_exits(bar)
        for symbol, position in list(self.open_positions.items()):
            if symbol != snapshot.symbol:
                continue
            oms = getattr(self.router, "oms", None)
            if oms is not None and oms.has_venue_protection(symbol):
                # venue-side bracket owns the exit; bar-close management
                # would double-close (go-live Phase 2 coexistence rule)
                continue
            rec = position.recommendation
            long = rec.action is TradeAction.BUY
            # intrabar high/low with stop-first priority: identical
            # pessimistic semantics to the backtest broker (QUANT-03)
            stop_hit = bar.low <= rec.stop_loss if long else bar.high >= rec.stop_loss
            final_tp = _final_tp_price(rec)
            target_hit = bar.high >= final_tp if long else bar.low <= final_tp
            if not (stop_hit or target_hit):
                continue
            exit_reference = rec.stop_loss if stop_hit else final_tp
            result = self.router.adapter.close_position(symbol, exit_reference)
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
                                        lesson=f"{rec.action.value} exited via {reason}",
                                        event_time=bar.start)
            self.metrics.inc("positions_closed_total", reason=reason)
            self.metrics.set_gauge("last_realized_pnl", pnl)
            del self.open_positions[symbol]
            closed.append({"symbol": symbol, "pnl": pnl, "reason": reason})
        return closed

    def _consume_oms_exits(self, bar) -> list[dict]:
        """Fold venue-detected exits (brackets/watchdog flattens) into the
        SAME downstream path as bar-close exits: breaker, memory, metrics."""
        oms = getattr(self.router, "oms", None)
        if oms is None:
            return []
        oms.poll()
        closed = []
        for trade in oms.drain_closed():
            position = self.open_positions.pop(trade.symbol, None)
            self.router.record_close(trade.symbol, trade.pnl)
            if position is not None:
                record = self.memory.find_trade_by_recommendation(
                    position.recommendation.id)
                if record is not None:
                    self.memory.close_trade(
                        record.id, pnl=trade.pnl,
                        lesson=f"exited via venue {trade.reason}",
                        event_time=bar.start,
                    )
            self.metrics.inc("positions_closed_total", reason=trade.reason)
            self.metrics.set_gauge("last_realized_pnl", trade.pnl)
            closed.append({"symbol": trade.symbol, "pnl": trade.pnl,
                           "reason": trade.reason})
        return closed
