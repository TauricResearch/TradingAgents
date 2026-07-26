"""
Portfolio manager — the bridge between broker state and persistent storage.

Responsibilities:
  1. Record every executed trade to the database.
  2. Track open-position metadata (entry date, entry signal) in memory
     so we can compute P&L when a position is closed.
  3. Take end-of-day snapshots of portfolio value.
  4. Compute performance metrics (Sharpe, win-rate, drawdown, …).
  5. Feed realised P&L back into TradingAgents reflection loop.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from tradingbot.broker.base import BrokerAdapter, Order, OrderSide
from .database import PortfolioDatabase
from .models import PerformanceMetrics, PortfolioSnapshot, TradeRecord

logger = logging.getLogger(__name__)


class _PositionMeta:
    """In-memory metadata for an open position (not persisted separately)."""

    def __init__(self, ticker: str, entry_price: float, entry_date: str, entry_signal: str):
        self.ticker = ticker
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.entry_signal = entry_signal


class PortfolioManager:
    """
    Coordinates between the broker and the database.

    One instance should live for the lifetime of the trading session and be
    reused across all tickers so that position metadata is not lost.
    """

    def __init__(self, broker: BrokerAdapter, db: PortfolioDatabase):
        self._broker = broker
        self._db = db
        # In-memory map of ticker → position metadata.
        # Rebuilt from the trade history on startup.
        self._position_meta: Dict[str, _PositionMeta] = {}
        self._rebuild_position_meta()
        logger.info("PortfolioManager initialised")

    # ------------------------------------------------------------------ #
    # Recording trades                                                     #
    # ------------------------------------------------------------------ #

    def record_trade(
        self,
        order: Order,
        signal: str,
        agent_reasoning: str,
        trade_date: Optional[str] = None,
    ) -> TradeRecord:
        """
        Persist a filled order as a TradeRecord.

        For BUY orders, also stores in-memory entry metadata so we can
        calculate P&L when the position is eventually closed.
        """
        if trade_date is None:
            trade_date = date.today().isoformat()

        fill_price = order.filled_avg_price or 0.0
        trade = TradeRecord(
            ticker=order.ticker,
            side=order.side.value,
            qty=order.filled_qty,
            price=fill_price,
            total_value=order.filled_qty * fill_price,
            signal=signal,
            agent_reasoning=agent_reasoning,
            order_id=order.order_id,
            trade_date=trade_date,
        )
        self._db.insert_trade(trade)
        logger.info(
            "Recorded trade: %s %s %.4f @ $%.2f (signal=%s)",
            trade.side.upper(), trade.ticker, trade.qty, trade.price, signal,
        )

        if order.side == OrderSide.BUY:
            # Track entry info so we can compute P&L on exit.
            existing = self._position_meta.get(order.ticker)
            if existing is None:
                self._position_meta[order.ticker] = _PositionMeta(
                    ticker=order.ticker,
                    entry_price=fill_price,
                    entry_date=trade_date,
                    entry_signal=signal,
                )
            else:
                # Adding to existing position → update avg entry price.
                pos = self._broker.get_position(order.ticker)
                if pos:
                    existing.entry_price = pos.avg_entry_price

        return trade

    # ------------------------------------------------------------------ #
    # Closing positions & P&L reflection                                  #
    # ------------------------------------------------------------------ #

    def close_and_record(
        self,
        order: Order,
        signal: str,
        agent_reasoning: str,
        trade_date: Optional[str] = None,
    ) -> Tuple[TradeRecord, float]:
        """
        Record a SELL order and persist the closed-position P&L.

        Returns:
            (trade_record, realised_pnl)

        The caller should pass realised_pnl into
        TradingAgentsGraph.reflect_and_remember(realised_pnl)
        to close the learning loop.
        """
        if trade_date is None:
            trade_date = date.today().isoformat()

        trade = self.record_trade(order, signal, agent_reasoning, trade_date)

        meta = self._position_meta.pop(order.ticker, None)
        if meta is None:
            logger.warning(
                "No entry metadata for %s — P&L will be approximate", order.ticker
            )
            entry_price = order.filled_avg_price or 0.0
            entry_date = trade_date
            entry_signal = None
        else:
            entry_price = meta.entry_price
            entry_date = meta.entry_date
            entry_signal = meta.entry_signal

        realized_pnl = self._db.record_closed_position(
            ticker=order.ticker,
            entry_price=entry_price,
            exit_price=order.filled_avg_price or 0.0,
            qty=order.filled_qty,
            entry_date=entry_date,
            exit_date=trade_date,
            entry_signal=entry_signal,
            exit_signal=signal,
        )
        return trade, realized_pnl

    # ------------------------------------------------------------------ #
    # Daily snapshot                                                       #
    # ------------------------------------------------------------------ #

    def take_snapshot(self, snapshot_date: Optional[str] = None) -> PortfolioSnapshot:
        """
        Capture a point-in-time portfolio snapshot and persist it.
        Call this at the end of each trading day.
        """
        if snapshot_date is None:
            snapshot_date = date.today().isoformat()

        account = self._broker.get_account()
        positions = self._broker.get_positions()
        invested_value = sum(p.market_value for p in positions)

        prev = self._db.get_latest_snapshot()
        if prev and prev.snapshot_date != snapshot_date:
            daily_pnl = account.equity - prev.total_value
            daily_pnl_pct = daily_pnl / prev.total_value if prev.total_value > 0 else 0.0
        else:
            daily_pnl = 0.0
            daily_pnl_pct = 0.0

        snap = PortfolioSnapshot(
            snapshot_date=snapshot_date,
            cash=account.cash,
            invested_value=invested_value,
            total_value=account.equity,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            open_positions=len(positions),
        )
        self._db.upsert_snapshot(snap)
        logger.info(
            "Snapshot %s: total=$%.2f cash=$%.2f invested=$%.2f daily_pnl=$%.2f",
            snapshot_date, snap.total_value, snap.cash, snap.invested_value, snap.daily_pnl,
        )
        return snap

    # ------------------------------------------------------------------ #
    # Performance metrics                                                  #
    # ------------------------------------------------------------------ #

    def get_performance_metrics(self) -> PerformanceMetrics:
        """Compute statistics over all closed positions."""
        closed = self._db.get_closed_positions(limit=10_000)
        snapshots = self._db.get_snapshots(limit=365)

        wins = [r for r in closed if r["realized_pnl"] > 0]
        losses = [r for r in closed if r["realized_pnl"] <= 0]

        total = len(closed)
        win_rate = len(wins) / total if total > 0 else 0.0
        total_pnl = sum(r["realized_pnl"] for r in closed)
        avg_win = sum(r["realized_pnl"] for r in wins) / len(wins) if wins else 0.0
        avg_loss = sum(r["realized_pnl"] for r in losses) / len(losses) if losses else 0.0

        gross_profit = sum(r["realized_pnl"] for r in wins)
        gross_loss = abs(sum(r["realized_pnl"] for r in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        sharpe = self._compute_sharpe(snapshots)
        max_dd = self._compute_max_drawdown(snapshots)

        account = self._broker.get_account()
        start_value = snapshots[0].total_value if snapshots else account.equity
        total_return = (account.equity - start_value) / start_value if start_value > 0 else 0.0

        return PerformanceMetrics(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=win_rate,
            total_realized_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            current_equity=account.equity,
            starting_equity=start_value,
            total_return_pct=total_return,
        )

    def _compute_sharpe(self, snapshots: List[PortfolioSnapshot]) -> float:
        if len(snapshots) < 2:
            return 0.0
        daily_returns = [s.daily_pnl_pct for s in snapshots[1:]]
        n = len(daily_returns)
        mean = sum(daily_returns) / n
        variance = sum((r - mean) ** 2 for r in daily_returns) / n
        std = math.sqrt(variance) if variance > 0 else 0.0
        # Annualise: √252 scaling, risk-free rate ≈ 0
        return (mean / std) * math.sqrt(252) if std > 0 else 0.0

    def _compute_max_drawdown(self, snapshots: List[PortfolioSnapshot]) -> float:
        if not snapshots:
            return 0.0
        peak = snapshots[0].total_value
        max_dd = 0.0
        for s in snapshots:
            if s.total_value > peak:
                peak = s.total_value
            dd = (peak - s.total_value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    # ------------------------------------------------------------------ #
    # Convenience accessors                                                #
    # ------------------------------------------------------------------ #

    def get_open_positions(self):
        return self._broker.get_positions()

    def get_trade_history(self, ticker: Optional[str] = None, limit: int = 200):
        return self._db.get_trades(ticker=ticker, limit=limit)

    def get_equity_curve(self) -> List[PortfolioSnapshot]:
        return self._db.get_snapshots(limit=365)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _rebuild_position_meta(self) -> None:
        """
        Reconstruct in-memory entry metadata from trade history on startup.
        Only processes BUY trades that don't yet have a matching SELL.
        """
        trades = self._db.get_trades(limit=10_000)
        buy_map: Dict[str, List[TradeRecord]] = {}
        sell_qty_map: Dict[str, float] = {}

        for t in reversed(trades):  # oldest first
            if t.is_buy:
                buy_map.setdefault(t.ticker, []).append(t)
            elif t.is_sell:
                sell_qty_map[t.ticker] = sell_qty_map.get(t.ticker, 0.0) + t.qty

        for ticker, buys in buy_map.items():
            total_bought = sum(b.qty for b in buys)
            total_sold = sell_qty_map.get(ticker, 0.0)
            if total_bought > total_sold + 1e-6:
                # Position is still open — reconstruct weighted avg entry
                first_buy = buys[0]
                weighted = sum(b.qty * b.price for b in buys)
                avg_price = weighted / total_bought if total_bought > 0 else first_buy.price
                self._position_meta[ticker] = _PositionMeta(
                    ticker=ticker,
                    entry_price=avg_price,
                    entry_date=first_buy.trade_date,
                    entry_signal=first_buy.signal,
                )
        logger.debug("Rebuilt position metadata for %d tickers", len(self._position_meta))
