# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Performance calculator for computing trading metrics from trade records."""

from collections import defaultdict
from datetime import datetime
from math import sqrt
from typing import Any, Dict, List

from .models import PerformanceMetrics, TradeRecord


class PerformanceCalculator:
    """Computes trading performance metrics from a list of TradeRecord objects.

    All computations use only standard library and the project's own models.
    No external data fetching (e.g. yfinance) is performed here.
    """

    def calculate(
        self,
        trades: List[TradeRecord],
        initial_capital: float,
        benchmark_ticker: str,
        start_date: str,
        end_date: str,
    ) -> PerformanceMetrics:
        """Calculate performance metrics from a list of closed trades.

        Args:
            trades: List of TradeRecord objects (should have exit_price/pnl filled).
            initial_capital: Starting capital for the backtest.
            benchmark_ticker: Benchmark ticker symbol (stored for reference,
                not fetched here).
            start_date: Backtest start date (YYYY-MM-DD).
            end_date: Backtest end date (YYYY-MM-DD).

        Returns:
            PerformanceMetrics dataclass with all computed statistics.
        """
        if not trades:
            return self._empty_metrics()

        # Extract per-trade return percentages
        returns = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        pnls = [t.pnl for t in trades if t.pnl is not None]

        total_trades = len(trades)
        winning = [r for r in returns if r > 0]
        losing = [r for r in returns if r <= 0]

        win_rate = (len(winning) / total_trades) * 100 if total_trades else 0.0
        avg_return = sum(returns) / len(returns) if returns else 0.0

        # Cumulative return as total PnL / initial capital
        total_pnl = sum(pnls) if pnls else 0.0
        cumulative_return = (total_pnl / initial_capital) * 100

        # Equity curve & drawdown
        equity_curve = self._build_equity_curve(trades, initial_capital)

        # Max drawdown from equity curve
        max_dd, max_dd_duration = self._max_drawdown(equity_curve)

        # Monthly returns
        monthly_rets = self._monthly_returns(trades)

        # Sharpe ratio (annualized from monthly)
        monthly_values = [m["return"] for m in monthly_rets]
        sharpe = self._sharpe_ratio(monthly_values)

        # Profit factor: gross profit / gross loss
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        # Average holding days
        avg_holding = self._avg_holding_days(trades)

        # Alpha and beta require benchmark returns; set to 0.0 as placeholder
        # (benchmark fetching is outside this calculator's scope)
        alpha = 0.0
        beta = 0.0

        return PerformanceMetrics(
            total_trades=total_trades,
            win_rate=win_rate,
            avg_return=avg_return,
            cumulative_return=cumulative_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            alpha=alpha,
            beta=beta,
            profit_factor=profit_factor,
            avg_holding_days=avg_holding,
            equity_curve=equity_curve,
            monthly_returns=monthly_rets,
        )

    def _empty_metrics(self) -> PerformanceMetrics:
        """Return a zeroed-out PerformanceMetrics for empty trade lists."""
        return PerformanceMetrics(
            total_trades=0,
            win_rate=0.0,
            avg_return=0.0,
            cumulative_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration=0,
            alpha=0.0,
            beta=0.0,
            profit_factor=0.0,
            avg_holding_days=0.0,
            equity_curve=[],
            monthly_returns=[],
        )

    def _build_equity_curve(
        self, trades: List[TradeRecord], initial_capital: float
    ) -> List[Dict[str, Any]]:
        """Build cumulative equity curve with drawdown per trade.

        Each entry contains:
            - date: the trade's exit date (or trade_date if no exit)
            - equity: cumulative equity after this trade
            - drawdown: percentage decline from peak equity at this point

        Trades are sorted by exit date before processing.
        """
        # Sort trades by exit date (fall back to trade_date)
        sorted_trades = sorted(
            trades,
            key=lambda t: t.exit_date if t.exit_date else t.trade_date,
        )

        curve: List[Dict[str, Any]] = []
        equity = initial_capital
        peak = initial_capital

        for trade in sorted_trades:
            pnl = trade.pnl if trade.pnl is not None else 0.0
            equity += pnl
            if equity > peak:
                peak = equity
            dd_pct = ((equity - peak) / peak) * 100 if peak > 0 else 0.0

            date_str = trade.exit_date if trade.exit_date else trade.trade_date
            curve.append({
                "date": date_str,
                "equity": round(equity, 2),
                "drawdown": round(dd_pct, 4),
            })

        return curve

    def _sharpe_ratio(self, monthly_returns: List[float]) -> float:
        """Compute annualized Sharpe ratio from monthly return percentages.

        Formula: sqrt(12) * mean(monthly_returns) / std(monthly_returns)
        Returns 0.0 if there are fewer than 2 data points or zero std.
        """
        if len(monthly_returns) < 2:
            return 0.0

        mean_ret = sum(monthly_returns) / len(monthly_returns)
        variance = sum((r - mean_ret) ** 2 for r in monthly_returns) / (
            len(monthly_returns) - 1
        )
        std_ret = sqrt(variance) if variance > 0 else 0.0

        if std_ret == 0.0:
            return 0.0

        return sqrt(12) * mean_ret / std_ret

    def _max_drawdown(
        self, equity_curve: List[Dict[str, Any]]
    ) -> tuple[float, int]:
        """Compute maximum drawdown percentage and duration in days.

        Args:
            equity_curve: List of dicts with 'date', 'equity', 'drawdown' keys.

        Returns:
            Tuple of (max_drawdown_pct, max_drawdown_duration_days).
            max_drawdown_pct is negative (e.g. -10.0 means 10% decline).
            Duration is the number of days from peak to trough.
        """
        if not equity_curve:
            return 0.0, 0

        peak = equity_curve[0]["equity"]
        peak_date_str = equity_curve[0]["date"]
        max_dd = 0.0
        max_dd_duration = 0

        for point in equity_curve:
            eq = point["equity"]
            date_str = point["date"]

            if eq >= peak:
                peak = eq
                peak_date_str = date_str

            dd_pct = ((eq - peak) / peak) * 100 if peak > 0 else 0.0

            if dd_pct < max_dd:
                max_dd = dd_pct
                try:
                    peak_dt = datetime.strptime(peak_date_str, "%Y-%m-%d")
                    trough_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    max_dd_duration = (trough_dt - peak_dt).days
                except ValueError:
                    max_dd_duration = 0

        return round(max_dd, 4), max_dd_duration

    def _monthly_returns(
        self, trades: List[TradeRecord]
    ) -> List[Dict[str, Any]]:
        """Group trades by month and compute average return per month.

        Uses the exit_date (or trade_date) to determine the month bucket.

        Returns:
            Sorted list of dicts with 'month' (YYYY-MM) and 'return' (avg %).
        """
        monthly: Dict[str, List[float]] = defaultdict(list)

        for trade in trades:
            date_str = trade.exit_date if trade.exit_date else trade.trade_date
            # Extract YYYY-MM
            month_key = date_str[:7]  # "2024-05" from "2024-05-01"
            ret = trade.pnl_pct if trade.pnl_pct is not None else 0.0
            monthly[month_key].append(ret)

        result = []
        for month_key in sorted(monthly.keys()):
            rets = monthly[month_key]
            avg = sum(rets) / len(rets) if rets else 0.0
            result.append({"month": month_key, "return": round(avg, 4)})

        return result

    def _avg_holding_days(self, trades: List[TradeRecord]) -> float:
        """Compute average holding period in days across all trades."""
        durations: List[int] = []
        for trade in trades:
            if trade.exit_date and trade.trade_date:
                try:
                    entry = datetime.strptime(trade.trade_date, "%Y-%m-%d")
                    exit_ = datetime.strptime(trade.exit_date, "%Y-%m-%d")
                    durations.append((exit_ - entry).days)
                except ValueError:
                    continue

        return sum(durations) / len(durations) if durations else 0.0
