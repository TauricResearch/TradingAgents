"""Per-market-regime performance breakdown over the enriched trade log.

Each executed trade carries the ``market_regime`` classified (deterministically,
from bars) at its entry decision. Grouping trades by that tag shows where the
system's edge concentrates and where it should stand down. Pure and testable.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass

from tradingagents.pro.backtest.metrics import max_drawdown
from tradingagents.pro.backtest.trade_log import EnrichedTrade


@dataclass
class RegimeStats:
    regime: str
    n_trades: int
    win_rate: float
    total_net_pnl: float
    avg_net_pnl: float
    profit_factor: float
    best_trade: float
    worst_trade: float
    max_drawdown: float  # over this regime's trade-pnl equity path

    def as_dict(self) -> dict:
        return asdict(self)


def regime_breakdown(trades: list[EnrichedTrade]) -> list[RegimeStats]:
    """One ``RegimeStats`` per regime present in the trades, sorted by total
    net P&L (descending)."""
    groups: dict[str, list[EnrichedTrade]] = {}
    for t in trades:
        groups.setdefault(t.market_regime or "unknown", []).append(t)

    out: list[RegimeStats] = []
    for regime, ts in groups.items():
        pnls = [t.net_pnl for t in ts]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_win = math.fsum(wins)
        gross_loss = -math.fsum(losses)
        # a running equity path (relative) to measure intra-regime drawdown
        equity, cum = [0.0], 0.0
        for p in pnls:
            cum += p
            equity.append(cum)
        out.append(
            RegimeStats(
                regime=regime,
                n_trades=len(ts),
                win_rate=round(len(wins) / len(pnls), 4) if pnls else 0.0,
                total_net_pnl=round(math.fsum(pnls), 4),
                avg_net_pnl=round(statistics.mean(pnls), 4) if pnls else 0.0,
                profit_factor=(
                    round(gross_win / gross_loss, 4)
                    if gross_loss > 0
                    else (float("inf") if gross_win > 0 else 0.0)
                ),
                best_trade=round(max(pnls), 4) if pnls else 0.0,
                worst_trade=round(min(pnls), 4) if pnls else 0.0,
                # shift the path positive so the fractional drawdown is defined
                max_drawdown=round(
                    max_drawdown([e + 1e9 for e in equity]), 6
                ),
            )
        )
    out.sort(key=lambda r: r.total_net_pnl, reverse=True)
    return out
