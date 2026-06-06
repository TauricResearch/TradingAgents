"""Deterministic long-only ATR backtest over stored bars.

Walks the bars one at a time; when flat, opens a position using the same ATR
levels + risk-based sizing as the live system, then simulates the fill and the
stop/take-profit exit on subsequent bars. Produces the metrics used to validate
the thresholds (hit-rate, return, drawdown).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..domain.enums import Direction
from ..domain.risk import position_size
from ..indicators import core


@dataclass
class BacktestResult:
    num_trades: int = 0
    wins: int = 0
    hit_rate: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    final_equity: float = 0.0
    trades: list[dict[str, Any]] = field(default_factory=list)


def backtest(
    bars: list[dict[str, Any]],
    *,
    k_entry: float = 0.0,
    k_stop: float = 2.0,
    k_tp: float = 3.0,
    atr_period: int = 14,
    base_risk_pct: float = 0.01,
    initial_capital: float = 100_000.0,
    max_hold: int = 40,
) -> BacktestResult:
    """Simulate the long-only ATR strategy; return performance metrics."""
    n = len(bars)
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    trades: list[dict[str, Any]] = []

    i = atr_period + 1
    while i < n:
        atr = core.atr(bars[: i + 1], atr_period)
        if not atr or atr <= 0:
            i += 1
            continue
        close = float(bars[i]["close"])
        entry = close - k_entry * atr
        stop = entry - k_stop * atr
        tp = entry + k_tp * atr
        stop_distance = entry - stop
        sizing = position_size(equity, entry, stop_distance, Direction.BUY, base_risk_pct=base_risk_pct)
        qty = sizing.quantity

        filled = False
        exit_price: Optional[float] = None
        reason: Optional[str] = None
        j = i + 1
        end = min(n, i + 1 + max_hold)
        while j < end:
            low = float(bars[j]["low"])
            high = float(bars[j]["high"])
            if not filled and low <= entry:
                filled = True
            if filled:
                if low <= stop:
                    exit_price, reason = stop, "sl"
                    break
                if high >= tp:
                    exit_price, reason = tp, "tp"
                    break
            j += 1

        if filled and exit_price is not None and qty > 0:
            pnl = (exit_price - entry) * qty
            equity += pnl
            trades.append({"entry": entry, "exit": exit_price, "reason": reason, "pnl": pnl, "qty": qty})
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
            i = j + 1
        else:
            i += 1

    wins = sum(1 for t in trades if t["pnl"] > 0)
    n_tr = len(trades)
    return BacktestResult(
        num_trades=n_tr,
        wins=wins,
        hit_rate=(wins / n_tr if n_tr else 0.0),
        total_return=equity / initial_capital - 1.0,
        max_drawdown=max_dd,
        final_equity=equity,
        trades=trades,
    )


def run_backtest(
    session: Session, symbol: str, *, interval: str = "1d", lookback: int = 2000, **params: Any
) -> BacktestResult:
    """Run the backtest on the bars stored for ``symbol``."""
    from ..indicators.db import recent_bars

    bars = recent_bars(session, symbol, interval=interval, lookback=lookback)
    return backtest(bars, **params)
